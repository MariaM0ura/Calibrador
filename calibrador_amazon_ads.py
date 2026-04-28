#!/usr/bin/env python3
"""
Robô de Calibragem de Campanhas Amazon Ads
Versão: 1.0

Estrutura da aba "Sponsored Products Campaigns":
  Col B (2)  : Entity
  Col C (3)  : Operation  → recebe "update" quando alterado
  Col J (10) : Campaign Name
  Col U (21) : Daily Budget
  Col AB (28): Bid
  Col AH (34): Placement (tipo: Top, Product Page, Rest Of Search)
  Col AI (35): Percentage (% de ajuste de placement)
  Col AQ (43): Clicks
  Col AT (46): Sales
  Col AZ (52): ROAS
"""

import os
import sys
import warnings
import openpyxl
from datetime import datetime

# Suprimir warnings do openpyxl sobre estilo padrão
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

# ============================================================
# FLAGS DE CONTROLE  ← edite aqui antes de rodar
# ============================================================
CALIBRAR_BID        = True
CALIBRAR_BUDGET     = True
CALIBRAR_PLACEMENT  = True

ROAS_TARGET          = 4.0     # ROAS alvo das campanhas
BUDGET_DIARIO_CONTA  = 500.0   # Budget diário total da conta (R$)
BID_MAXIMO           = 5.0     # Bid máximo permitido (R$)
BUDGET_MINIMO        = 10.0    # Budget mínimo por campanha (R$)
DIAS                 = 30      # Período de análise (dias)
PLACEMENT_MAXIMO     = 900.0   # Máximo de ajuste de placement (%)

# ============================================================
# ÍNDICES DE COLUNAS (1-indexed, padrão openpyxl)
# ============================================================
COL_ENTITY          = 2   # B
COL_OPERATION       = 3   # C
COL_CAMPAIGN_NAME   = 10  # J
COL_BUDGET          = 21  # U``
COL_BID             = 28  # AB
COL_PLACEMENT_TYPE  = 34  # AH
COL_PLACEMENT_PCT   = 35  # AI
COL_CLICKS          = 43  # AQ
COL_SALES           = 46  # AT
COL_ROAS            = 52  # AZ
COL_CAMPAIGN_INFO   = 12  # L  (Campaign Name Informational — preenchido em linhas não-Campaign)


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def to_float(val, default=0.0):
    """Converte valor de célula para float com segurança."""
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def get_campaign_name(ws, row):
    """Retorna o nome da campanha de uma linha (coluna J ou L, o que estiver preenchido)."""
    name_j = ws.cell(row, COL_CAMPAIGN_NAME).value
    name_l = ws.cell(row, COL_CAMPAIGN_INFO).value
    return (name_j or name_l or "").strip()


def calcular_ajuste_roas(roas, target):
    """
    Calcula o fator de ajuste e o motivo com base no desvio de ROAS em relação ao target.

    Retorna: (fator: float, motivo: str)
      fator > 1.0  → aumento
      fator < 1.0  → redução
      fator = 1.0  → sem alteração
    """
    if target <= 0 or roas < 0:
        return 1.0, "Dados inválidos (target=0 ou ROAS negativo)"

    desvio = (roas - target) / target  # positivo = acima, negativo = abaixo

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

    else:
        return 1.0, f"ROAS {roas:.2f} igual ao target → sem ajuste"


# ============================================================
# MÓDULO 1 — CALIBRAGEM DE BID
# ============================================================

