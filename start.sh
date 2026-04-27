#!/bin/bash
# start.sh — Sobe a interface Streamlit do Robô de Calibragem Amazon Ads

set -e

echo "======================================================"
echo "  Robô de Calibragem de Campanhas — Amazon Ads"
echo "======================================================"

# Instalar dependências
echo "[1/2] Instalando dependências..."
pip install -r requirements.txt -q

# Subir Streamlit
echo "[2/2] Iniciando interface web..."
echo ""
echo "  Acesse: http://localhost:8501"
echo ""
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
