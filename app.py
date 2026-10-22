"""Simulador de frete: app Streamlit (dados fictícios de exemplo)."""
from pathlib import Path

import pandas as pd
import streamlit as st

import frete

DATA = Path(__file__).parent / "data"
AZUL = "#1F4E9C"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

st.set_page_config(page_title="Simulador de Frete", page_icon="🚚", layout="wide")


def brl(valor: float) -> str:
    if pd.isna(valor):
        return "-"
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def delta_brl(atual: float, base: float) -> str | None:
    dif = atual - base
    if abs(dif) < 0.005:
        return None
    return ("-" if dif < 0 else "+") + brl(abs(dif))


def ler_arquivo(arquivo) -> pd.DataFrame:
    if arquivo.name.lower().endswith(".csv"):
        return pd.read_csv(arquivo)
    return pd.read_excel(arquivo)


@st.cache_data
def carregar_exemplo() -> tuple[pd.DataFrame, pd.DataFrame]:
    return (
        pd.read_csv(DATA / "pedidos_exemplo.csv"),
        pd.read_csv(DATA / "tabela_frete_exemplo.csv"),
    )


def rodar(pedidos, tabela_original, tabela, prazo_max) -> dict:
    resultado = frete.simular(pedidos, tabela, prazo_max)
    base = frete.simular(pedidos, tabela_original, prazo_max)
    resumo_df = frete.resumo(resultado)
    transp_df = frete.por_transportadora(resultado)
    tabela_usada = tabela.dropna(how="all")
    return {
        "resultado": resultado,
        "resumo": resumo_df,
        "transportadoras": transp_df,
        "kpis": frete.kpis(resultado),
        "kpis_base": frete.kpis(base),
        "excel": frete.exportar_excel(resultado, resumo_df, transp_df, tabela_usada),
    }


# ---------------------------------------------------------------- barra lateral
with st.sidebar:
    st.header("Dados")
    fonte = st.radio("Fonte", ["Dados de exemplo", "Enviar arquivos"])
    if fonte == "Dados de exemplo":
        pedidos, tabela_original = carregar_exemplo()
        chave_editor = "exemplo"
    else:
        arq_pedidos = st.file_uploader("Pedidos (.csv ou .xlsx)", type=["csv", "xlsx"])
        arq_tabela = st.file_uploader("Tabela de frete (.csv ou .xlsx)", type=["csv", "xlsx"])
        if not (arq_pedidos and arq_tabela):
            st.info("Envie os dois arquivos para continuar.")
            st.stop()
        pedidos, tabela_original = ler_arquivo(arq_pedidos), ler_arquivo(arq_tabela)
        chave_editor = arq_tabela.name

    st.header("Regras")
    limitar = st.checkbox("Limitar prazo máximo")
    prazo_max = st.number_input("Prazo máximo (dias)", 1, 60, 7) if limitar else None

try:
    frete.validar_colunas(pedidos, frete.COLUNAS_PEDIDOS, "Pedidos")
    frete.validar_colunas(tabela_original, frete.COLUNAS_TABELA, "Tabela de frete")
except ValueError as erro:
    st.error(str(erro))
    st.stop()

# ------------------------------------------------------------------- conteúdo
st.title("🚚 Simulador de Frete")
st.caption(
    "Escolhe a transportadora mais barata para cada pedido, dentro do prazo. "
    "Os dados de exemplo são fictícios."
)

st.subheader("1. Tabela de frete")
st.caption(
    "Edite custos e prazos ou adicione linhas. A tabela original fica guardada "
    "como base para medir o impacto das mudanças."
)
origens = sorted(pedidos["origem"].dropna().astype(str).unique())
destinos = sorted(pedidos["destino_tipo"].dropna().astype(str).unique())
tabela = st.data_editor(
    tabela_original[frete.COLUNAS_TABELA],
    num_rows="dynamic",
    hide_index=True,
    key=f"editor_{chave_editor}",
    column_config={
        "transportadora": st.column_config.TextColumn("Transportadora", required=True),
        "origem": st.column_config.SelectboxColumn("Origem", options=origens, required=True),
        "destino_tipo": st.column_config.SelectboxColumn("Destino", options=destinos, required=True),
        "custo_base": st.column_config.NumberColumn(
            "Custo base (R$)", min_value=0.0, format="%.2f", required=True
        ),
        "custo_por_kg": st.column_config.NumberColumn(
            "Custo por kg (R$)", min_value=0.0, format="%.2f", required=True
        ),
        "prazo_dias": st.column_config.NumberColumn(
            "Prazo (dias)", min_value=1, step=1, required=True
        ),
    },
)

st.subheader("2. Simulação")
if st.button("▶ Rodar simulação", type="primary"):
    try:
        st.session_state["saida"] = rodar(pedidos, tabela_original, tabela, prazo_max)
    except ValueError as erro:
        st.session_state.pop("saida", None)
        st.error(str(erro))

saida = st.session_state.get("saida")
if not saida:
    st.info("Ajuste a tabela, se quiser, e clique em **Rodar simulação**.")
    st.stop()

k, kb = saida["kpis"], saida["kpis_base"]
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Pedidos", f"{k['pedidos']:,}".replace(",", "."))
c2.metric(
    "Custo total",
    brl(k["custo_total"]),
    delta=delta_brl(k["custo_total"], kb["custo_total"]),
    delta_color="inverse",
    help="Variação em relação à tabela original.",
)
c3.metric(
    "Custo médio por pedido",
    brl(k["custo_medio"]),
    delta=delta_brl(k["custo_medio"], kb["custo_medio"]),
    delta_color="inverse",
    help="Média ponderada: total de frete ÷ pedidos cobertos. "
    "Não é a média das médias dos grupos.",
)
c4.metric("Prazo médio (dias)", f"{k['prazo_medio']:.1f}".replace(".", ","))
c5.metric(
    "Sem cobertura",
    k["sem_cobertura"],
    delta=(k["sem_cobertura"] - kb["sem_cobertura"]) or None,
    delta_color="inverse",
)

aba_resumo, aba_transp, aba_pedidos = st.tabs(["Resumo", "Transportadoras", "Pedidos"])

with aba_resumo:
    resumo_df = saida["resumo"]
    st.dataframe(
        resumo_df,
        hide_index=True,
        column_config={
            "custo_total": st.column_config.NumberColumn("custo_total", format="R$ %.2f"),
            "custo_medio": st.column_config.NumberColumn("custo_medio", format="R$ %.2f"),
        },
    )
    st.caption(
        "A linha TOTAL é calculada a partir dos pedidos, não pela média das linhas acima."
    )
    grupos = resumo_df[resumo_df["origem"] != "TOTAL"].copy()
    grupos["grupo"] = grupos["origem"] + " → " + grupos["destino_tipo"]
    st.bar_chart(grupos.set_index("grupo")["custo_medio"], color=AZUL)

with aba_transp:
    st.dataframe(saida["transportadoras"], hide_index=True)
    st.bar_chart(saida["transportadoras"].set_index("transportadora")["pedidos"], color=AZUL)

with aba_pedidos:
    st.dataframe(saida["resultado"], hide_index=True)

st.download_button(
    "⬇ Baixar resultado (.xlsx)",
    data=saida["excel"],
    file_name="resultado_simulacao_frete.xlsx",
    mime=XLSX,
)
