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

    # --- Filtros ---
    f1, f2, f3 = st.columns(3)
    transportadoras = sorted(opcoes["transportadora"].unique())
    selecionadas = f1.multiselect("Transportadora", transportadoras, default=transportadoras)
    origem = f2.selectbox("Origem da coleta", ["Todas"] + sorted(opcoes["origem"].unique()))
    regioes_presentes = set(opcoes["regiao"])
    regiao_filtro = f3.selectbox(
        "Região de destino",
        ["Todas"] + [r for r in frete.ORDEM_REGIOES if r in regioes_presentes],
    )

    filtrado = opcoes[opcoes["transportadora"].isin(selecionadas)]
    if origem != "Todas":
        filtrado = filtrado[filtrado["origem"] == origem]
    if regiao_filtro != "Todas":
        filtrado = filtrado[filtrado["regiao"] == regiao_filtro]
    if filtrado.empty:
        st.info("Nenhuma opção de frete com esses filtros.")
        return

    n_pedidos = filtrado["pedido_id"].nunique()
    st.caption(f"Top 3 considerando {vz.num_br(n_pedidos, 0)} pedidos no filtro atual.")

    # --- Top 3 geral com cards redesenhados ---
    geral = frete.ranking(filtrado, [])
    colunas_top = st.columns(min(3, len(geral)))
    for coluna, (_, linha) in zip(colunas_top, geral.iterrows()):
        coluna.markdown(vz.cartao(linha), unsafe_allow_html=True)

    st.divider()

    # --- Detalhamento: abas por região + tabela UF ---
    por_uf = frete.ranking(filtrado, ["regiao", "uf"])
    por_regiao = frete.ranking(filtrado, ["regiao"])
    regioes = [r for r in frete.ORDEM_REGIOES if r in set(por_regiao["regiao"])]

    sub_ranking, sub_uf = st.tabs(["🏆 Top 3 por região", "📊 Ranking por UF"])

    with sub_ranking:
        if len(regioes) > 1:
            abas_regiao = st.tabs(regioes)
            for aba, nome in zip(abas_regiao, regioes):
                with aba:
                    dados_regiao = por_regiao[por_regiao["regiao"] == nome]
                    col_p, col_g = st.columns([3, 5])
                    with col_p:
                        st.markdown(vz.painel_regiao(nome, dados_regiao), unsafe_allow_html=True)
                        n_ped_reg = filtrado[filtrado["regiao"] == nome]["pedido_id"].nunique()
                        st.caption(f"{vz.num_br(n_ped_reg, 0)} pedidos nessa região")
                    with col_g:
                        grafico = vz.grafico_ranking_regiao(por_regiao, nome)
                        if grafico:
                            st.altair_chart(grafico)
        else:
            nome = regioes[0]
            dados_regiao = por_regiao[por_regiao["regiao"] == nome]
            col_p, col_g = st.columns([3, 5])
            with col_p:
                st.markdown(vz.painel_regiao(nome, dados_regiao), unsafe_allow_html=True)
            with col_g:
                grafico = vz.grafico_ranking_regiao(por_regiao, nome)
                if grafico:
                    st.altair_chart(grafico)

    with sub_uf:
        st.markdown("**Transportadora mais barata de cada UF**")
        st.caption("Mapa de calor: verde = menor valor, vermelho = maior. O prazo é o da transportadora mais barata daquela UF.")
        st.dataframe(vz.tabela_ranking_uf(por_uf), hide_index=True, height=620)

    st.caption(
        "Cada transportadora é aplicada aos mesmos pedidos de cada grupo. Frete e prazo (LT) são "
        "médias ponderadas (total ÷ pedidos), não médias das médias. A variação compara cada "
        "colocado com o seguinte."
    )


