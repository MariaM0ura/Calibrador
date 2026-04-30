"""
app.py — Interface web Streamlit para o Robô de Calibragem Amazon Ads.

Executar:
    streamlit run app.py --server.address 0.0.0.0 --server.port 8501
"""

import io

import pandas as pd
import streamlit as st

from pipeline import rodar_calibragem

# ---------------------------------------------------------------------------
# Configuração da página
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Robô de Calibragem — Amazon Ads",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Sidebar — parâmetros de calibragem
# ---------------------------------------------------------------------------
st.sidebar.title("⚙️ Configurações")
st.sidebar.markdown("---")

st.sidebar.subheader("Parâmetros gerais")
roas_target    = st.sidebar.number_input("ROAS Target",                value=4.0,   min_value=0.1,  step=0.1,  format="%.1f")
budget_diario  = st.sidebar.number_input("Budget Diário da Conta", value=500.0, min_value=1.0,  step=10.0, format="%.2f")
bid_maximo     = st.sidebar.number_input("Bid Máximo",            value=5.0,   min_value=0.01, step=0.5,  format="%.2f")
budget_minimo  = st.sidebar.number_input("Budget Mínimo",         value=10.0,  min_value=1.0,  step=1.0,  format="%.2f")
dias           = st.sidebar.number_input("Período de análise (dias)",   value=30,    min_value=1,    max_value=365, step=1)

st.sidebar.markdown("---")
st.sidebar.subheader("Módulos ativos")
calibrar_bid        = st.sidebar.checkbox("✅ Calibrar Bid",       value=True)
calibrar_budget     = st.sidebar.checkbox("✅ Calibrar Budget",    value=True)
calibrar_placement  = st.sidebar.checkbox("✅ Calibrar Placement", value=True)
calibrar_budget_sb  = st.sidebar.checkbox("✅ Incluir Sponsored Brands no budget", value=True)
calibrar_budget_sd  = st.sidebar.checkbox("✅ Incluir Sponsored Display no budget", value=True)

st.sidebar.markdown("---")
st.sidebar.caption("Robô de Calibragem v1.0")

# ---------------------------------------------------------------------------
# Cabeçalho principal
# ---------------------------------------------------------------------------
st.title("🤖 Robô de Calibragem de Campanhas")
st.subheader("Amazon Ads — Sponsored Products, Sponsored Brands e Sponsored Display")
st.markdown(
    "Faça upload do **BulkSheet** exportado da Amazon Ads, configure os parâmetros "
    "na barra lateral e clique em **▶ Rodar Calibragem**."
)
st.markdown("---")

# ---------------------------------------------------------------------------
# Upload do arquivo
# ---------------------------------------------------------------------------
uploaded_file = st.file_uploader(
    "📂 Selecione o arquivo BulkSheet (.xlsx)",
    type=["xlsx"],
    help="Arquivo exportado direto da plataforma Amazon Ads.",
)

if uploaded_file:
    size_kb = len(uploaded_file.getvalue()) / 1024
    st.success(f"Arquivo carregado: **{uploaded_file.name}** ({size_kb:.1f} KB)")

# ---------------------------------------------------------------------------
# Botão de execução
# ---------------------------------------------------------------------------
rodar = st.button(
    "▶ Rodar Calibragem",
    disabled=not uploaded_file,
    type="primary",
    use_container_width=True,
)