def modulo_bid(ws, relatorio):
    """
    Ajusta bids (coluna AB) para entidades Keyword e Product Targeting.

    Regra de baixo volume: se clicks < (5 × DIAS) → +5% (prioridade sobre ROAS).
    Regras ROAS: desvio em relação ao ROAS_TARGET → faixas de aumento/redução.
    Proteção: novo bid nunca ultrapassa BID_MAXIMO.
    """
    print("\n[MÓDULO 1] Calibragem de Bid")
    print(f"  Parâmetros: ROAS_TARGET={ROAS_TARGET} | BID_MAXIMO={BID_MAXIMO} | DIAS={DIAS}")
    ajustados = 0

    for row in range(2, ws.max_row + 1):
        entity = ws.cell(row, COL_ENTITY).value

        if entity not in ("Keyword", "Product Targeting"):
            continue

        bid_atual = to_float(ws.cell(row, COL_BID).value)
        if bid_atual <= 0:
            continue  # sem bid definido, pular

        clicks = to_float(ws.cell(row, COL_CLICKS).value)
        roas   = to_float(ws.cell(row, COL_ROAS).value)
        camp   = get_campaign_name(ws, row)

        # Regra de baixo volume (prioridade)
        if clicks < (5 * DIAS):
            novo_bid = bid_atual * 1.05
            motivo   = f"Baixo volume de clicks ({int(clicks)} cliques < threshold {5*DIAS})"
        else:
            fator, motivo = calcular_ajuste_roas(roas, ROAS_TARGET)
            novo_bid = bid_atual * fator

        # Proteção: respeitar bid máximo
        novo_bid = min(novo_bid, BID_MAXIMO)
        novo_bid = round(novo_bid, 2)

        if novo_bid == bid_atual:
            continue

        ws.cell(row, COL_BID).value       = novo_bid
        ws.cell(row, COL_OPERATION).value = "update"

        relatorio.append({
            "Campanha":     camp,
            "Tipo":         "Bid",
            "Valor Antigo": bid_atual,
            "Valor Novo":   novo_bid,
            "Motivo":       motivo,
        })
        ajustados += 1

    print(f"  → {ajustados} bids ajustados")
    return ajustados


# ============================================================
# MÓDULO 2 — CALIBRAGEM DE BUDGET
# ============================================================

def modulo_budget(ws, relatorio):
    """
    Ajusta budgets diários (coluna U) para entidades Campaign.

    Etapas:
      1. Soma Sales totais de todas as campanhas.
      2. Calcula Sales Share por campanha.
      3. Calcula desvio de ROAS e aplica fator de ajuste.
      4. Aplica limites: mínimo fixo e máximo dinâmico por share.
      5. Proteção global: se soma > BUDGET_DIARIO_CONTA, aplica fator proporcional.
    """
    print("\n[MÓDULO 2] Calibragem de Budget")
    print(f"  Parâmetros: ROAS_TARGET={ROAS_TARGET} | BUDGET_DIARIO={BUDGET_DIARIO_CONTA} | BUDGET_MIN={BUDGET_MINIMO}")

    # --- Etapa 1: Coletar campanhas ---
    campanhas = []
    for row in range(2, ws.max_row + 1):
        if ws.cell(row, COL_ENTITY).value != "Campaign":
            continue
        campanhas.append({
            "row":    row,
            "camp":   get_campaign_name(ws, row),
            "budget": to_float(ws.cell(row, COL_BUDGET).value),
            "sales":  to_float(ws.cell(row, COL_SALES).value),
            "roas":   to_float(ws.cell(row, COL_ROAS).value),
        })

    if not campanhas:
        print("  → Nenhuma campanha encontrada")
        return 0

    total_sales = sum(c["sales"] for c in campanhas)
    print(f"  → {len(campanhas)} campanhas | Sales total: R$ {total_sales:,.2f}")

    if total_sales <= 0:
        print("  → AVISO: Sales total = 0, skipping budget calibration")
        return 0

    # --- Etapa 2-4: Calcular novo budget individual ---
    for c in campanhas:
        sales_share = c["sales"] / total_sales  # proporção 0-1
        fator, motivo = calcular_ajuste_roas(c["roas"], ROAS_TARGET)

        novo_budget = c["budget"] * fator

        # Respeitar budget mínimo
        novo_budget = max(novo_budget, BUDGET_MINIMO)

        # Budget máximo dinâmico: share da campanha × budget diário × fator de headroom (1.5)
        budget_max_dinamico = max(sales_share * BUDGET_DIARIO_CONTA * 1.5, BUDGET_MINIMO)
        novo_budget = min(novo_budget, budget_max_dinamico)

        c["novo_budget"] = round(novo_budget, 2)
        c["motivo"] = (
            f"Sales Share={sales_share*100:.1f}% | ROAS={c['roas']:.2f} | {motivo}"
        )

    # --- Etapa 5: Proteção global ---
    soma_calculada = sum(c["novo_budget"] for c in campanhas)
    print(f"  → Soma pré-proteção: R$ {soma_calculada:,.2f} | Limite: R$ {BUDGET_DIARIO_CONTA:,.2f}")

    if soma_calculada > BUDGET_DIARIO_CONTA:
        fator_global = BUDGET_DIARIO_CONTA / soma_calculada
        print(f"  → PROTEÇÃO GLOBAL ativada! Fator de escala: {fator_global:.6f}")
        for c in campanhas:
            c["novo_budget"] = round(max(c["novo_budget"] * fator_global, BUDGET_MINIMO), 2)
            c["motivo"] += f" | Proteção global aplicada (fator={fator_global:.4f})"
    else:
        print("  → Soma dentro do limite — proteção global não necessária")

    # --- Etapa 6: Aplicar no workbook ---
    ajustados = 0
    for c in campanhas:
        if c["novo_budget"] == c["budget"]:
            continue

        ws.cell(c["row"], COL_BUDGET).value    = c["novo_budget"]
        ws.cell(c["row"], COL_OPERATION).value = "update"

        relatorio.append({
            "Campanha":     c["camp"],
            "Tipo":         "Budget",
            "Valor Antigo": c["budget"],
            "Valor Novo":   c["novo_budget"],
            "Motivo":       c["motivo"],
        })
        ajustados += 1

    print(f"  → {ajustados} budgets ajustados")
    return ajustados


