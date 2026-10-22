"""Lógica da simulação de frete.

Fica separada da interface (app.py) para poder ser testada sem Streamlit
e reaproveitada em scripts ou em tarefas agendadas.
"""
from __future__ import annotations

import io

import pandas as pd
from openpyxl.styles import Font, PatternFill

COLUNAS_PEDIDOS = ["pedido_id", "origem", "destino_tipo", "uf", "peso_kg", "valor_mercadoria"]
# Nome antigo da coluna de valor, ainda aceito em arquivos enviados.
COLUNA_VALOR_LEGADA = "valor_pedido"
COLUNAS_TABELA = [
    "transportadora",
    "origem",
    "regiao",
    "destino_tipo",
    "custo_base",
    "custo_por_kg",
    "prazo_dias",
]
SEM_COBERTURA = "Sem cobertura"
CHAVE = ["origem", "regiao", "destino_tipo"]

# A região do pedido é derivada da UF de destino.
REGIAO_POR_UF = {
    **dict.fromkeys(["ES", "MG", "RJ", "SP"], "Sudeste"),
    **dict.fromkeys(["PR", "RS", "SC"], "Sul"),
    **dict.fromkeys(["DF", "GO", "MS", "MT"], "Centro-Oeste"),
    **dict.fromkeys(["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"], "Nordeste"),
    **dict.fromkeys(["AC", "AM", "AP", "PA", "RO", "RR", "TO"], "Norte"),
}
ORDEM_REGIOES = ["Sudeste", "Sul", "Centro-Oeste", "Nordeste", "Norte"]

# Nomes amigáveis para exibição (tela e Excel). Internamente as colunas
# mantêm os nomes originais.
ROTULOS = {
    "pedido_id": "Pedido",
    "origem": "Origem",
    "regiao": "Região",
    "destino_tipo": "Destino",
    "uf": "UF",
    "peso_kg": "Peso (kg)",
    "valor_mercadoria": "Valor de mercadoria (R$)",
    "transportadora": "Transportadora",
    "custo_frete": "Frete (R$)",
    "prazo_dias": "Prazo (dias)",
    "pedidos": "Pedidos",
    "cobertos": "Cobertos",
    "sem_cobertura": "Sem cobertura",
    "custo_total": "Custo total (R$)",
    "custo_medio": "Custo médio (R$)",
    "prazo_medio": "Prazo médio (dias)",
    "participacao_pct": "Participação (%)",
}


def rotular(df: pd.DataFrame) -> pd.DataFrame:
    """Troca os nomes internos das colunas pelos nomes de exibição."""
    return df.rename(columns=ROTULOS)


def normalizar_pedidos(pedidos: pd.DataFrame) -> pd.DataFrame:
    """Aceita o nome antigo da coluna de valor (valor_pedido) como valor_mercadoria."""
    if COLUNA_VALOR_LEGADA in pedidos.columns and "valor_mercadoria" not in pedidos.columns:
        return pedidos.rename(columns={COLUNA_VALOR_LEGADA: "valor_mercadoria"})
    return pedidos


def validar_colunas(df: pd.DataFrame, esperadas: list[str], nome: str) -> None:
    faltando = [c for c in esperadas if c not in df.columns]
    if faltando:
        raise ValueError(f"{nome}: faltam as colunas {', '.join(faltando)}.")


def _preparar(
    df: pd.DataFrame, colunas: list[str], numericas: list[str], nome: str
) -> pd.DataFrame:
    """Seleciona as colunas, converte números e recusa células vazias ou inválidas."""
    validar_colunas(df, colunas, nome)
    out = df[colunas].dropna(how="all").copy()
    for col in numericas:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    if out.isna().any().any():
        raise ValueError(f"{nome}: há células vazias ou com valor inválido.")
    if (out[numericas] < 0).any().any():
        raise ValueError(f"{nome}: há valores negativos em {', '.join(numericas)}.")
    for col in colunas:
        if col not in numericas:
            out[col] = out[col].astype(str).str.strip()
    return out


