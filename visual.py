"""Elementos visuais do app: formatação, estilo, cards e gráficos."""
from __future__ import annotations

import html

import altair as alt
import pandas as pd

import frete

AZUL = "#1F4E9C"
AZUL_CLARO = "#E8EEF7"
CINZA = "#4A5568"
CINZA_CLARO = "#E5E8EE"

ESTILO = """
<style>
.topo {background: #1F4E9C; padding: 1.2rem 1.5rem; border-radius: 10px; margin-bottom: 1.2rem;}
.topo h1 {color: #FFFFFF !important; font-size: 1.7rem !important; margin: 0 !important; padding: 0 !important;}
.topo p {color: #DCE6F5 !important; margin: 0.3rem 0 0 0 !important; font-size: 0.95rem !important;}
.med {background: #E8EEF7; border: 1px solid #D3DCEB; border-radius: 8px; overflow: hidden; margin-bottom: 8px;}
.med-t {background: #1B2A41; color: #FFFFFF !important; font-weight: 700; font-size: 0.9rem; text-align: center; padding: 6px 8px;}
.med-c {color: #1F2933 !important; font-size: 0.85rem; line-height: 1.55; text-align: center; padding: 6px 10px;}
.painel {background: #F1F3F6; border-radius: 10px; padding: 8px; margin-bottom: 12px;}
.painel-t {background: #1B2A41; color: #FFFFFF !important; font-weight: 700; text-align: center; padding: 7px; border-radius: 8px; margin-bottom: 8px;}
</style>
"""

CABECALHO = """
<div class="topo">
<h1>🚚 Simulador de Frete</h1>
<p>Escolhe a transportadora mais barata de cada pedido, dentro do prazo. Os dados de exemplo são fictícios.</p>
</div>
"""

MEDALHAS = {1: "🥇", 2: "🥈", 3: "🥉"}


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
    """Card de uma transportadora no ranking (medalha, frete, prazo e variação)."""
    if pd.notna(linha["var_pct"]):
        variacao = f"<b>% Var vs Top{int(linha['posicao']) + 1}:</b> {num_br(linha['var_pct'], 1)}%"
    else:
        variacao = "&nbsp;"
    texto = (
        '<div class="med">'
        f'<div class="med-t">{MEDALHAS[int(linha["posicao"])]} {html.escape(str(linha["transportadora"]))}</div>'
        f'<div class="med-c"><b>Frete:</b> {brl(linha["frete"])} &nbsp;·&nbsp; '
        f'<b>LT:</b> {num_br(linha["prazo"], 1)} dias<br>{variacao}</div>'
        "</div>"
    )
    # "$" vira entidade para o markdown não tratá-lo como fórmula.
    return texto.replace("$", "&#36;")


def painel_regiao(nome: str, ranking_regiao: pd.DataFrame) -> str:
    cartoes = "".join(cartao(linha) for _, linha in ranking_regiao.sort_values("posicao").iterrows())
    return f'<div class="painel"><div class="painel-t">{html.escape(nome)}</div>{cartoes}</div>'


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
