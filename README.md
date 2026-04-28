# Robô de Calibragem de Campanhas — Amazon Ads

Ajusta automaticamente bids, budgets e placements de campanhas **Sponsored Products** com base em ROAS e Sales Share. Disponível como interface web (Streamlit) e API REST (FastAPI).

---

## Estrutura do projeto

```
Calibrador/
├── pipeline.py                  # Lógica de calibragem (módulo importável)
├── app.py                       # Interface web — Streamlit
├── api.py                       # API REST — FastAPI
├── calibrador_amazon_ads.py     # CLI original (linha de comando)
├── requirements.txt
├── start.sh
└── README.md
```

---

## Instalação

```bash
pip install -r requirements.txt
```

---

## Interface Web (Streamlit)

```bash
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

Acesse: **http://localhost:8501**

**O que a interface oferece:**
- Upload do BulkSheet (.xlsx)
- Sidebar com todos os parâmetros de calibragem
- Checkboxes para ativar/desativar cada módulo (Bid, Budget, Placement)
- Barra de progresso com status de cada etapa
- Cards com métricas: bids / budgets / placements alterados
- Tabela do relatório com filtro por tipo
- Botões de download da planilha ajustada e do relatório em Excel

Ou use o script de atalho:

```bash
chmod +x start.sh && ./start.sh
```

---

## API REST (FastAPI)

```bash
uvicorn api:app --host 0.0.0.0 --port 8000 --workers 4
```

Documentação interativa: **http://localhost:8000/docs**

### Endpoints

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET`  | `/health` | Status da API |
| `POST` | `/processar` | Processa o BulkSheet e retorna ajustes |
| `GET`  | `/download/{job_id}/{arquivo}` | Baixa os arquivos gerados |
| `GET`  | `/docs` | Swagger UI automático |

### Exemplo de chamada (curl)

```bash
curl -X POST "http://localhost:8000/processar" \
  -F "arquivo=@BulkSheetExport.xlsx" \
  -G \
  --data-urlencode "roas_target=4.0" \
  --data-urlencode "budget_diario=500.0" \
  --data-urlencode "bid_maximo=5.0" \
  --data-urlencode "budget_minimo=10.0" \
  --data-urlencode "dias=30" \
  --data-urlencode "calibrar_bid=true" \
  --data-urlencode "calibrar_budget=true" \
  --data-urlencode "calibrar_placement=true"
```

**Resposta:**

```json
{
  "job_id": "abc123-...",
  "resumo": {
    "bids_ajustados": 38,
    "budgets_ajustados": 6,
    "placements_ajustados": 11,
    "total_alteracoes": 55,
    "abas_removidas": []
  },
  "downloads": {
    "planilha":  "/download/abc123-.../BulkSheet_Ajustado.xlsx",
    "relatorio": "/download/abc123-.../relatorio_alteracoes.xlsx"
  },
  "relatorio": [...]
}
```

### Baixar os arquivos após processamento

```bash
# Planilha ajustada
curl -O "http://localhost:8000/download/{job_id}/BulkSheet_Ajustado.xlsx"

# Relatório Excel
curl -O "http://localhost:8000/download/{job_id}/relatorio_alteracoes.xlsx"
```

---

## CLI (linha de comando)

```bash
python calibrador_amazon_ads.py
```

Edite as flags no topo do arquivo antes de rodar:

```python
ROAS_TARGET          = 4.0
BUDGET_DIARIO_CONTA  = 500.0
BID_MAXIMO           = 5.0
BUDGET_MINIMO        = 10.0
DIAS                 = 30
```

---

## Produção (Linux com systemd + Nginx)

### 1. Serviço systemd — Streamlit

Crie `/etc/systemd/system/calibrador-ui.service`:

```ini
[Unit]
Description=Calibrador Amazon Ads — Interface Streamlit
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/calibrador
ExecStart=/opt/calibrador/venv/bin/streamlit run app.py \
          --server.address 127.0.0.1 \
          --server.port 8501 \
          --server.headless true
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 2. Serviço systemd — FastAPI

Crie `/etc/systemd/system/calibrador-api.service`:

```ini
[Unit]
Description=Calibrador Amazon Ads — API FastAPI
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/calibrador
ExecStart=/opt/calibrador/venv/bin/uvicorn api:app \
          --host 127.0.0.1 \
          --port 8000 \
          --workers 4
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Ativar e iniciar os serviços:

```bash
sudo systemctl daemon-reload
sudo systemctl enable calibrador-ui calibrador-api
sudo systemctl start calibrador-ui calibrador-api
```

### 3. Nginx reverse proxy

Crie `/etc/nginx/sites-available/calibrador`:

```nginx
server {
    listen 80;
    server_name seu-dominio.com;

    # Interface Streamlit
    location / {
        proxy_pass         http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_read_timeout 300s;
    }

    # API FastAPI
    location /api/ {
        proxy_pass       http://127.0.0.1:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        client_max_body_size 50M;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/calibrador /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

---

## Lógica dos módulos

| Módulo | Entidade | Coluna | Regra principal |
|--------|----------|--------|-----------------|
| **Bid** | Keyword / Product Targeting | AB | Baixo volume (<5×dias cliques) → +5%; desvio de ROAS → ±5% a ±20%; nunca excede Bid Máximo |
| **Budget** | Campaign | U | Ajuste por ROAS + Sales Share; proteção global impede soma > Budget Diário |
| **Placement** | Bidding Adjustment | AI | Placement=0 com ROAS bom → 10%; desvio de ROAS → ±5% a ±20%; limites 0%–900% |
