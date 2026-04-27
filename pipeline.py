"""
pipeline.py — Módulo importável de calibragem de campanhas Amazon Ads.

Uso:
    from pipeline import rodar_calibragem

    resultado = rodar_calibragem(
        arquivo=io.BytesIO(bytes_do_xlsx),
        roas_target=4.0,
        budget_diario=500.0,
        ...
    )

O parâmetro `arquivo` aceita:
  - str / Path  → caminho para o .xlsx no disco
  - bytes       → conteúdo bruto do arquivo
  - file-like   → BytesIO, UploadedFile do Streamlit, etc.

O parâmetro `on_progress` é opcional: fn(pct: float, msg: str) chamada
a cada etapa para atualizar barras de progresso externas.

Retorna dict com chaves:
  n_bids, n_budgets, n_placements, relatorio, workbook, abas_removidas
"""

import io
import warnings
from pathlib import Path

import openpyxl

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

# ---------------------------------------------------------------------------
# Constantes de layout da planilha (1-indexed, padrão openpyxl)
# ---------------------------------------------------------------------------
_COL_ENTITY         = 2   # B
_COL_OPERATION      = 3   # C
_COL_CAMPAIGN_NAME  = 10  # J  (preenchido só em linhas Campaign)
_COL_CAMPAIGN_INFO  = 12  # L  (informational — preenchido em todas as linhas)
_COL_BUDGET         = 21  # U
_COL_BID            = 28  # AB
_COL_PLACEMENT_TYPE = 34  # AH (ex: "Placement Top")
_COL_PLACEMENT_PCT  = 35  # AI
_COL_CLICKS         = 43  # AQ
_COL_SALES          = 46  # AT
_COL_ROAS           = 52  # AZ

_ABA_SP   = "Sponsored Products Campaigns"
_ABAS_RAS = ("RAS Campaigns", "RAS Search Term Report")
_PLACEMENT_MAXIMO = 900.0


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _to_float(val, default=0.0):
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _campaign_name(ws, row):
    name = ws.cell(row, _COL_CAMPAIGN_NAME).value or ws.cell(row, _COL_CAMPAIGN_INFO).value
    return (name or "").strip()


def calcular_ajuste_roas(roas: float, target: float):
    """
    Retorna (fator, motivo) para um dado ROAS e target.

    fator > 1.0 → aumento  |  fator < 1.0 → redução  |  1.0 → sem ajuste
    Exportado para testes ou uso externo.
    """
    if target <= 0 or roas < 0:
        return 1.0, "Dados inválidos (target ≤ 0 ou ROAS negativo)"

    desvio = (roas - target) / target

    if roas > target:
        if desvio < 0.15:
            return 1.05, f"ROAS {roas:.2f} acima do target em {desvio*100:.1f}% → +5%"
        elif desvio < 0.25:
            return 1.07, f"ROAS {roas:.2f} acima do target em {desvio*100:.1f}% → +7%"
        elif desvio < 0.50:
            return 1.10, f"ROAS {roas:.2f} acima do target em {desvio*100:.1f}% → +10%"
        elif desvio < 1.00:
            return 1.15, f"ROAS {roas:.2f} acima do target em {desvio*100:.1f}% → +15%"
        else:
            return 1.20, f"ROAS {roas:.2f} acima do target em {desvio*100:.1f}% → +20%"

    elif roas < target:
        if desvio > -0.15:
            return 0.90, f"ROAS {roas:.2f} abaixo do target em {abs(desvio)*100:.1f}% → -10%"
        elif desvio > -0.25:
            return 0.85, f"ROAS {roas:.2f} abaixo do target em {abs(desvio)*100:.1f}% → -15%"
        elif desvio > -0.50:
            return 0.80, f"ROAS {roas:.2f} abaixo do target em {abs(desvio)*100:.1f}% → -20%"
        else:
            return 0.80, f"ROAS {roas:.2f} muito abaixo do target em {abs(desvio)*100:.1f}% → -20%"

    return 1.0, f"ROAS {roas:.2f} igual ao target → sem ajuste"


# ---------------------------------------------------------------------------
# Módulo 1 — Bid
# ---------------------------------------------------------------------------

