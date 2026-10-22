"""Simulador de frete: app Streamlit (dados fictícios de exemplo)."""
from pathlib import Path

import pandas as pd
import streamlit as st

import frete
import visual as vz

DATA = Path(__file__).parent / "data"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

st.set_page_config(page_title="Simulador de Frete", page_icon="🚚", layout="wide")


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


def card(coluna, titulo: str, valor, **kwargs) -> None:
    with coluna.container(border=True):
        st.metric(titulo, valor, **kwargs)


# ------------------------------------------------------------ aba: simulação
def secao_simulacao(pedidos, tabela_original, tabela, prazo_max) -> None:
    if st.button("▶ Rodar simulação", type="primary"):
        try:
            st.session_state["saida"] = rodar(pedidos, tabela_original, tabela, prazo_max)
        except ValueError as erro:
            st.session_state.pop("saida", None)
            st.error(str(erro))

    saida = st.session_state.get("saida")
    if not saida:
        st.info("Ajuste a tabela, se quiser, e clique em **Rodar simulação**.")
        return

    k, kb = saida["kpis"], saida["kpis_base"]
    c1, c2, c3, c4, c5 = st.columns(5)
    card(c1, "Pedidos", vz.num_br(k["pedidos"], 0))
    card(
        c2,
        "Custo total",
        vz.brl(k["custo_total"]),
        delta=vz.delta_brl(k["custo_total"], kb["custo_total"]),
        delta_color="inverse",
        help="Variação em relação à tabela original.",
    )
    card(
        c3,
        "Custo médio por pedido",
        vz.brl(k["custo_medio"]),
        delta=vz.delta_brl(k["custo_medio"], kb["custo_medio"]),
        delta_color="inverse",
        help="Média ponderada: total de frete ÷ pedidos cobertos. "
        "Não é a média das médias dos grupos.",
    )
    card(c4, "Prazo médio", vz.num_br(k["prazo_medio"], 1) + " dias")
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
        st.dataframe(vz.estilizar(resumo_df, destacar_total=True), hide_index=True)
        st.caption("A linha TOTAL é calculada a partir dos pedidos, não pela média das linhas acima.")
        grupos = resumo_df[resumo_df["origem"] != "TOTAL"].copy()
        if not grupos.empty:
            grupos["grupo"] = grupos["origem"] + " → " + grupos["destino_tipo"]
            grupos["texto"] = grupos["custo_medio"].map(vz.brl)
            st.altair_chart(
                vz.grafico_barras(grupos, "grupo", "custo_medio", "texto", "Custo médio por pedido (R$)")
            )

    with aba_transp:
        transp = saida["transportadoras"]
        if transp.empty:
            st.info("Nenhum pedido foi atendido com as regras atuais.")
        else:
            st.dataframe(
                vz.estilizar(transp),
                hide_index=True,
                column_config={
                    "Participação (%)": st.column_config.ProgressColumn(
                        "Participação (%)", min_value=0, max_value=100, format="%.1f"
                    )
                },
            )
            transp = transp.copy()
            transp["texto"] = transp["participacao_pct"].map(lambda v: vz.num_br(v, 1) + "%")
            st.altair_chart(
                vz.grafico_barras(
                    transp, "transportadora", "participacao_pct", "texto", "Participação nos pedidos (%)"
                )
            )

    with aba_pedidos:
        st.dataframe(vz.estilizar(saida["resultado"]), hide_index=True)

    st.download_button(
        "⬇ Baixar resultado (.xlsx)",
        data=saida["excel"],
        file_name="resultado_simulacao_frete.xlsx",
        mime=XLSX,
    )


# --------------------------------------------------------- aba: ranking regional
def secao_ranking(pedidos, tabela) -> None:
    try:
        opcoes = frete.calcular_opcoes(pedidos, tabela)
    except ValueError as erro:
        st.error(str(erro))
        return
    if opcoes.empty:
        st.info("Nenhuma transportadora da tabela atende os pedidos.")
        return

    f1, f2, f3 = st.columns(3)
    transportadoras = sorted(opcoes["transportadora"].unique())
    selecionadas = f1.multiselect("Transportadora", transportadoras, default=transportadoras)
    origem = f2.selectbox("Origem da coleta", ["Todas"] + sorted(opcoes["origem"].unique()))
    regioes_presentes = set(opcoes["regiao"])
    regiao = f3.selectbox(
        "Região de destino",
        ["Todas"] + [r for r in frete.ORDEM_REGIOES if r in regioes_presentes],
    )

    filtrado = opcoes[opcoes["transportadora"].isin(selecionadas)]
    if origem != "Todas":
        filtrado = filtrado[filtrado["origem"] == origem]
    if regiao != "Todas":
        filtrado = filtrado[filtrado["regiao"] == regiao]
    if filtrado.empty:
        st.info("Nenhuma opção de frete com esses filtros.")
        return

    st.caption(f"Top 3 considerando {vz.num_br(filtrado['pedido_id'].nunique(), 0)} pedidos no filtro atual.")
    geral = frete.ranking(filtrado, [])
    for coluna, (_, linha) in zip(st.columns(3), geral.iterrows()):
        coluna.markdown(vz.cartao(linha), unsafe_allow_html=True)

    col_esq, col_dir = st.columns([5, 6])
    por_uf = frete.ranking(filtrado, ["regiao", "uf"])
    por_regiao = frete.ranking(filtrado, ["regiao"])

    with col_esq:
        st.markdown("**Detalhamento: ranking de frete por UF**")
        st.dataframe(vz.tabela_ranking_uf(por_uf), hide_index=True, height=620)

    with col_dir:
        st.markdown("**Top 3 por região**")
        regioes = [r for r in frete.ORDEM_REGIOES if r in set(por_regiao["regiao"])]
        for i in range(0, len(regioes), 2):
            for coluna, nome in zip(st.columns(2), regioes[i : i + 2]):
                coluna.markdown(
                    vz.painel_regiao(nome, por_regiao[por_regiao["regiao"] == nome]),
                    unsafe_allow_html=True,
                )

    st.caption(
        "Cada transportadora é aplicada aos mesmos pedidos de cada grupo. Frete e prazo (LT) são "
        "médias ponderadas (total ÷ pedidos), não médias das médias. A variação compara cada "
        "colocado com o seguinte. O prazo da tabela por UF é o da transportadora mais barata."
    )


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
st.markdown(vz.ESTILO + vz.CABECALHO, unsafe_allow_html=True)

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
        "regiao": st.column_config.SelectboxColumn(
            "Região", options=frete.ORDEM_REGIOES, required=True
        ),
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

aba_simulacao, aba_ranking = st.tabs(["Simulação de pedidos", "Ranking por região"])
with aba_simulacao:
    secao_simulacao(pedidos, tabela_original, tabela, prazo_max)
with aba_ranking:
    secao_ranking(pedidos, tabela)