# -------------------------------------------------- aba: cobertura e competitividade
def secao_cobertura(pedidos, tabela) -> None:
    try:
        opcoes = frete.calcular_opcoes(pedidos, tabela)
    except ValueError as erro:
        st.error(str(erro))
        return
    if opcoes.empty:
        st.info("Nenhuma transportadora da tabela atende os pedidos.")
        return

    st.markdown("**Matriz de posição: Transportadora × Região**")
    st.caption(
        "Cada célula mostra a posição da transportadora na região "
        "(1º = mais barata considerando todos os pedidos daquela região). "
        "Média ponderada, não média das médias."
    )
    st.markdown(vz.legenda_cobertura(), unsafe_allow_html=True)

    matriz_reg = frete.matriz_cobertura(opcoes)
    st.dataframe(vz.estilizar_matriz_cobertura(matriz_reg), hide_index=True, width="stretch")

    with st.expander("🔍 Ver detalhamento por UF"):
        st.caption("Posição de cada transportadora em cada UF (1º = mais barata naquela UF).")
        matriz_uf = frete.matriz_cobertura_uf(opcoes)
        st.dataframe(
            vz.estilizar_matriz_cobertura(matriz_uf),
            hide_index=True,
            width="stretch",
            height=min(len(matriz_uf) * 38 + 40, 500),
        )

    # Resumo textual
    st.markdown("**Resumo de cobertura**")
    n_transp = opcoes["transportadora"].nunique()
    n_regioes = opcoes["regiao"].nunique()
    n_ufs = opcoes["uf"].nunique()
    col1, col2, col3 = st.columns(3)
    with col1.container(border=True):
        st.metric("Transportadoras ativas", n_transp)
    with col2.container(border=True):
        st.metric("Regiões cobertas", f"{n_regioes} / 5")
    with col3.container(border=True):
        st.metric("UFs cobertas", f"{n_ufs} / 27")

    # Lacunas
    todas_ufs = set(frete.REGIAO_POR_UF.keys())
    ufs_cobertas = set(opcoes["uf"].unique())
    sem = todas_ufs - ufs_cobertas
    if sem:
        st.warning(f"UFs sem cobertura: {', '.join(sorted(sem))}")