def _preparar_entradas(
    pedidos: pd.DataFrame, tabela: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    ped = _preparar(
        normalizar_pedidos(pedidos), COLUNAS_PEDIDOS, ["peso_kg", "valor_mercadoria"], "Pedidos"
    )
    tab = _preparar(
        tabela, COLUNAS_TABELA, ["custo_base", "custo_por_kg", "prazo_dias"], "Tabela de frete"
    )
    if ped["pedido_id"].duplicated().any():
        raise ValueError("Pedidos: há pedido_id repetido.")
    ped["uf"] = ped["uf"].str.upper()
    ped["regiao"] = ped["uf"].map(REGIAO_POR_UF)
    desconhecidas = sorted(ped.loc[ped["regiao"].isna(), "uf"].unique())
    if desconhecidas:
        raise ValueError("Pedidos: UF não reconhecida: " + ", ".join(desconhecidas) + ".")
    return ped, tab


def _opcoes(ped: pd.DataFrame, tab: pd.DataFrame, prazo_max: float | None) -> pd.DataFrame:
    opcoes = ped.merge(tab, on=CHAVE, how="inner")
    opcoes["custo_frete"] = (opcoes["custo_base"] + opcoes["custo_por_kg"] * opcoes["peso_kg"]).round(2)
    if prazo_max is not None:
        opcoes = opcoes[opcoes["prazo_dias"] <= prazo_max]
    return opcoes


def calcular_opcoes(
    pedidos: pd.DataFrame, tabela: pd.DataFrame, prazo_max: float | None = None
) -> pd.DataFrame:
    """Todas as opções de frete de cada pedido (uma linha por pedido e transportadora).

    Custo = custo_base + custo_por_kg * peso_kg.
    """
    ped, tab = _preparar_entradas(pedidos, tabela)
    return _opcoes(ped, tab, prazo_max)


def simular(
    pedidos: pd.DataFrame, tabela: pd.DataFrame, prazo_max: float | None = None
) -> pd.DataFrame:
    """Escolhe, para cada pedido, a transportadora mais barata dentro do prazo.

    Empate de custo é decidido pelo menor prazo. Pedido sem nenhuma opção
    vira "Sem cobertura".
    """
    ped, tab = _preparar_entradas(pedidos, tabela)
    opcoes = _opcoes(ped, tab, prazo_max)
    vencedoras = (
        opcoes.sort_values(["pedido_id", "custo_frete", "prazo_dias", "transportadora"])
        .drop_duplicates("pedido_id")[["pedido_id", "transportadora", "custo_frete", "prazo_dias"]]
    )
    resultado = ped.merge(vencedoras, on="pedido_id", how="left")
    resultado["transportadora"] = resultado["transportadora"].fillna(SEM_COBERTURA)
    return resultado


def ranking(opcoes: pd.DataFrame, por: list[str], top: int = 3) -> pd.DataFrame:
    """Top N transportadoras mais baratas em cada grupo (por exemplo, por UF).

    Cada transportadora é avaliada sobre os mesmos pedidos do grupo, aplicando a
    sua tabela a cada um deles. Os valores são médias ponderadas:
    frete = soma do frete ÷ pedidos do grupo (e prazo, idem), nunca a média das
    médias de subgrupos. var_pct compara o frete com o do colocado seguinte
    (Top 1 vs Top 2, Top 2 vs Top 3) e fica vazio para o último da lista.
    """
    por = list(por)
    if not por:
        opcoes = opcoes.assign(escopo="Todos")
        por = ["escopo"]
    g = opcoes.groupby(por + ["transportadora"], as_index=False).agg(
        pedidos=("pedido_id", "count"),
        custo_total=("custo_frete", "sum"),
        prazo_total=("prazo_dias", "sum"),
    )
    g["frete"] = g["custo_total"] / g["pedidos"]
    g["prazo"] = g["prazo_total"] / g["pedidos"]
    g = g.sort_values(por + ["frete", "prazo", "transportadora"]).reset_index(drop=True)
    g["posicao"] = g.groupby(por).cumcount() + 1
    g = g[g["posicao"] <= top].copy()
    seguinte = g.groupby(por)["frete"].shift(-1)
    g["var_pct"] = (g["frete"] / seguinte - 1) * 100
    return g.drop(columns=["custo_total", "prazo_total"]).reset_index(drop=True)


def kpis(resultado: pd.DataFrame) -> dict:
    """Indicadores calculados sempre a partir dos totais (média ponderada).

    custo_medio = soma do frete / pedidos cobertos. Não é a média das médias
    de cada grupo, que daria o mesmo peso a grupos de tamanhos diferentes.
    """
    cobertos = int(resultado["custo_frete"].notna().sum())
    custo_total = float(resultado["custo_frete"].sum())
    prazo_total = float(resultado["prazo_dias"].sum())
    return {
        "pedidos": len(resultado),
        "cobertos": cobertos,
        "sem_cobertura": len(resultado) - cobertos,
        "custo_total": custo_total,
        "custo_medio": custo_total / cobertos if cobertos else float("nan"),
        "prazo_medio": prazo_total / cobertos if cobertos else float("nan"),
    }


def resumo(resultado: pd.DataFrame, por: tuple[str, ...] = ("origem", "destino_tipo")) -> pd.DataFrame:
    """Resumo por grupo + linha TOTAL calculada a partir dos dados brutos."""
    por = list(por)
    linhas = []
    for chave, grupo in resultado.groupby(por, sort=True):
        chave = chave if isinstance(chave, tuple) else (chave,)
        linhas.append({**dict(zip(por, chave)), **kpis(grupo)})
    total = {**{c: "" for c in por}, **kpis(resultado)}
    total[por[0]] = "TOTAL"
    linhas.append(total)
    return pd.DataFrame(linhas).round({"custo_total": 2, "custo_medio": 2, "prazo_medio": 2})


def por_transportadora(resultado: pd.DataFrame) -> pd.DataFrame:
    cobertos = resultado[resultado["transportadora"] != SEM_COBERTURA]
    df = cobertos.groupby("transportadora", as_index=False).agg(
        pedidos=("pedido_id", "count"),
        custo_total=("custo_frete", "sum"),
        prazo_total=("prazo_dias", "sum"),
    )
    df["participacao_pct"] = df["pedidos"] / df["pedidos"].sum() * 100
    df["custo_medio"] = df["custo_total"] / df["pedidos"]
    df["prazo_medio"] = df["prazo_total"] / df["pedidos"]
    df = df.drop(columns="prazo_total").sort_values("pedidos", ascending=False)
    return df.round(2).reset_index(drop=True)


def matriz_cobertura(opcoes: pd.DataFrame) -> pd.DataFrame:
    """Matriz transportadora × região: posição de cada transportadora em cada região.

    Retorna um DataFrame com colunas [transportadora, <região1>, <região2>, ...].
    Valores: 1 = mais barata, 2 = segunda, 3 = terceira, NaN = sem cobertura.
    """
    r = ranking(opcoes, ["regiao"], top=99)
    pivot = r.pivot_table(index="transportadora", columns="regiao", values="posicao", aggfunc="first")
    pivot = pivot.reindex(columns=ORDEM_REGIOES).reset_index()
    pivot = pivot.sort_values(
        [r for r in ORDEM_REGIOES if r in pivot.columns],
        na_position="last",
    )
    return pivot


def matriz_cobertura_uf(opcoes: pd.DataFrame) -> pd.DataFrame:
    """Matriz transportadora × UF: posição de cada transportadora em cada UF."""
    r = ranking(opcoes, ["uf"], top=99)
    ufs_ordenadas = sorted(r["uf"].unique(), key=lambda u: (ORDEM_REGIOES.index(REGIAO_POR_UF[u]), u))
    pivot = r.pivot_table(index="transportadora", columns="uf", values="posicao", aggfunc="first")
    pivot = pivot.reindex(columns=ufs_ordenadas).reset_index()
    return pivot


def sensibilidade(
    pedidos: pd.DataFrame,
    tabela: pd.DataFrame,
    transportadora: str,
    variacao_pct: float,
    prazo_max: float | None = None,
) -> dict:
    """Simula o impacto de ajustar os custos de uma transportadora em X%.

    Retorna dict com resultado da simulação ajustada e métricas de comparação.
    """
    tabela_ajustada = tabela.copy()
    mascara = tabela_ajustada["transportadora"] == transportadora
    tabela_ajustada.loc[mascara, "custo_base"] *= 1 + variacao_pct / 100
    tabela_ajustada.loc[mascara, "custo_por_kg"] *= 1 + variacao_pct / 100
    return simular(pedidos, tabela_ajustada, prazo_max)


def comparar_cenarios(
    base: pd.DataFrame, ajustado: pd.DataFrame
) -> dict:
    """Compara dois resultados de simulação e retorna métricas de diferença."""
    k_base = kpis(base)
    k_ajust = kpis(ajustado)

    # Pedidos que trocaram de transportadora
    merged = base[["pedido_id", "transportadora"]].merge(
        ajustado[["pedido_id", "transportadora"]],
        on="pedido_id",
        suffixes=("_antes", "_depois"),
    )
    trocaram = merged[merged["transportadora_antes"] != merged["transportadora_depois"]]

    return {
        "kpis_base": k_base,
        "kpis_ajustado": k_ajust,
        "delta_custo": k_ajust["custo_total"] - k_base["custo_total"],
        "delta_medio": k_ajust["custo_medio"] - k_base["custo_medio"],
        "pedidos_trocaram": len(trocaram),
        "trocas": trocaram,
    }


def distribuicao_faixas(resultado: pd.DataFrame, coluna: str, faixas: list[tuple[float, float, str]]) -> pd.DataFrame:
    """Distribui os pedidos em faixas customizadas de uma coluna numérica."""
    cobertos = resultado[resultado["transportadora"] != SEM_COBERTURA].copy()
    cobertos["faixa"] = pd.cut(
        cobertos[coluna],
        bins=[f[0] for f in faixas] + [faixas[-1][1]],
        labels=[f[2] for f in faixas],
        include_lowest=True,
        right=True,
    )
    return cobertos.groupby("faixa", observed=False).agg(
        pedidos=("pedido_id", "count"),
        custo_medio=("custo_frete", "mean"),
    ).reset_index()


def por_uf(resultado: pd.DataFrame) -> pd.DataFrame:
    """Demanda e frete médio por UF de destino, só com pedidos cobertos.

    frete_medio = soma do frete da UF ÷ pedidos da UF (média ponderada, nunca a
    média das médias de subgrupos). pct = participação da UF no total de pedidos.
    """
    cobertos = resultado[resultado["transportadora"] != SEM_COBERTURA]
    df = cobertos.groupby(["uf", "regiao"], as_index=False).agg(
        pedidos=("pedido_id", "count"),
        custo_total=("custo_frete", "sum"),
    )
    df["frete_medio"] = df["custo_total"] / df["pedidos"]
    df["pct"] = df["pedidos"] / df["pedidos"].sum() * 100
    return df.sort_values("pedidos", ascending=False).reset_index(drop=True)


def pct_custo_frete(resultado: pd.DataFrame) -> pd.DataFrame:
    """% custo de frete de cada pedido coberto: Frete ÷ Valor de mercadoria × 100."""
    cobertos = resultado[resultado["transportadora"] != SEM_COBERTURA]
    df = cobertos[["pedido_id", "valor_mercadoria", "custo_frete"]].copy()
    df["pct_frete"] = df["custo_frete"] / df["valor_mercadoria"] * 100
    return df


def indicadores_pct_frete(pct: pd.DataFrame) -> dict:
    """Média, mediana e máximo do % custo de frete por pedido, mais o valor ponderado.

    media é a média simples dos percentuais de cada pedido (cada pedido pesa igual).
    ponderado = soma do frete ÷ soma do valor de mercadoria (pedidos maiores pesam mais).
    """
    if pct.empty:
        nan = float("nan")
        return {"media": nan, "mediana": nan, "maximo": nan, "ponderado": nan}
    return {
        "media": float(pct["pct_frete"].mean()),
        "mediana": float(pct["pct_frete"].median()),
        "maximo": float(pct["pct_frete"].max()),
        "ponderado": float(pct["custo_frete"].sum() / pct["valor_mercadoria"].sum() * 100),
    }


def gerar_template_excel() -> bytes:
    """Gera um .xlsx com as duas abas modelo (Pedidos e Tabela de frete).

    Cada aba tem o cabeçalho correto, 2 linhas de exemplo preenchidas e uma
    aba 'Instruções' explicando cada coluna.
    """
    exemplo_pedidos = pd.DataFrame([
        ["PED-001", "CD Leste", "Capital", "SP", 2.5, 150.00],
        ["PED-002", "Loja", "Interior", "MG", 1.2, 89.90],
    ], columns=COLUNAS_PEDIDOS)

    exemplo_tabela = pd.DataFrame([
        ["Transportadora A", "CD Leste", "Sudeste", "Capital", 8.50, 1.20, 3],
        ["Transportadora A", "CD Leste", "Sudeste", "Interior", 10.00, 1.50, 5],
    ], columns=COLUNAS_TABELA)

    instrucoes = pd.DataFrame([
        ["Pedidos", "pedido_id", "Identificador único do pedido (texto ou número)"],
        ["Pedidos", "origem", "De onde sai o pedido (ex: CD Leste, Loja, CD Oeste)"],
        ["Pedidos", "destino_tipo", "Capital ou Interior"],
        ["Pedidos", "uf", "Sigla da UF de destino (ex: SP, RJ, MG)"],
        ["Pedidos", "peso_kg", "Peso do pedido em quilos (número)"],
        ["Pedidos", "valor_mercadoria", "Valor de mercadoria do pedido em R$ (número)"],
        ["Tabela de frete", "transportadora", "Nome da transportadora"],
        ["Tabela de frete", "origem", "Origem da coleta (deve bater com a do pedido)"],
        ["Tabela de frete", "regiao", "Sudeste, Sul, Centro-Oeste, Nordeste ou Norte"],
        ["Tabela de frete", "destino_tipo", "Capital ou Interior (deve bater com a do pedido)"],
        ["Tabela de frete", "custo_base", "Custo fixo por envio em R$ (número)"],
        ["Tabela de frete", "custo_por_kg", "Custo variável por kg em R$ (número)"],
        ["Tabela de frete", "prazo_dias", "Prazo de entrega em dias úteis (número inteiro)"],
    ], columns=["Aba", "Coluna", "Descrição"])

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as escritor:
        exemplo_pedidos.to_excel(escritor, sheet_name="Pedidos", index=False)
        exemplo_tabela.to_excel(escritor, sheet_name="Tabela de frete", index=False)
        instrucoes.to_excel(escritor, sheet_name="Instruções", index=False)
        for aba in escritor.book.worksheets:
            aba.freeze_panes = "A2"
            for celula in aba[1]:
                celula.font = Font(bold=True, color="FFFFFF")
                celula.fill = PatternFill("solid", fgColor="1F4E9C")
            for coluna in aba.columns:
                largura = max(len(str(c.value)) if c.value is not None else 0 for c in coluna)
                aba.column_dimensions[coluna[0].column_letter].width = min(largura + 3, 50)
    return buffer.getvalue()


def exportar_excel(
    resultado: pd.DataFrame,
    resumo_df: pd.DataFrame,
    transportadoras: pd.DataFrame,
    tabela: pd.DataFrame,
) -> bytes:
    """Gera o .xlsx de saída. A aba Parametros guarda a tabela usada na rodada."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as escritor:
        rotular(resultado).to_excel(escritor, sheet_name="Resultado", index=False)
        rotular(resumo_df).to_excel(escritor, sheet_name="Resumo", index=False)
        rotular(transportadoras).to_excel(escritor, sheet_name="Transportadoras", index=False)
        # Parametros mantém os nomes originais: a aba pode ser reaproveitada como entrada.
        tabela.to_excel(escritor, sheet_name="Parametros", index=False)
        for aba in escritor.book.worksheets:
            aba.freeze_panes = "A2"
            for celula in aba[1]:
                celula.font = Font(bold=True, color="FFFFFF")
                celula.fill = PatternFill("solid", fgColor="1F4E9C")
            for linha in aba.iter_rows(min_row=2):
                if linha[0].value == "TOTAL":
                    for celula in linha:
                        celula.font = Font(bold=True)
            for coluna in aba.columns:
                if str(coluna[0].value).endswith("(R$)"):
                    for celula in coluna[1:]:
                        celula.number_format = "#,##0.00"
                largura = max(len(str(c.value)) if c.value is not None else 0 for c in coluna)
                aba.column_dimensions[coluna[0].column_letter].width = min(largura + 2, 40)
    return buffer.getvalue()
