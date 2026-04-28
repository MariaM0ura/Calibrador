"""
api.py — API REST FastAPI para o Robô de Calibragem Amazon Ads.

Executar:
    uvicorn api:app --host 0.0.0.0 --port 8000 --workers 4

Docs interativas:
    http://localhost:8000/docs
"""

import io
import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

import openpyxl
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from pipeline import rodar_calibragem

# ---------------------------------------------------------------------------
# Inicialização do app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Robô de Calibragem Amazon Ads",
    description=(
        "API para calibragem automática de bids, budgets e placements "
        "de campanhas Amazon Ads Sponsored Products."
    ),
    version="1.0.0",
    contact={"name": "Calibrador Amazon Ads"},
)

# Diretório temporário para armazenar arquivos gerados por job
_JOBS_DIR = Path(tempfile.gettempdir()) / "calibrador_jobs"
_JOBS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Sistema"], summary="Status da API")
def health():
    """Retorna status e timestamp atual da API."""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.post("/processar", tags=["Calibragem"], summary="Processa um BulkSheet e retorna ajustes")
async def processar(
    arquivo: UploadFile = File(..., description="Arquivo .xlsx exportado da Amazon Ads"),
    roas_target: float   = Query(4.0,   description="ROAS alvo das campanhas"),
    budget_diario: float = Query(500.0, description="Budget diário total da conta (R$)"),
    bid_maximo: float    = Query(5.0,   description="Bid máximo permitido por keyword (R$)"),
    budget_minimo: float = Query(10.0,  description="Budget mínimo por campanha (R$)"),
    dias: int            = Query(30,    description="Período de análise em dias (regra de baixo volume)"),
    calibrar_bid: bool        = Query(True, description="Ativar Módulo 1 — Calibragem de Bid"),
    calibrar_budget: bool     = Query(True, description="Ativar Módulo 2 — Calibragem de Budget"),
    calibrar_placement: bool  = Query(True, description="Ativar Módulo 3 — Calibragem de Placement"),
):
    """
    Recebe o BulkSheet da Amazon Ads (.xlsx) via multipart/form-data,
    executa os módulos de calibragem selecionados e retorna:

    - **resumo**: contadores de bids, budgets e placements ajustados
    - **relatorio**: lista completa de alterações com motivo
    - **downloads**: endpoints para baixar os arquivos gerados

    Os arquivos ficam disponíveis em `/download/{job_id}/{arquivo}`.
    """
    # Validar extensão
    if not (arquivo.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="O arquivo deve ter extensão .xlsx")

    # Ler bytes do upload
    file_bytes = await arquivo.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Arquivo enviado está vazio")

    # Executar pipeline
    try:
        resultado = rodar_calibragem(
            arquivo=io.BytesIO(file_bytes),
            roas_target=roas_target,
            budget_diario=budget_diario,
            bid_maximo=bid_maximo,
            budget_minimo=budget_minimo,
            dias=dias,
            calibrar_bid=calibrar_bid,
            calibrar_budget=calibrar_budget,
            calibrar_placement=calibrar_placement,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro interno durante calibragem: {exc}")

    # Criar diretório de job único
    job_id  = str(uuid.uuid4())
    job_dir = _JOBS_DIR / job_id
    job_dir.mkdir(parents=True)

    # Salvar planilha ajustada
    xlsx_name = "BulkSheet_Ajustado.xlsx"
    resultado["workbook"].save(str(job_dir / xlsx_name))

    # Salvar relatório XLSX
    relatorio_name = "relatorio_alteracoes.xlsx"
    relatorio_wb = openpyxl.Workbook()
    relatorio_ws = relatorio_wb.active
    relatorio_ws.title = "Relatorio"
    campos = ["Campanha", "Tipo", "Valor Antigo", "Valor Novo", "Motivo"]
    relatorio_ws.append(campos)
    for item in resultado["relatorio"]:
        relatorio_ws.append([item.get(campo, "") for campo in campos])
    relatorio_wb.save(job_dir / relatorio_name)

    n_total = resultado["n_bids"] + resultado["n_budgets"] + resultado["n_placements"]

    return {
        "job_id": job_id,
        "resumo": {
            "bids_ajustados":        resultado["n_bids"],
            "budgets_ajustados":     resultado["n_budgets"],
            "placements_ajustados":  resultado["n_placements"],
            "total_alteracoes":      n_total,
            "abas_removidas":        resultado["abas_removidas"],
        },
        "downloads": {
            "planilha":  f"/download/{job_id}/{xlsx_name}",
            "relatorio": f"/download/{job_id}/{relatorio_name}",
        },
        "relatorio": resultado["relatorio"],
    }


@app.get(
    "/download/{job_id}/{arquivo}",
    tags=["Calibragem"],
    summary="Baixa arquivo gerado por um job",
)
def download(job_id: str, arquivo: str):
    """
    Retorna o arquivo gerado pelo endpoint `/processar`.

    - **job_id**: identificador retornado pelo `/processar`
    - **arquivo**: `BulkSheet_Ajustado.xlsx` ou `relatorio_alteracoes.xlsx`
    """
    # Proteção contra path traversal
    if "/" in arquivo or "\\" in arquivo or ".." in arquivo:
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido")

    file_path = _JOBS_DIR / job_id / arquivo

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Arquivo não encontrado. O job pode ter expirado ou o job_id está incorreto.",
        )

    media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    return FileResponse(path=str(file_path), filename=arquivo, media_type=media_type)
