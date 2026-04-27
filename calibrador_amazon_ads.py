#!/usr/bin/env python3
"""
calibrador_amazon_ads.py — CLI do Robô de Calibragem Amazon Ads.

Edite as FLAGS abaixo e execute:
    python calibrador_amazon_ads.py
"""

import csv
import os
import sys
from datetime import datetime

from pipeline import rodar_calibragem

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

INPUT_FILE  = "BulkSheetExport (2).xlsx"
OUTPUT_FILE = "BulkSheet_Ajustado.xlsx"
REPORT_FILE = "relatorio_alteracoes.csv"


def main():
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

    if not os.path.exists(INPUT_FILE):
        print(f"\n  ERRO: Arquivo '{INPUT_FILE}' não encontrado!")
        sys.exit(1)

    def on_progress(pct, msg):
        bar = "█" * int(pct * 30) + "░" * (30 - int(pct * 30))
        print(f"\r  [{bar}] {int(pct*100):3d}%  {msg:<40}", end="", flush=True)

    print()
    resultado = rodar_calibragem(
        arquivo=INPUT_FILE,
        roas_target=ROAS_TARGET,
        budget_diario=BUDGET_DIARIO_CONTA,
        bid_maximo=BID_MAXIMO,
        budget_minimo=BUDGET_MINIMO,
        dias=DIAS,
        calibrar_bid=CALIBRAR_BID,
        calibrar_budget=CALIBRAR_BUDGET,
        calibrar_placement=CALIBRAR_PLACEMENT,
        on_progress=on_progress,
    )
    print()  # nova linha após a barra de progresso

    if resultado["abas_removidas"]:
        print(f"\n  Abas RAS removidas: {resultado['abas_removidas']}")

    # Salvar relatório CSV
    with open(REPORT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        campos = ["Campanha", "Tipo", "Valor Antigo", "Valor Novo", "Motivo"]
        writer = csv.DictWriter(f, fieldnames=campos, delimiter=";")
        writer.writeheader()
        writer.writerows(resultado["relatorio"])

    # Salvar planilha
    resultado["workbook"].save(OUTPUT_FILE)

    # Resumo
    n_total = resultado["n_bids"] + resultado["n_budgets"] + resultado["n_placements"]
    print("\n" + "=" * 65)
    print("  RESUMO FINAL")
    print("=" * 65)
    print(f"  Bids ajustados:        {resultado['n_bids']}")
    print(f"  Budgets ajustados:     {resultado['n_budgets']}")
    print(f"  Placements ajustados:  {resultado['n_placements']}")
    print(f"  Total de alterações:   {n_total}")
    print("=" * 65)
    print(f"\n  Outputs gerados:")
    print(f"    → {OUTPUT_FILE}")
    print(f"    → {REPORT_FILE}")
    print()


if __name__ == "__main__":
    main()