def _modulo_bid(ws, relatorio, cfg):
    ajustados = 0
    roas_target = cfg["roas_target"]
    bid_maximo  = cfg["bid_maximo"]
    dias        = cfg["dias"]

    for row in range(2, ws.max_row + 1):
        entity = ws.cell(row, _COL_ENTITY).value
        if entity not in ("Keyword", "Product Targeting"):
            continue

        bid_atual = _to_float(ws.cell(row, _COL_BID).value)
        if bid_atual <= 0:
            continue

        clicks = _to_float(ws.cell(row, _COL_CLICKS).value)
        roas   = _to_float(ws.cell(row, _COL_ROAS).value)
        camp   = _campaign_name(ws, row)

        # Regra de baixo volume tem prioridade sobre ROAS
        if clicks < (5 * dias):
            novo_bid = bid_atual * 1.05
            motivo   = f"Baixo volume de clicks ({int(clicks)} cliques < threshold {5 * dias})"
        else:
            fator, motivo = calcular_ajuste_roas(roas, roas_target)
            novo_bid = bid_atual * fator

        novo_bid = min(round(novo_bid, 2), bid_maximo)

        if novo_bid == bid_atual:
            continue

        ws.cell(row, _COL_BID).value       = novo_bid
        ws.cell(row, _COL_OPERATION).value = "update"
        relatorio.append({
            "Campanha": camp, "Tipo": "Bid",
            "Valor Antigo": bid_atual, "Valor Novo": novo_bid,
            "Motivo": motivo,
        })
        ajustados += 1

    return ajustados


# ---------------------------------------------------------------------------
# Módulo 2 — Budget
# ---------------------------------------------------------------------------

def _modulo_budget(ws, relatorio, cfg):
    ajustados     = 0
    roas_target   = cfg["roas_target"]
    budget_diario = cfg["budget_diario"]
    budget_minimo = cfg["budget_minimo"]

    campanhas = []
    for row in range(2, ws.max_row + 1):
        if ws.cell(row, _COL_ENTITY).value != "Campaign":
            continue
        campanhas.append({
            "row":    row,
            "camp":   _campaign_name(ws, row),
            "budget": _to_float(ws.cell(row, _COL_BUDGET).value),
            "sales":  _to_float(ws.cell(row, _COL_SALES).value),
            "roas":   _to_float(ws.cell(row, _COL_ROAS).value),
        })

    if not campanhas:
        return 0

    total_sales = sum(c["sales"] for c in campanhas)
    if total_sales <= 0:
        return 0

    # Calcular novo budget individual
    for c in campanhas:
        sales_share = c["sales"] / total_sales
        fator, motivo = calcular_ajuste_roas(c["roas"], roas_target)

        novo = c["budget"] * fator
        novo = max(novo, budget_minimo)

        # Budget máximo dinâmico por share (headroom de 1.5×)
        budget_max = max(sales_share * budget_diario * 1.5, budget_minimo)
        novo = min(novo, budget_max)

        c["novo_budget"] = round(novo, 2)
        c["motivo"] = f"Sales Share={sales_share*100:.1f}% | ROAS={c['roas']:.2f} | {motivo}"

    # Proteção global: soma dos budgets não pode ultrapassar budget diário
    soma = sum(c["novo_budget"] for c in campanhas)
    if soma > budget_diario:
        fator_global = budget_diario / soma
        for c in campanhas:
            c["novo_budget"] = round(max(c["novo_budget"] * fator_global, budget_minimo), 2)
            c["motivo"] += f" | Proteção global (fator={fator_global:.4f})"

    for c in campanhas:
        if c["novo_budget"] == c["budget"]:
            continue
        ws.cell(c["row"], _COL_BUDGET).value    = c["novo_budget"]
        ws.cell(c["row"], _COL_OPERATION).value = "update"
        relatorio.append({
            "Campanha": c["camp"], "Tipo": "Budget",
            "Valor Antigo": c["budget"], "Valor Novo": c["novo_budget"],
            "Motivo": c["motivo"],
        })
        ajustados += 1

    return ajustados


# ---------------------------------------------------------------------------
# Módulo 3 — Placement
# ---------------------------------------------------------------------------

def _modulo_placement(ws, relatorio, cfg):
    ajustados   = 0
    roas_target = cfg["roas_target"]

    for row in range(2, ws.max_row + 1):
        entity = ws.cell(row, _COL_ENTITY).value
        if entity != "Bidding Adjustment":
            continue

        placement_type = ws.cell(row, _COL_PLACEMENT_TYPE).value
        if not placement_type:
            # Linha de ajuste de audiência — ignorar
            continue

        pct_atual = _to_float(ws.cell(row, _COL_PLACEMENT_PCT).value)
        roas      = _to_float(ws.cell(row, _COL_ROAS).value)
        label     = f"{_campaign_name(ws, row)} | {placement_type}"

        nova_pct = pct_atual
        motivo   = ""

        if roas > roas_target:
            if pct_atual == 0:
                nova_pct = 10.0
                motivo   = f"ROAS {roas:.2f} acima do target, placement=0 → definido para 10%"
            else:
                fator, motivo = calcular_ajuste_roas(roas, roas_target)
                nova_pct = pct_atual * fator
        elif roas < roas_target:
            if roas == 0 and pct_atual > 0:
                nova_pct = 0.0
                motivo   = "ROAS = 0 → placement zerado"
            elif roas > 0:
                fator, motivo = calcular_ajuste_roas(roas, roas_target)
                nova_pct = pct_atual * fator

        nova_pct = round(max(0.0, min(nova_pct, _PLACEMENT_MAXIMO)), 1)

        if nova_pct == pct_atual:
            continue

        ws.cell(row, _COL_PLACEMENT_PCT).value = nova_pct
        ws.cell(row, _COL_OPERATION).value     = "update"
        relatorio.append({
            "Campanha": label, "Tipo": "Placement",
            "Valor Antigo": pct_atual, "Valor Novo": nova_pct,
            "Motivo": motivo,
        })
        ajustados += 1

    return ajustados