# -------------------------------------------------- aba: análise de sensibilidade
def secao_sensibilidade(pedidos, tabela, prazo_max) -> None:
    try:
        base = frete.simular(pedidos, tabela, prazo_max)
    except ValueError as erro:
        st.error(str(erro))
        return

    transportadoras = sorted(tabela["transportadora"].dropna().unique())
    if not transportadoras:
        st.info("Nenhuma transportadora na tabela.")
        return

    st.caption(
        "Ajuste o custo de uma transportadora em ±30% e veja quantos pedidos mudam de mão e o impacto no custo total."
    )

    col_t, col_s = st.columns([2, 3])
    transp = col_t.selectbox("Transportadora para ajustar", transportadoras, key="sens_transp")
    variacao = col_s.slider(
        "Variação no custo (%)",
        min_value=-30,
        max_value=30,
        value=0,
        step=1,
        key="sens_slider",
        help="Negativo = desconto, positivo = aumento. Vale para o frete inteiro: valor da faixa, R$/kg e GRIS + Ad valorem.",
    )

    if variacao == 0:
        st.info("Mova o slider para simular um cenário de ajuste de custo.")
        return

    ajustado = frete.sensibilidade(pedidos, tabela, transp, variacao, prazo_max)
    comp = frete.comparar_cenarios(base, ajustado)

    sinal = "📉" if variacao < 0 else "📈"
    st.markdown(f"**{sinal} Cenário: {transp} com {variacao:+d}% no custo**")

    c1, c2, c3, c4 = st.columns(4)
    with c1.container(border=True):
        st.metric(
            "Custo total",
            vz.brl(comp["kpis_ajustado"]["custo_total"]),
            delta=vz.delta_brl(comp["kpis_ajustado"]["custo_total"], comp["kpis_base"]["custo_total"]),
            delta_color="inverse",
        )
    with c2.container(border=True):
        st.metric(
            "Custo médio",
            vz.brl(comp["kpis_ajustado"]["custo_medio"]),
            delta=vz.delta_brl(comp["kpis_ajustado"]["custo_medio"], comp["kpis_base"]["custo_medio"]),
            delta_color="inverse",
        )
    with c3.container(border=True):
        st.metric("Pedidos que trocaram", comp["pedidos_trocaram"])
    with c4.container(border=True):
        st.metric(
            "Sem cobertura",
            comp["kpis_ajustado"]["sem_cobertura"],
            delta=(comp["kpis_ajustado"]["sem_cobertura"] - comp["kpis_base"]["sem_cobertura"]) or None,
            delta_color="inverse",
        )

    if comp["pedidos_trocaram"] > 0:
        trocas = comp["trocas"].copy()
        trocas.columns = ["Pedido", "Antes", "Depois"]
        with st.expander(f"📋 Ver {comp['pedidos_trocaram']} pedido(s) que trocaram de transportadora"):
            st.dataframe(trocas, hide_index=True, width="stretch")

    # Comparar distribuição antes × depois
    st.markdown("**Distribuição de pedidos por transportadora: antes × depois**")
    dist_antes = base.groupby("transportadora")["pedido_id"].count().reset_index()
    dist_antes.columns = ["transportadora", "pedidos_antes"]
    dist_depois = ajustado.groupby("transportadora")["pedido_id"].count().reset_index()
    dist_depois.columns = ["transportadora", "pedidos_depois"]
    dist = dist_antes.merge(dist_depois, on="transportadora", how="outer").fillna(0)
    dist = dist[dist["transportadora"] != frete.SEM_COBERTURA].sort_values("pedidos_antes", ascending=False)
    if not dist.empty:
        st.altair_chart(vz.grafico_sensibilidade(dist))
        st.caption("Barra clara = antes do ajuste · Barra escura = depois do ajuste")


