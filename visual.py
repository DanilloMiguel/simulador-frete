"""Elementos visuais do app: formatação, estilo, cards e gráficos."""
from __future__ import annotations

import html
import json
from functools import lru_cache
from pathlib import Path

import altair as alt
import pandas as pd

import frete

AZUL = "#1F4E9C"
AZUL_CLARO = "#E8EEF7"
CINZA = "#4A5568"
CINZA_CLARO = "#E5E8EE"
GEOJSON_UFS = Path(__file__).parent / "data" / "brasil_ufs.geojson"

ESTILO = """
<style>
.topo {background: #1F4E9C; padding: 1.2rem 1.5rem; border-radius: 10px; margin-bottom: 1.2rem;}
.topo h1 {color: #FFFFFF !important; font-size: 1.7rem !important; margin: 0 !important; padding: 0 !important;}
.topo p {color: #DCE6F5 !important; margin: 0.3rem 0 0 0 !important; font-size: 0.95rem !important;}

/* --- Ranking: card Top 3 geral --- */
.rk-card {border-radius: 10px; overflow: hidden; margin-bottom: 10px; border-left: 5px solid #CCC;}
.rk-card.pos1 {border-left-color: #D4A017; background: linear-gradient(135deg, #FFF8E1 0%, #FFFFFF 60%);}
.rk-card.pos2 {border-left-color: #9E9E9E; background: linear-gradient(135deg, #F5F5F5 0%, #FFFFFF 60%);}
.rk-card.pos3 {border-left-color: #B87333; background: linear-gradient(135deg, #FBF0E8 0%, #FFFFFF 60%);}
.rk-head {padding: 10px 14px 2px; display: flex; align-items: center; gap: 8px;}
.rk-medal {font-size: 1.5rem;}
.rk-nome {font-weight: 700; font-size: 1.0rem; color: #1B2A41 !important;}
.rk-body {padding: 4px 14px 12px;}
.rk-valor {font-size: 1.6rem; font-weight: 800; color: #1F4E9C !important; margin: 2px 0;}
.rk-sub {font-size: 0.82rem; color: #4A5568 !important; line-height: 1.5;}
.rk-var {display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.78rem; font-weight: 600; margin-top: 4px;}
.rk-var.neg {background: #E8F5E9; color: #2E7D32 !important;}
.rk-var.pos {background: #FFEBEE; color: #C62828 !important;}

/* --- Ranking: painéis de região (dentro das abas) --- */
.rk-reg {background: #F8F9FB; border: 1px solid #E5E8EE; border-radius: 10px; padding: 12px; margin-bottom: 10px;}
.rk-reg-t {font-weight: 700; font-size: 0.95rem; color: #1F4E9C !important; margin-bottom: 8px; padding-bottom: 6px; border-bottom: 2px solid #1F4E9C;}
.rk-mini {display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid #EEE;}
.rk-mini:last-child {border-bottom: none;}
.rk-mini-pos {width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 0.82rem; color: #FFF !important; flex-shrink: 0;}
.rk-mini-pos.p1 {background: #D4A017;}
.rk-mini-pos.p2 {background: #9E9E9E;}
.rk-mini-pos.p3 {background: #B87333;}
.rk-mini-info {flex: 1; font-size: 0.84rem; color: #1F2933 !important; line-height: 1.4;}
.rk-mini-nome {font-weight: 600;}
.rk-mini-vals {color: #4A5568 !important;}
</style>
"""

CABECALHO = """
<div class="topo">
<h1>🚚 Simulador de Frete</h1>
<p>Escolhe a transportadora mais barata de cada pedido, dentro do prazo. Os dados de exemplo são fictícios.</p>
</div>
"""

MEDALHAS = {1: "🥇", 2: "🥈", 3: "🥉"}
COR_POSICAO = {1: "#63B95F", 2: "#F5C842", 3: "#F09A4A", 4: "#E07B6B"}  # verde, amarelo, laranja, vermelho


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
    "Valor de mercadoria (R$)": lambda v: num_br(v, 2),
    "Frete (R$)": lambda v: num_br(v, 2),
    "GRIS + Ad valorem (R$)": lambda v: num_br(v, 2),
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


# ------------------------------------------------------------- mapa de calor
def _mix(a: tuple, b: tuple, t: float) -> tuple:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _escala(serie: pd.Series):
    """Escala verde (menor) → branco → vermelho (maior), suavizada."""
    vmin, vmax = float(serie.min()), float(serie.max())
    verde, branco, vermelho = (99, 190, 123), (255, 255, 255), (248, 105, 107)

    def css(valor):
        if pd.isna(valor) or vmax == vmin:
            return ""
        t = (valor - vmin) / (vmax - vmin)
        cor = _mix(verde, branco, t / 0.5) if t < 0.5 else _mix(branco, vermelho, (t - 0.5) / 0.5)
        cor = _mix(cor, branco, 0.25)
        return "background-color: rgb({}, {}, {})".format(*cor)

    return css