# ============================================================
# MÓDULO 3 — CALIBRAGEM DE PLACEMENT
# ============================================================

def modulo_placement(ws, relatorio):
    """
    Ajusta percentual de placement (coluna AI) para entidades Bidding Adjustment
    que possuem tipo de placement definido (coluna AH não vazia).

    O ROAS usado é sempre o da própria linha de placement (coluna AZ).

    Regras:
      ROAS > target E pct = 0  → definir 10%
      ROAS > target E pct > 0  → aumentar conforme faixas
      ROAS < target            → reduzir (mínimo 0%)
    """
    print("\n[MÓDULO 3] Calibragem de Placement")
    print(f"  Parâmetros: ROAS_TARGET={ROAS_TARGET} | PLACEMENT_MAX={PLACEMENT_MAXIMO}%")
    ajustados = 0

    for row in range(2, ws.max_row + 1):
        entity = ws.cell(row, COL_ENTITY).value
        if entity != "Bidding Adjustment":
            continue

        placement_type = ws.cell(row, COL_PLACEMENT_TYPE).value
        if not placement_type:
            # Linha de ajuste de audiência (sem tipo de placement) — ignorar
            continue

        pct_atual = to_float(ws.cell(row, COL_PLACEMENT_PCT).value)
        roas      = to_float(ws.cell(row, COL_ROAS).value)
        camp      = get_campaign_name(ws, row)
        label     = f"{camp} | {placement_type}"

        nova_pct = pct_atual
        motivo   = ""

        if roas > ROAS_TARGET:
            if pct_atual == 0:
                nova_pct = 10.0
                motivo   = f"ROAS {roas:.2f} acima do target e placement=0 → definido para 10%"
            else:
                fator, msg = calcular_ajuste_roas(roas, ROAS_TARGET)
                nova_pct   = pct_atual * fator
                motivo     = msg

        elif roas < ROAS_TARGET:
            if roas == 0 and pct_atual > 0:
                nova_pct = 0.0
                motivo   = "ROAS = 0 → placement zerado"
            elif roas > 0:
                fator, msg = calcular_ajuste_roas(roas, ROAS_TARGET)
                nova_pct   = pct_atual * fator
                motivo     = msg
            # roas == 0 e pct_atual == 0: sem alteração

        # Limites: [0, PLACEMENT_MAXIMO]
        nova_pct = max(0.0, min(nova_pct, PLACEMENT_MAXIMO))
        nova_pct = round(nova_pct, 1)

        if nova_pct == pct_atual:
            continue

        ws.cell(row, COL_PLACEMENT_PCT).value = nova_pct
        ws.cell(row, COL_OPERATION).value     = "update"

        relatorio.append({
            "Campanha":     label,
            "Tipo":         "Placement",
            "Valor Antigo": pct_atual,
            "Valor Novo":   nova_pct,
            "Motivo":       motivo,
        })
        ajustados += 1

    print(f"  → {ajustados} placements ajustados")
    return ajustados


# ============================================================
# MAIN
# ============================================================