# -------------------------------------------------- aba: distribuição dos pedidos
def secao_distribuicao(pedidos, tabela, prazo_max) -> None:
    try:
        resultado = frete.simular(pedidos, tabela, prazo_max)
    except ValueError as erro:
        st.error(str(erro))
        return

    cobertos = resultado[resultado["transportadora"] != frete.SEM_COBERTURA].copy()
    if cobertos.empty:
        st.info("Nenhum pedido coberto para analisar a distribuição.")
        return

    st.caption("Visão do perfil da base de pedidos: como se distribuem por região, peso, valor de mercadoria e representatividade do frete.")

    # Distribuição por região e UF
    st.markdown("**Pedidos por região**")
    por_uf = frete.por_uf(resultado)
    por_regiao = cobertos.groupby("regiao")["pedido_id"].count().reset_index()
    por_regiao.columns = ["regiao", "pedidos"]
    por_regiao["pct"] = por_regiao["pedidos"] / por_regiao["pedidos"].sum() * 100
    por_regiao = por_regiao.sort_values("pedidos", ascending=False)

    col_g, col_t = st.columns([5, 4])
    with col_g:
        st.altair_chart(vz.grafico_mapa_uf(por_uf))
        st.caption(
            "Cor do estado = frete médio por pedido (soma do frete ÷ nº de pedidos da UF). "
            "Tamanho da bolha = nº de pedidos, ou seja, onde está a maior demanda."
        )
    with col_t:
        por_regiao_display = por_regiao.copy()
        por_regiao_display["pct"] = por_regiao_display["pct"].round(1)
        por_regiao_display.columns = ["Região", "Pedidos", "% do total"]
        st.dataframe(por_regiao_display, hide_index=True, width="stretch")

        # Custo médio por região
        custo_regiao = cobertos.groupby("regiao").agg(
            custo_medio=("custo_frete", "mean"),
            prazo_medio=("prazo_dias", "mean"),
        ).round(2).reset_index()
        custo_regiao.columns = ["Região", "Frete médio (R$)", "Prazo médio (dias)"]
        st.dataframe(custo_regiao, hide_index=True, width="stretch")

    st.divider()

    # Faixas de peso e valor lado a lado
    col_peso, col_valor = st.columns(2)

    with col_peso:
        faixas_peso = [
            (0, 2, "0–2 kg"), (2, 5, "2–5 kg"), (5, 10, "5–10 kg"),
            (10, 20, "10–20 kg"), (20, 50, "20–50 kg"), (50, 999, "50+ kg"),
        ]
        dist_peso = frete.distribuicao_faixas(resultado, "peso_kg", faixas_peso)
        st.altair_chart(vz.grafico_faixas(dist_peso, "Pedidos por faixa de peso"))

    with col_valor:
        faixas_valor = [
            (0, 50, "0–50"), (50, 100, "50–100"), (100, 200, "100–200"),
            (200, 500, "200–500"), (500, 1000, "500–1k"), (1000, 99999, "1k+"),
        ]
        dist_valor = frete.distribuicao_faixas(resultado, "valor_mercadoria", faixas_valor)
        st.altair_chart(vz.grafico_faixas(dist_valor, "Pedidos por faixa de valor de mercadoria (R$)"))

    st.divider()

    # % custo de frete = Frete / Valor de mercadoria
    st.markdown("**Representatividade do frete**")
    pct = frete.pct_custo_frete(resultado)
    ind = frete.indicadores_pct_frete(pct)
    col_sc, col_kpi = st.columns([5, 3])
    with col_sc:
        st.altair_chart(vz.grafico_frete_sobre_valor(pct))
    with col_kpi:
        with st.container(border=True):
            st.metric("% custo de frete (média)", f"{vz.num_br(ind['media'], 1)}%")
        with st.container(border=True):
            st.metric("% custo de frete (mediana)", f"{vz.num_br(ind['mediana'], 1)}%")
        with st.container(border=True):
            st.metric("% custo de frete (máximo)", f"{vz.num_br(ind['maximo'], 1)}%")
        st.caption(
            "**Como é calculado:** % custo de frete = Frete ÷ Valor de mercadoria × 100, "
            "pedido a pedido, usando o frete da transportadora escolhida na simulação.  \n"
            "**Média:** soma dos percentuais de cada pedido ÷ nº de pedidos. É uma média simples "
            "dos percentuais, não ponderada pelo valor.  \n"
            "**Mediana:** o percentual do pedido que fica no meio da distribuição.  \n"
            "**Máximo:** o maior percentual entre os pedidos.  \n"
            f"Para comparar, o percentual ponderado (soma do frete ÷ soma do valor de mercadoria) "
            f"é {vz.num_br(ind['ponderado'], 1)}%."
        )
        st.caption(
            "Pedidos com frete alto relativo ao valor de mercadoria são candidatos a negociação de custo."
        )