def tabela_ranking_uf(por_uf: pd.DataFrame):
    """Transportadora mais barata de cada UF, com mapa de calor em frete e prazo."""
    t1 = por_uf[por_uf["posicao"] == 1].copy()
    t1["_ordem"] = t1["regiao"].map({r: i for i, r in enumerate(frete.ORDEM_REGIOES)})
    t1 = t1.sort_values(["_ordem", "uf"])
    tabela = t1[["regiao", "uf", "transportadora", "frete", "prazo", "var_pct"]].rename(
        columns={
            "regiao": "Região",
            "uf": "UF",
            "transportadora": "Transportadora + barata",
            "frete": "Menor frete (R$)",
            "prazo": "Prazo (dias)",
            "var_pct": "% Var Top1 vs Top2",
        }
    )
    tabela = tabela.reset_index(drop=True)
    estilo = tabela.style.format(
        {
            "Menor frete (R$)": lambda v: num_br(v, 2),
            "Prazo (dias)": lambda v: num_br(v, 1),
            "% Var Top1 vs Top2": lambda v: "-" if pd.isna(v) else num_br(v, 2) + "%",
        }
    )
    for coluna in ("Menor frete (R$)", "Prazo (dias)"):
        estilo = estilo.map(_escala(tabela[coluna]), subset=[coluna])
    return estilo


# ------------------------------------------------------------------ cards HTML
def cartao(linha: pd.Series) -> str:
    """Card grande de uma transportadora no ranking geral (Top 3)."""
    pos = int(linha["posicao"])
    medal = MEDALHAS.get(pos, "")
    nome = html.escape(str(linha["transportadora"]))

    if pd.notna(linha["var_pct"]):
        v = linha["var_pct"]
        cls = "neg" if v < 0 else "pos"
        sinal = "" if v < 0 else "+"
        var_html = f'<span class="rk-var {cls}">{sinal}{num_br(v, 1)}% vs Top {pos + 1}</span>'
    else:
        var_html = ""

    texto = (
        f'<div class="rk-card pos{pos}">'
        f'<div class="rk-head"><span class="rk-medal">{medal}</span>'
        f'<span class="rk-nome">{nome}</span></div>'
        f'<div class="rk-body">'
        f'<div class="rk-valor">R&#36; {num_br(linha["frete"], 2)}</div>'
        f'<div class="rk-sub">Prazo médio: {num_br(linha["prazo"], 1)} dias &nbsp;·&nbsp; '
        f'{num_br(linha["pedidos"], 0)} pedidos</div>'
        f'{var_html}</div></div>'
    )
    return texto


def mini_card_regiao(linha: pd.Series) -> str:
    """Card compacto de uma transportadora dentro do painel de região."""
    pos = int(linha["posicao"])
    nome = html.escape(str(linha["transportadora"]))
    return (
        f'<div class="rk-mini">'
        f'<div class="rk-mini-pos p{pos}">{pos}º</div>'
        f'<div class="rk-mini-info">'
        f'<div class="rk-mini-nome">{nome}</div>'
        f'<div class="rk-mini-vals">R&#36; {num_br(linha["frete"], 2)} &nbsp;·&nbsp; '
        f'{num_br(linha["prazo"], 1)} dias</div>'
        f'</div></div>'
    )


def painel_regiao(nome: str, ranking_regiao: pd.DataFrame) -> str:
    """Painel de Top 3 de uma região, para uso dentro de abas."""
    linhas = "".join(
        mini_card_regiao(linha)
        for _, linha in ranking_regiao.sort_values("posicao").iterrows()
    )
    return f'<div class="rk-reg"><div class="rk-reg-t">{html.escape(nome)}</div>{linhas}</div>'


def grafico_ranking_regiao(ranking_df: pd.DataFrame, regiao: str):
    """Barras horizontais comparando frete das transportadoras de uma região."""
    dados = ranking_df[ranking_df["regiao"] == regiao].copy()
    if dados.empty:
        return None
    dados["rotulo"] = dados["frete"].map(lambda v: f"R$ {num_br(v, 2)}")
    dados["cor"] = dados["posicao"].map({1: "#D4A017", 2: "#9E9E9E", 3: "#B87333"})

    limite = float(dados["frete"].max()) * 1.25 or 1.0
    base = alt.Chart(dados).encode(
        y=alt.Y(
            "transportadora:N",
            sort=alt.EncodingSortField(field="frete", order="ascending"),
            title=None,
            axis=alt.Axis(labelLimit=260, labelFontSize=12),
        ),
        x=alt.X("frete:Q", title="Frete médio (R$)", scale=alt.Scale(domain=[0, limite])),
    )
    cores = dict(zip(dados["transportadora"], dados["cor"]))
    barras = base.mark_bar(cornerRadiusEnd=4, size=26).encode(
        color=alt.Color(
            "transportadora:N",
            scale=alt.Scale(domain=list(cores.keys()), range=list(cores.values())),
            legend=None,
        ),
    )
    textos = base.mark_text(align="left", dx=5, color=CINZA, fontSize=12, fontWeight="bold").encode(
        text="rotulo:N",
    )
    return (
        (barras + textos)
        .properties(width="container", height=alt.Step(38))
        .configure_axis(gridColor=CINZA_CLARO, domain=False, labelColor=CINZA, titleColor=CINZA)
        .configure_view(stroke=None)
    )