def main():
    input_file  = "BulkSheetExport (2).xlsx"
    output_file = "BulkSheet_Ajustado.xlsx"
    report_file = "relatorio_alteracoes.xlsx"

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print("=" * 65)
    print("  ROBÔ DE CALIBRAGEM DE CAMPANHAS — AMAZON ADS")
    print(f"  Executado em: {timestamp}")
    print("=" * 65)
    print(f"  ROAS Target:           {ROAS_TARGET}")
    print(f"  Budget Diário Conta:   R$ {BUDGET_DIARIO_CONTA:.2f}")
    print(f"  Bid Máximo:            R$ {BID_MAXIMO:.2f}")
    print(f"  Budget Mínimo:         R$ {BUDGET_MINIMO:.2f}")
    print(f"  Dias de análise:       {DIAS}")
    print(f"  Módulos ativos:        BID={CALIBRAR_BID} | BUDGET={CALIBRAR_BUDGET} | PLACEMENT={CALIBRAR_PLACEMENT}")
    print("=" * 65)

    # --- [1/8] Carregar planilha ---
    print(f"\n[1/8] Carregando '{input_file}'...")
    if not os.path.exists(input_file):
        print(f"  ERRO: Arquivo '{input_file}' não encontrado!")
        sys.exit(1)

    wb = openpyxl.load_workbook(input_file, data_only=True)
    print(f"  → Abas encontradas: {wb.sheetnames}")

    # --- [2/8] Remover abas RAS ---
    print("\n[2/8] Verificando abas RAS...")
    for aba_ras in ("RAS Campaigns", "RAS Search Term Report"):
        if aba_ras in wb.sheetnames:
            del wb[aba_ras]
            print(f"  → Aba '{aba_ras}' REMOVIDA")
        else:
            print(f"  → Aba '{aba_ras}' não encontrada (OK)")

    # Verificar aba principal
    aba_sp = "Sponsored Products Campaigns"
    if aba_sp not in wb.sheetnames:
        print(f"\n  ERRO: Aba '{aba_sp}' não encontrada!")
        sys.exit(1)
    ws = wb[aba_sp]
    print(f"  → Aba '{aba_sp}' carregada ({ws.max_row} linhas × {ws.max_column} colunas)")

    relatorio = []
    n_bids = n_budgets = n_placements = 0

    # --- [3/8] Módulo 1 — Bid ---
    if CALIBRAR_BID:
        print("\n[3/8] Módulo 1 — Calibragem de Bid")
        n_bids = modulo_bid(ws, relatorio)
    else:
        print("\n[3/8] Módulo 1 (Bid) — DESATIVADO")

    # --- [4/8] e [5/8] Módulo 2 — Budget + Proteção Global ---
    if CALIBRAR_BUDGET:
        print("\n[4/8] Módulo 2 — Calibragem de Budget (inclui proteção global)")
        n_budgets = modulo_budget(ws, relatorio)
    else:
        print("\n[4/8] Módulo 2 (Budget) — DESATIVADO")

    # --- [6/8] Módulo 3 — Placement ---
    if CALIBRAR_PLACEMENT:
        print("\n[6/8] Módulo 3 — Calibragem de Placement")
        n_placements = modulo_placement(ws, relatorio)
    else:
        print("\n[6/8] Módulo 3 (Placement) — DESATIVADO")

    # --- [7/8] Relatório de alterações ---
    print(f"\n[7/8] Gerando relatório '{report_file}'...")
    wb_relatorio = openpyxl.Workbook()
    ws_relatorio = wb_relatorio.active
    ws_relatorio.title = "Relatorio"
    campos = ["Campanha", "Tipo", "Valor Antigo", "Valor Novo", "Motivo"]
    ws_relatorio.append(campos)
    for item in relatorio:
        ws_relatorio.append([item.get(campo, "") for campo in campos])
    wb_relatorio.save(report_file)
    print(f"  → {len(relatorio)} alterações registradas em '{report_file}'")

    # --- [8/8] Exportar planilha final ---
    print(f"\n[8/8] Exportando '{output_file}'...")
    wb.save(output_file)
    print(f"  → Salvo com sucesso: '{output_file}'")

    # --- Resumo ---
    total = n_bids + n_budgets + n_placements
    print("\n" + "=" * 65)
    print("  RESUMO FINAL")
    print("=" * 65)
    print(f"  Bids ajustados:        {n_bids}")
    print(f"  Budgets ajustados:     {n_budgets}")
    print(f"  Placements ajustados:  {n_placements}")
    print(f"  Total de alterações:   {total}")
    print("=" * 65)
    print(f"\n  Outputs gerados:")
    print(f"    → {output_file}     (planilha pronta para upload)")
    print(f"    → {report_file}  (log de alterações)")
    print()


if __name__ == "__main__":
    main()