# ---------------------------------------------------------------- barra lateral
with st.sidebar:
    st.header("Dados")
    fonte = st.radio("Fonte", ["Dados de exemplo", "Enviar arquivos"])
    if fonte == "Dados de exemplo":
        pedidos, tabela_original = carregar_exemplo()
        chave_editor = "exemplo"
    else:
        st.download_button(
            "📥 Baixar planilha modelo",
            data=frete.gerar_template_excel(),
            file_name="modelo_simulador_frete.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        st.caption("Baixe, preencha e envie abaixo ↓")
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

pedidos = frete.normalizar_pedidos(pedidos)  # aceita o nome antigo valor_pedido

try:
    frete.validar_colunas(pedidos, frete.COLUNAS_PEDIDOS, "Pedidos")
    # Cria as colunas opcionais que faltarem (uf/regiao, faixas de peso, % GRIS + ADV).
    tabela_original = frete.normalizar_tabela(tabela_original)
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
with st.expander("Como a tabela é lida"):
    st.markdown(
        "- **UF ou região:** a linha com UF vale só para aquela UF. A linha só com região vale para "
        "todas as UFs da região. Se existirem as duas para a mesma transportadora, origem e destino, "
        "**vale a da UF**.\n"
        "- **Faixa de peso:** o pedido cai na menor faixa cujo *Peso até* comporta o peso. "
        "*Peso até* vazio = sem limite.\n"
        "- **Frete** = Valor da faixa + R\\$/kg × (peso − *Peso de*) + GRIS + Ad valorem (%) × valor de mercadoria. "
        "Com faixas, deixe o R\\$/kg em 0 e use-o só na linha de excedente (ex.: *Peso de* 30, *Peso até* vazio).\n"
        "- **GRIS + Ad valorem:** digite 0,30 para 0,30%.\n"
        "- Células vazias aparecem como *None*."
    )
gris = pd.to_numeric(tabela_original["gris_adv_pct"], errors="coerce")
if ((gris > 0) & (gris < 0.05)).any():
    st.warning(
        "Alguns valores de GRIS + Ad valorem estão abaixo de 0,05%. Se a célula estava formatada "
        "como % no Excel, 0,30% vira 0,003 no arquivo. Digite 0,30 para 0,30%."
    )
ufs = sorted(frete.REGIAO_POR_UF, key=lambda u: (frete.ORDEM_REGIOES.index(frete.REGIAO_POR_UF[u]), u))
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
        "uf": st.column_config.SelectboxColumn(
            "UF", options=ufs, help="Vazio = vale para todas as UFs da região."
        ),
        "regiao": st.column_config.SelectboxColumn(
            "Região", options=frete.ORDEM_REGIOES, help="Use quando a linha vale para a região inteira."
        ),
        "destino_tipo": st.column_config.SelectboxColumn("Destino", options=destinos, required=True),
        "peso_min": st.column_config.NumberColumn(
            "Peso de (kg)", min_value=0.0, format="%.3f", help="Início da faixa. Vazio = 0."
        ),
        "peso_max": st.column_config.NumberColumn(
            "Peso até (kg)", min_value=0.0, format="%.3f", help="Fim da faixa. Vazio = sem limite."
        ),
        "custo_base": st.column_config.NumberColumn(
            "Valor da faixa (R$)", min_value=0.0, format="%.2f", required=True,
            help="Valor da faixa de peso ou custo fixo por envio.",
        ),
        "custo_por_kg": st.column_config.NumberColumn(
            "R$/kg acima do Peso de", min_value=0.0, format="%.2f", required=True,
            help="Com faixas, use 0. Na linha de excedente, o R$ por kg excedente.",
        ),
        "gris_adv_pct": st.column_config.NumberColumn(
            "GRIS + Ad valorem (%)", min_value=0.0, format="%.2f",
            help="Percentual sobre o valor de mercadoria: 0,30 = 0,30%. Vazio = 0.",
        ),
        "prazo_dias": st.column_config.NumberColumn(
            "Prazo (dias)", min_value=1, step=1, required=True
        ),
    },
)

aba_simulacao, aba_ranking, aba_cobertura, aba_sensibilidade, aba_distrib = st.tabs(
    ["Simulação de pedidos", "Ranking por região", "Cobertura e Competitividade", "Análise de Sensibilidade", "Distribuição dos Pedidos"]
)
with aba_simulacao:
    secao_simulacao(pedidos, tabela_original, tabela, prazo_max)
with aba_ranking:
    secao_ranking(pedidos, tabela)
with aba_cobertura:
    secao_cobertura(pedidos, tabela)
with aba_sensibilidade:
    secao_sensibilidade(pedidos, tabela, prazo_max)
with aba_distrib:
    secao_distribuicao(pedidos, tabela, prazo_max)