# -------------------------------------------------------------------- gráficos
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


# --------------------------------------------------------- matriz de cobertura
def estilizar_matriz_cobertura(pivot: pd.DataFrame):
    """Heatmap de posição: verde (1ª), amarelo (2ª), laranja (3ª), vermelho (4+), cinza (sem)."""

    def _cor_posicao(val):
        if pd.isna(val):
            return "background-color: #E5E8EE; color: #999"
        pos = int(val)
        cor = COR_POSICAO.get(pos, "#D9534F")
        return f"background-color: {cor}; color: #FFF; font-weight: 700; text-align: center"

    def _formatar(val):
        if pd.isna(val):
            return "—"
        pos = int(val)
        return {1: "1º", 2: "2º", 3: "3º"}.get(pos, f"{pos}º")

    regioes = [c for c in pivot.columns if c != "transportadora"]
    estilo = pivot.style.map(_cor_posicao, subset=regioes)
    estilo = estilo.format({r: _formatar for r in regioes})
    return estilo


def legenda_cobertura() -> str:
    """HTML da legenda da matriz de cobertura."""
    itens = [
        ("#63B95F", "1º (mais barata)"),
        ("#F5C842", "2º"),
        ("#F09A4A", "3º"),
        ("#E07B6B", "4º+"),
        ("#E5E8EE", "Sem cobertura"),
    ]
    blocos = " ".join(
        f'<span style="display:inline-block;width:14px;height:14px;background:{cor};'
        f'border-radius:3px;vertical-align:middle;margin-right:3px"></span>'
        f'<span style="font-size:0.82rem;color:#4A5568;margin-right:14px">{txt}</span>'
        for cor, txt in itens
    )
    return f'<div style="margin:6px 0 10px">{blocos}</div>'


# --------------------------------------------------------- sensibilidade
def grafico_sensibilidade(dados: pd.DataFrame):
    """Gráfico de barras comparando pedidos atendidos antes × depois por transportadora."""
    base = alt.Chart(dados).encode(
        y=alt.Y("transportadora:N", sort="-x", title=None, axis=alt.Axis(labelLimit=260, labelFontSize=12)),
    )
    barras_antes = base.mark_bar(color=CINZA_CLARO, size=18).encode(
        x=alt.X("pedidos_antes:Q", title="Pedidos atendidos"),
    )
    barras_depois = base.mark_bar(color=AZUL, size=10).encode(
        x=alt.X("pedidos_depois:Q"),
    )
    return (
        (barras_antes + barras_depois)
        .properties(width="container", height=alt.Step(34))
        .configure_axis(gridColor=CINZA_CLARO, domain=False, labelColor=CINZA, titleColor=CINZA)
        .configure_view(stroke=None)
    )


# ----------------------------------------------------------- distribuição
@lru_cache(maxsize=1)
def _contornos_ufs() -> tuple:
    """Contorno simplificado das 27 UFs (data/brasil_ufs.geojson), lido uma vez."""
    return tuple(json.loads(GEOJSON_UFS.read_text(encoding="utf-8"))["features"])