# ---------------------------------------------------------------------------
# Ponto de entrada principal
# ---------------------------------------------------------------------------

def rodar_calibragem(
    arquivo,
    roas_target: float = 4.0,
    budget_diario: float = 500.0,
    bid_maximo: float = 5.0,
    budget_minimo: float = 10.0,
    dias: int = 30,
    calibrar_bid: bool = True,
    calibrar_budget: bool = True,
    calibrar_placement: bool = True,
    on_progress=None,
) -> dict:
    """
    Executa o pipeline completo de calibragem Amazon Ads.

    Args:
        arquivo:             Caminho (str/Path), bytes ou file-like object do .xlsx.
        roas_target:         ROAS alvo das campanhas.
        budget_diario:       Budget diário total da conta (R$).
        bid_maximo:          Bid máximo permitido (R$).
        budget_minimo:       Budget mínimo por campanha (R$).
        dias:                Período de análise para regra de baixo volume.
        calibrar_bid:        Ativar Módulo 1 — Bid.
        calibrar_budget:     Ativar Módulo 2 — Budget.
        calibrar_placement:  Ativar Módulo 3 — Placement.
        on_progress:         Callable(pct: float, msg: str) para atualizar UI (opcional).

    Returns:
        {
          "n_bids":          int,
          "n_budgets":       int,
          "n_placements":    int,
          "relatorio":       list[dict],   # cada item tem Campanha/Tipo/Valor Antigo/Valor Novo/Motivo
          "workbook":        openpyxl.Workbook,
          "abas_removidas":  list[str],
        }

    Raises:
        ValueError: se a aba "Sponsored Products Campaigns" não existir.
    """

    def _prog(pct, msg=""):
        if on_progress:
            on_progress(pct, msg)

    cfg = {
        "roas_target":   roas_target,
        "budget_diario": budget_diario,
        "bid_maximo":    bid_maximo,
        "budget_minimo": budget_minimo,
        "dias":          dias,
    }

    # --- Carregar workbook ---
    _prog(0.05, "Carregando planilha...")
    if isinstance(arquivo, bytes):
        arquivo = io.BytesIO(arquivo)
    elif isinstance(arquivo, (str, Path)):
        pass  # openpyxl aceita diretamente
    wb = openpyxl.load_workbook(arquivo, data_only=True)

    # --- Remover abas RAS ---
    _prog(0.15, "Verificando abas RAS...")
    abas_removidas = []
    for aba in _ABAS_RAS:
        if aba in wb.sheetnames:
            del wb[aba]
            abas_removidas.append(aba)

    # --- Validar aba principal ---
    if _ABA_SP not in wb.sheetnames:
        raise ValueError(
            f"Aba '{_ABA_SP}' não encontrada. "
            f"Abas disponíveis: {wb.sheetnames}"
        )
    ws = wb[_ABA_SP]

    relatorio   = []
    n_bids      = 0
    n_budgets   = 0
    n_placements = 0

    # --- Módulo 1: Bid ---
    if calibrar_bid:
        _prog(0.30, "Módulo 1: Calibrando Bids...")
        n_bids = _modulo_bid(ws, relatorio, cfg)

    # --- Módulo 2: Budget + proteção global ---
    if calibrar_budget:
        _prog(0.55, "Módulo 2: Calibrando Budgets...")
        n_budgets = _modulo_budget(ws, relatorio, cfg)

    # --- Módulo 3: Placement ---
    if calibrar_placement:
        _prog(0.80, "Módulo 3: Calibrando Placements...")
        n_placements = _modulo_placement(ws, relatorio, cfg)

    _prog(1.0, "Concluído!")

    return {
        "n_bids":         n_bids,
        "n_budgets":      n_budgets,
        "n_placements":   n_placements,
        "relatorio":      relatorio,
        "workbook":       wb,
        "abas_removidas": abas_removidas,
    }