if rodar and uploaded_file:
    # Limpar resultado anterior
    for key in ("resultado", "xlsx_bytes", "relatorio_xlsx_bytes"):
        st.session_state.pop(key, None)

    progress_bar = st.progress(0.0)
    status_text  = st.empty()

    def on_progress(pct, msg):
        progress_bar.progress(min(pct, 1.0))
        status_text.markdown(f"⏳ **{msg}**")

    try:
        file_bytes = uploaded_file.getvalue()
        resultado  = rodar_calibragem(
            arquivo=io.BytesIO(file_bytes),
            roas_target=float(roas_target),
            budget_diario=float(budget_diario),
            bid_maximo=float(bid_maximo),
            budget_minimo=float(budget_minimo),
            dias=int(dias),
            calibrar_bid=calibrar_bid,
            calibrar_budget=calibrar_budget,
            calibrar_placement=calibrar_placement,
            incluir_budget_sb=calibrar_budget_sb,
            incluir_budget_sd=calibrar_budget_sd,
            on_progress=on_progress,
        )

        # Serializar workbook para bytes (download)
        status_text.markdown("⏳ **Preparando downloads...**")
        wb_buffer = io.BytesIO()
        resultado["workbook"].save(wb_buffer)
        wb_buffer.seek(0)

        # Serializar relatório XLSX para bytes (download)
        relatorio_buffer = io.BytesIO()
        df_relatorio = pd.DataFrame(
            resultado["relatorio"],
            columns=["Campanha", "Tipo", "Valor Antigo", "Valor Novo", "Motivo"],
        )
        df_relatorio.to_excel(relatorio_buffer, index=False, sheet_name="Relatorio")
        relatorio_buffer.seek(0)

        # Armazenar na sessão
        st.session_state["resultado"]  = resultado
        st.session_state["xlsx_bytes"] = wb_buffer.getvalue()
        st.session_state["relatorio_xlsx_bytes"] = relatorio_buffer.getvalue()

        progress_bar.progress(1.0)
        status_text.empty()

    except ValueError as e:
        progress_bar.empty()
        status_text.empty()
        st.error(f"❌ Erro de validação: {e}")
        st.stop()
    except Exception as e:
        progress_bar.empty()
        status_text.empty()
        st.error(f"❌ Erro inesperado: {e}")
        st.stop()

# ---------------------------------------------------------------------------
# Resultados (persistem via session_state entre reruns)
# ---------------------------------------------------------------------------
if "resultado" in st.session_state:
    resultado = st.session_state["resultado"]
    n_total   = resultado["n_bids"] + resultado["n_budgets"] + resultado["n_placements"]

    st.markdown("---")
    st.success(f"✅ Calibragem concluída com **{n_total} alterações** aplicadas.")

    if resultado["abas_removidas"]:
        st.info(f"🗑️ Abas RAS removidas: `{'`, `'.join(resultado['abas_removidas'])}`")

    # --- Cards de métricas ---
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🎯 Bids Alterados",       resultado["n_bids"])
    col2.metric("💰 Budgets Alterados",    resultado["n_budgets"])
    col3.metric("📍 Placements Alterados", resultado["n_placements"])
    col4.metric("📊 Total de Alterações",  n_total)

    st.markdown("---")

    # --- Tabela de relatório com filtro ---
    st.subheader("📋 Relatório de Alterações")
    relatorio = resultado["relatorio"]

    if relatorio:
        df = pd.DataFrame(relatorio)

        # Filtro por tipo
        tipos_disponiveis = sorted(df["Tipo"].unique().tolist())
        tipos_selecionados = st.multiselect(
            "Filtrar por tipo de ajuste:",
            options=tipos_disponiveis,
            default=tipos_disponiveis,
        )

        df_filtrado = df[df["Tipo"].isin(tipos_selecionados)] if tipos_selecionados else df

        # Formatar valores numéricos
        df_display = df_filtrado.copy()
        df_display["Valor Antigo"] = df_display["Valor Antigo"].map("{:.2f}".format)
        df_display["Valor Novo"]   = df_display["Valor Novo"].map("{:.2f}".format)

        st.dataframe(df_display, use_container_width=True, hide_index=True)
        st.caption(f"Exibindo {len(df_filtrado)} de {len(df)} alterações.")
    else:
        st.info("ℹ️ Nenhuma alteração foi necessária com os parâmetros atuais.")

    st.markdown("---")

    # --- Botões de download ---
    st.subheader("⬇️ Downloads")
    dl_col1, dl_col2 = st.columns(2)

    dl_col1.download_button(
        label="📥 BulkSheet Ajustado (.xlsx)",
        data=st.session_state["xlsx_bytes"],
        file_name="BulkSheet_Ajustado.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        type="primary",
    )

    dl_col2.download_button(
        label="📥 Relatório de Alterações (.xlsx)",
        data=st.session_state["relatorio_xlsx_bytes"],
        file_name="relatorio_alteracoes.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