def grafico_mapa_uf(dados: pd.DataFrame):
    """Mapa do Brasil por UF: cor = frete médio, tamanho da bolha = nº de pedidos.

    dados vem de frete.por_uf (colunas uf, pedidos, pct, frete_medio). UFs sem
    pedidos aparecem em cinza claro.
    """
    por_uf = dados.set_index("uf")
    base, com_dados = [], []
    for f in _contornos_ufs():
        uf = f["properties"]["uf"]
        props = dict(f["properties"])
        if uf in por_uf.index:
            linha = por_uf.loc[uf]
            props.update(
                pedidos=int(linha["pedidos"]),
                frete_medio=float(linha["frete_medio"]),
                frete_txt=brl(linha["frete_medio"]),
                pct_txt=num_br(linha["pct"], 1) + "%",
            )
        feature = {"type": "Feature", "properties": props, "geometry": f["geometry"]}
        base.append(feature)
        if uf in por_uf.index:
            com_dados.append(feature)

    fundo = (
        alt.Chart(alt.Data(values=base))
        .mark_geoshape(fill=CINZA_CLARO, stroke="white", strokeWidth=0.8)
    )
    tooltip = [
        alt.Tooltip("properties.nome:N", title="UF"),
        alt.Tooltip("properties.pedidos:Q", title="Pedidos"),
        alt.Tooltip("properties.pct_txt:N", title="% do total de pedidos"),
        alt.Tooltip("properties.frete_txt:N", title="Frete médio"),
    ]
    estados = (
        alt.Chart(alt.Data(values=com_dados))
        .mark_geoshape(stroke="white", strokeWidth=0.8)
        .encode(
            color=alt.Color(
                "properties.frete_medio:Q",
                title="Frete médio (R$)",
                scale=alt.Scale(range=["#DCE6F5", AZUL]),
                legend=alt.Legend(orient="right", format=",.0f", gradientLength=140),
            ),
            tooltip=tooltip,
        )
    )
    bolhas = (
        alt.Chart(alt.Data(values=[f["properties"] for f in com_dados]))
        .mark_circle(fill="#F7F9FC", fillOpacity=0.85, stroke=CINZA, strokeWidth=1)
        .encode(
            longitude="lon:Q",
            latitude="lat:Q",
            size=alt.Size(
                "pedidos:Q",
                title="Pedidos (tamanho da bolha)",
                scale=alt.Scale(range=[200, 1800]),
                legend=alt.Legend(
                    orient="right",
                    symbolFillColor=CINZA_CLARO,
                    symbolStrokeColor=CINZA,
                    symbolStrokeWidth=1.2,
                ),
            ),
            tooltip=[
                alt.Tooltip("nome:N", title="UF"),
                alt.Tooltip("pedidos:Q", title="Pedidos"),
                alt.Tooltip("pct_txt:N", title="% do total de pedidos"),
                alt.Tooltip("frete_txt:N", title="Frete médio"),
            ],
        )
    )
    rotulos = (
        alt.Chart(alt.Data(values=[f["properties"] for f in com_dados]))
        .mark_text(fontSize=9, fontWeight="bold", color="#1B2A41")
        .encode(longitude="lon:Q", latitude="lat:Q", text="uf:N")
    )
    return (
        alt.layer(fundo, estados, bolhas, rotulos)
        .project(type="mercator")
        .properties(width="container", height=470)
        .configure_view(stroke=None)
        .configure_legend(labelColor=CINZA, titleColor=CINZA)
    )


def grafico_faixas(dados: pd.DataFrame, titulo: str):
    """Barras verticais de quantidade de pedidos por faixa."""
    return (
        alt.Chart(dados)
        .mark_bar(color=AZUL, cornerRadiusEnd=3)
        .encode(
            x=alt.X("faixa:N", title=None, sort=None, axis=alt.Axis(labelAngle=-30, labelFontSize=11)),
            y=alt.Y("pedidos:Q", title="Pedidos"),
            tooltip=[
                alt.Tooltip("faixa:N", title="Faixa"),
                alt.Tooltip("pedidos:Q", title="Pedidos"),
                alt.Tooltip("custo_medio:Q", title="Frete médio (R$)", format=".2f"),
            ],
        )
        .properties(width="container", height=260, title=titulo)
        .configure_axis(gridColor=CINZA_CLARO, domain=False, labelColor=CINZA, titleColor=CINZA)
        .configure_view(stroke=None)
        .configure_title(color=CINZA, fontSize=14)
    )


def grafico_frete_sobre_valor(dados: pd.DataFrame):
    """Dispersão do % custo de frete (Frete ÷ Valor de mercadoria) × valor de mercadoria."""
    return (
        alt.Chart(dados)
        .mark_circle(color=AZUL, opacity=0.5, size=30)
        .encode(
            x=alt.X("valor_mercadoria:Q", title="Valor de mercadoria (R$)", axis=alt.Axis(format=",.0f")),
            y=alt.Y("pct_frete:Q", title="% custo de frete (Frete / Valor de mercadoria)"),
            tooltip=[
                alt.Tooltip("pedido_id:N", title="Pedido"),
                alt.Tooltip("valor_mercadoria:Q", title="Valor de mercadoria (R$)", format=",.2f"),
                alt.Tooltip("custo_frete:Q", title="Frete (R$)", format=",.2f"),
                alt.Tooltip("pct_frete:Q", title="% custo de frete", format=".1f"),
            ],
        )
        .properties(width="container", height=300, title="% custo de frete (Frete / Valor de mercadoria)")
        .configure_axis(gridColor=CINZA_CLARO, domain=False, labelColor=CINZA, titleColor=CINZA)
        .configure_view(stroke=None)
        .configure_title(color=CINZA, fontSize=14)
    )
