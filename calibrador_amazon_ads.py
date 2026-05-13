#!/usr/bin/env python3
"""
Robô de Calibragem de Campanhas Amazon Ads
Versão: 1.1 — delega a lógica para pipeline.rodar_calibragem.

Edite as constantes abaixo antes de rodar, ou use app.py / API.
"""

import os
import sys
import warnings
from datetime import datetime

import openpyxl

from pipeline import rodar_calibragem

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

# ============================================================
# FLAGS E PARÂMETROS  ← edite aqui antes de rodar
# ============================================================
CALIBRAR_BID = True
CALIBRAR_BUDGET = True
CALIBRAR_PLACEMENT = True

ROAS_TARGET = 4.0
BUDGET_DIARIO_SP = 500.0
BUDGET_DIARIO_SB = 0.0
BUDGET_DIARIO_SD = 0.0
BID_MAXIMO = 5.0
BUDGET_MINIMO = 10.0
DIAS = 30


def main():
    input_file = "BulkSheetExport (2).xlsx"
    output_file = "BulkSheet_Ajustado.xlsx"
    report_file = "relatorio_alteracoes.xlsx"

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print("=" * 65)
    print("  ROBÔ DE CALIBRAGEM DE CAMPANHAS — AMAZON ADS")
    print(f"  Executado em: {timestamp}")
    print("=" * 65)
    print(f"  ROAS Target:              {ROAS_TARGET}")
    print(f"  Budget diário SP:         R$ {BUDGET_DIARIO_SP:.2f}")
    print(f"  Budget diário SB:         R$ {BUDGET_DIARIO_SB:.2f}")
    print(f"  Budget diário SD:         R$ {BUDGET_DIARIO_SD:.2f}")
    print(f"  Bid Máximo:               R$ {BID_MAXIMO:.2f}")
    print(f"  Budget Mínimo:            R$ {BUDGET_MINIMO:.2f}")
    print(f"  Dias de análise:         {DIAS}")
    print(f"  Módulos ativos:           BID={CALIBRAR_BID} | BUDGET={CALIBRAR_BUDGET} | PLACEMENT={CALIBRAR_PLACEMENT}")
    print("=" * 65)

    print(f"\n[1/4] Carregando '{input_file}'...")
    if not os.path.exists(input_file):
        print(f"  ERRO: Arquivo '{input_file}' não encontrado!")
        sys.exit(1)

    def on_progress(pct, msg):
        print(f"  [{pct*100:5.1f}%] {msg}")

    try:
        resultado = rodar_calibragem(
            input_file,
            roas_target=ROAS_TARGET,
            budget_diario_sp=BUDGET_DIARIO_SP,
            budget_diario_sb=BUDGET_DIARIO_SB,
            budget_diario_sd=BUDGET_DIARIO_SD,
            bid_maximo=BID_MAXIMO,
            budget_minimo=BUDGET_MINIMO,
            dias=DIAS,
            calibrar_bid=CALIBRAR_BID,
            calibrar_budget=CALIBRAR_BUDGET,
            calibrar_placement=CALIBRAR_PLACEMENT,
            on_progress=on_progress,
        )
    except ValueError as e:
        print(f"\n  ERRO: {e}")
        sys.exit(1)

    wb = resultado["workbook"]
    relatorio = resultado["relatorio"]
    print(f"  → Abas finais: {wb.sheetnames}")

    print(f"\n[2/4] Salvando planilha '{output_file}'...")
    wb.save(output_file)
    print(f"  → OK ({output_file})")

    print(f"\n[3/4] Gerando relatório '{report_file}'...")
    wb_relatorio = openpyxl.Workbook()
    ws_relatorio = wb_relatorio.active
    ws_relatorio.title = "Relatorio"
    campos = ["Campanha", "Tipo", "Valor Antigo", "Valor Novo", "Motivo"]
    ws_relatorio.append(campos)
    for item in relatorio:
        ws_relatorio.append([item.get(campo, "") for campo in campos])
    wb_relatorio.save(report_file)
    print(f"  → {len(relatorio)} alterações em '{report_file}'")

    print("\n[4/4] Resumo")
    print("=" * 65)
    print(f"  Bids ajustados:         {resultado['n_bids']}")
    print(f"  Budgets ajustados:      {resultado['n_budgets']}")
    print(f"  Placements ajustados:   {resultado['n_placements']}")
    if resultado.get("abas_removidas"):
        print(f"  Abas RAS removidas:     {resultado['abas_removidas']}")
    print("=" * 65)


if __name__ == "__main__":
    main()
