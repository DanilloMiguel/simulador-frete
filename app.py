"""Simulador de frete: app Streamlit (dados fictícios de exemplo)."""
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

import frete

DATA = Path(__file__).parent / "data"
AZUL = "#1F4E9C"
AZUL_CLARO = "#E8EEF7"
CINZA = "#4A5568"
CINZA_CLARO = "#E5E8EE"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

st.set_page_config(page_title="Simulador de Frete", page_icon="🚚", layout="wide")

ESTILO = """
<style>
.topo {background: #1F4E9C; padding: 1.2rem 1.5rem; border-radius: 10px; margin-bottom: 1.2rem;}
.topo h1 {color: #FFFFFF !important; font-size: 1.7rem !important; margin: 0 !important; padding: 0 !important;}
.topo p {color: #DCE6F5 !important; margin: 0.3rem 0 0 0 !important; font-size: 0.95rem !important;}
</style>
"""

CABECALHO = """
<div class="topo">
<h1>🚚 Simulador de Frete</h1>
<p>Escolhe a transportadora mais barata de cada pedido, dentro do prazo. Os dados de exemplo são fictícios.</p>
</div>
"""


# ------------------------------------------------------------------ formatação
def num_br(valor: float, casas: int = 2) -> str:
    """Número no padrão brasileiro: 1.234,56."""
    if pd.isna(valor):
        return "-"
    return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def brl(valor: float) -> str:
    return "-" if pd.isna(valor) else "R$ " + num_br(valor, 2)


def delta_brl(atual: float, base: float) -> str | None:
    dif = atual - base
    if abs(dif) < 0.005:
        return None
    return ("-" if dif < 0 else "+") + brl(abs(dif))


FORMATOS = {
    "Peso (kg)": lambda v: num_br(v, 2),
    "Valor do pedido (R$)": lambda v: num_br(v, 2),
    "Frete (R$)": lambda v: num_br(v, 2),
    "Prazo (dias)": lambda v: num_br(v, 0),
    "Custo total (R$)": lambda v: num_br(v, 2),
    "Custo médio (R$)": lambda v: num_br(v, 2),
    "Prazo médio (dias)": lambda v: num_br(v, 1),
}


def estilizar(df: pd.DataFrame, destacar_total: bool = False):
    """Rótulos amigáveis, números no padrão brasileiro e linha TOTAL em destaque."""
    tabela = frete.rotular(df)
    estilo = tabela.style.format({c: f for c, f in FORMATOS.items() if c in tabela.columns})
    if destacar_total:
        estilo = estilo.apply(
            lambda linha: [
                f"font-weight: 700; background-color: {AZUL_CLARO}" if linha["Origem"] == "TOTAL" else ""
                for _ in linha
            ],
            axis=1,
        )
    return estilo


def grafico_barras(df: pd.DataFrame, categoria: str, valor: str, rotulo: str, titulo: str):
    """Barras horizontais em azul, com o valor escrito na ponta de cada barra."""
    limite = float(df[valor].max()) * 1.2 or 1.0
    base = alt.Chart(df).encode(
        y=alt.Y(
            f"{categoria}:N",
            sort="-x",
            title=None,
            axis=alt.Axis(labelLimit=260, labelFontSize=12),
        ),
        x=alt.X(
            f"{valor}:Q",
            title=titulo,
            scale=alt.Scale(domain=[0, limite]),
            axis=alt.Axis(grid=True, tickCount=5),
        ),
    )
    barras = base.mark_bar(color=AZUL, cornerRadiusEnd=3, size=22)
    textos = base.mark_text(align="left", dx=5, color=CINZA, fontSize=12).encode(text=f"{rotulo}:N")
    return (
        (barras + textos)
        .properties(width="container", height=alt.Step(34))
        .configure_axis(gridColor=CINZA_CLARO, domain=False, labelColor=CINZA, titleColor=CINZA)
        .configure_view(stroke=None)
    )


def card(coluna, titulo: str, valor, **kwargs) -> None:
    with coluna.container(border=True):
        st.metric(titulo, valor, **kwargs)


# ----------------------------------------------------------------------- dados
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
st.markdown(ESTILO + CABECALHO, unsafe_allow_html=True)

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
    height=320,
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
card(c1, "Pedidos", num_br(k["pedidos"], 0))
card(
    c2,
    "Custo total",
    brl(k["custo_total"]),
    delta=delta_brl(k["custo_total"], kb["custo_total"]),
    delta_color="inverse",
    help="Variação em relação à tabela original.",
)
card(
    c3,
    "Custo médio por pedido",
    brl(k["custo_medio"]),
    delta=delta_brl(k["custo_medio"], kb["custo_medio"]),
    delta_color="inverse",
    help="Média ponderada: total de frete ÷ pedidos cobertos. "
    "Não é a média das médias dos grupos.",
)
card(c4, "Prazo médio", num_br(k["prazo_medio"], 1) + " dias")
card(
    c5,
    "Sem cobertura",
    k["sem_cobertura"],
    delta=(k["sem_cobertura"] - kb["sem_cobertura"]) or None,
    delta_color="inverse",
    help="Pedidos para os quais nenhuma transportadora atende dentro das regras.",
)

aba_resumo, aba_transp, aba_pedidos = st.tabs(["Resumo", "Transportadoras", "Pedidos"])

with aba_resumo:
    resumo_df = saida["resumo"]
    st.dataframe(estilizar(resumo_df, destacar_total=True), hide_index=True)
    st.caption("A linha TOTAL é calculada a partir dos pedidos, não pela média das linhas acima.")
    grupos = resumo_df[resumo_df["origem"] != "TOTAL"].copy()
    if not grupos.empty:
        grupos["grupo"] = grupos["origem"] + " → " + grupos["destino_tipo"]
        grupos["texto"] = grupos["custo_medio"].map(brl)
        st.altair_chart(
            grafico_barras(grupos, "grupo", "custo_medio", "texto", "Custo médio por pedido (R$)")
        )

with aba_transp:
    transp = saida["transportadoras"]
    if transp.empty:
        st.info("Nenhum pedido foi atendido com as regras atuais.")
    else:
        st.dataframe(
            estilizar(transp),
            hide_index=True,
            column_config={
                "Participação (%)": st.column_config.ProgressColumn(
                    "Participação (%)", min_value=0, max_value=100, format="%.1f"
                )
            },
        )
        transp = transp.copy()
        transp["texto"] = transp["participacao_pct"].map(lambda v: num_br(v, 1) + "%")
        st.altair_chart(
            grafico_barras(
                transp, "transportadora", "participacao_pct", "texto", "Participação nos pedidos (%)"
            )
        )

with aba_pedidos:
    st.dataframe(estilizar(saida["resultado"]), hide_index=True)

st.download_button(
    "⬇ Baixar resultado (.xlsx)",
    data=saida["excel"],
    file_name="resultado_simulacao_frete.xlsx",
    mime=XLSX,
)
