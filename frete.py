"""Lógica da simulação de frete.

Fica separada da interface (app.py) para poder ser testada sem Streamlit
e reaproveitada em scripts ou em tarefas agendadas.
"""
from __future__ import annotations

import io

import numpy as np
import pandas as pd
from openpyxl.styles import Font, PatternFill

COLUNAS_PEDIDOS = ["pedido_id", "origem", "destino_tipo", "uf", "peso_kg", "valor_mercadoria"]
# Nome antigo da coluna de valor, ainda aceito em arquivos enviados.
COLUNA_VALOR_LEGADA = "valor_pedido"
COLUNAS_TABELA = [
    "transportadora",
    "origem",
    "uf",
    "regiao",
    "destino_tipo",
    "peso_min",
    "peso_max",
    "custo_base",
    "custo_por_kg",
    "gris_adv_pct",
    "prazo_dias",
]
COLUNAS_TABELA_OBRIGATORIAS = [
    "transportadora",
    "origem",
    "destino_tipo",
    "custo_base",
    "custo_por_kg",
    "prazo_dias",
]
# Colunas opcionais e o valor usado quando a coluna não existe no arquivo.
# uf/regiao: pelo menos uma das duas precisa existir e vir preenchida em cada linha.
# peso_max vazio = sem limite de peso.
PADRAO_OPCIONAIS = {
    "uf": None,
    "regiao": None,
    "peso_min": 0.0,
    "peso_max": np.nan,
    "gris_adv_pct": 0.0,
}
SEM_COBERTURA = "Sem cobertura"
# Maior intervalo aceito entre o fim de uma faixa e o início da seguinte (ex.: 0,250 → 0,251).
# Acima disso, a tabela é recusada: faltaria uma faixa e o pedido cairia na faixa de cima.
TOLERANCIA_FAIXA_KG = 0.01
# Uma "rota" da tabela: cada pedido é comparado com as rotas da sua origem, UF e destino.
ROTA = ["transportadora", "origem", "uf", "destino_tipo"]

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
    "gris_adv_valor": "GRIS + Ad valorem (R$)",
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


def normalizar_tabela(tabela: pd.DataFrame) -> pd.DataFrame:
    """Confere as colunas obrigatórias e cria as opcionais que faltarem.

    Arquivos no formato antigo (só regiao, sem faixa de peso e sem %) continuam
    válidos: ganham peso_min 0, peso_max vazio (sem limite) e gris_adv_pct 0.
    """
    validar_colunas(tabela, COLUNAS_TABELA_OBRIGATORIAS, "Tabela de frete")
    if "uf" not in tabela.columns and "regiao" not in tabela.columns:
        raise ValueError("Tabela de frete: inclua a coluna uf, a coluna regiao ou as duas.")
    out = tabela.copy()
    for col, padrao in PADRAO_OPCIONAIS.items():
        if col not in out.columns:
            out[col] = padrao
    return out[COLUNAS_TABELA]


def _vazio(serie: pd.Series) -> pd.Series:
    return serie.isna() | serie.astype(str).str.strip().eq("")


def _exemplo_linhas(mascara: pd.Series, limite: int = 5) -> str:
    """Números das linhas como aparecem no Excel (cabeçalho na linha 1)."""
    linhas = [str(i + 2) for i in mascara[mascara].index[:limite]]
    return ", ".join(linhas) + ("…" if mascara.sum() > limite else "")


def preparar_tabela(tabela: pd.DataFrame) -> pd.DataFrame:
    """Valida a tabela de frete e devolve uma linha por UF.

    - Linha com uf vale só para aquela UF; linha só com regiao vale para todas as
      UFs da região. Se a mesma transportadora/origem/destino tiver linha da UF e
      linha da região, vale a da UF (a da região é descartada para aquela UF).
    - peso_min/peso_max definem a faixa de peso; peso_max vazio = sem limite.
    - gris_adv_pct é o % de GRIS + Ad valorem sobre o valor de mercadoria
      (0,30 significa 0,30%). Vazio = 0.
    """
    nome = "Tabela de frete"
    tab = normalizar_tabela(tabela).reset_index(drop=True)
    tab["_linha"] = tab.index + 2  # linha no Excel (cabeçalho na linha 1)
    # Linhas totalmente vazias (por exemplo, adicionadas no editor e não preenchidas).
    preenchidas = ~tab[COLUNAS_TABELA_OBRIGATORIAS + ["uf", "regiao", "peso_max"]].apply(_vazio).all(axis=1)
    tab = tab[preenchidas].copy()

    for col in ["transportadora", "origem", "destino_tipo", "uf", "regiao"]:
        tab[col] = tab[col].where(_vazio(tab[col]).eq(False)).astype(object)
        tab.loc[tab[col].notna(), col] = tab.loc[tab[col].notna(), col].astype(str).str.strip()

    texto_vazio = tab[["transportadora", "origem", "destino_tipo"]].isna().any(axis=1)
    if texto_vazio.any():
        raise ValueError(f"{nome}: há células vazias em transportadora, origem ou destino_tipo "
                         f"(linhas {_exemplo_linhas(texto_vazio)}).")

    numericas = ["custo_base", "custo_por_kg", "prazo_dias", "peso_min", "peso_max", "gris_adv_pct"]
    for col in numericas:
        bruto = tab[col]
        tab[col] = pd.to_numeric(bruto, errors="coerce")
        invalido = tab[col].isna() & ~_vazio(bruto)
        if invalido.any():
            raise ValueError(f"{nome}: valor inválido na coluna {col} (linhas {_exemplo_linhas(invalido)}). "
                             "Use só números, sem R$ ou %.")
    obrig_vazio = tab[["custo_base", "custo_por_kg", "prazo_dias"]].isna().any(axis=1)
    if obrig_vazio.any():
        raise ValueError(f"{nome}: há células vazias em custo_base, custo_por_kg ou prazo_dias "
                         f"(linhas {_exemplo_linhas(obrig_vazio)}). Se não houver custo, use 0.")
    tab["peso_min"] = tab["peso_min"].fillna(0.0)
    tab["gris_adv_pct"] = tab["gris_adv_pct"].fillna(0.0)
    negativo = (tab[numericas].fillna(0) < 0).any(axis=1)
    if negativo.any():
        raise ValueError(f"{nome}: há valores negativos (linhas {_exemplo_linhas(negativo)}).")
    tab["peso_max"] = tab["peso_max"].fillna(np.inf)
    faixa_invertida = tab["peso_min"] > tab["peso_max"]
    if faixa_invertida.any():
        raise ValueError(f"{nome}: peso_min maior que peso_max (linhas {_exemplo_linhas(faixa_invertida)}).")

    # UF e região
    tab["uf"] = tab["uf"].str.upper()
    regioes = {r.lower(): r for r in ORDEM_REGIOES}
    tab["regiao"] = tab["regiao"].map(lambda r: regioes.get(r.lower(), r) if isinstance(r, str) else r)
    sem_local = tab["uf"].isna() & tab["regiao"].isna()
    if sem_local.any():
        raise ValueError(f"{nome}: preencha uf ou regiao (linhas {_exemplo_linhas(sem_local)}).")
    uf_ruim = tab["uf"].notna() & ~tab["uf"].isin(list(REGIAO_POR_UF))
    if uf_ruim.any():
        raise ValueError(f"{nome}: UF não reconhecida: {', '.join(sorted(tab.loc[uf_ruim, 'uf'].unique()))}.")
    regiao_ruim = tab["regiao"].notna() & ~tab["regiao"].isin(ORDEM_REGIOES)
    if regiao_ruim.any():
        raise ValueError(f"{nome}: região não reconhecida: {', '.join(sorted(tab.loc[regiao_ruim, 'regiao'].unique()))}. "
                         f"Use {', '.join(ORDEM_REGIOES)}.")
    conflito = tab["uf"].notna() & tab["regiao"].notna() & (tab["uf"].map(REGIAO_POR_UF) != tab["regiao"])
    if conflito.any():
        raise ValueError(f"{nome}: UF e região não combinam (linhas {_exemplo_linhas(conflito)}).")

    tab["nivel"] = np.where(tab["uf"].notna(), "uf", "regiao")
    ufs_da_regiao = {r: [u for u, rr in REGIAO_POR_UF.items() if rr == r] for r in ORDEM_REGIOES}
    tab["uf"] = [[u] if isinstance(u, str) else ufs_da_regiao[r] for u, r in zip(tab["uf"], tab["regiao"])]
    tab = tab.explode("uf", ignore_index=True)
    tab["regiao"] = tab["uf"].map(REGIAO_POR_UF)

    # A linha da UF tem prioridade sobre a da região para a mesma rota.
    com_uf = tab.loc[tab["nivel"] == "uf", ROTA].drop_duplicates()
    marcada = tab.merge(com_uf.assign(_tem_uf=1), on=ROTA, how="left")["_tem_uf"].notna().to_numpy()
    tab = tab[(tab["nivel"] == "uf").to_numpy() | ~marcada].drop(columns="nivel").reset_index(drop=True)

    def _rota_txt(linha) -> str:
        return f"{linha['transportadora']}, {linha['origem']}, {linha['uf']}, {linha['destino_tipo']}"

    def _kg(valor) -> str:
        return "sem limite" if np.isinf(valor) else f"{valor:g} kg".replace(".", ",")

    repetida = tab.duplicated(ROTA + ["peso_max"], keep=False)
    if repetida.any():
        ex = tab[repetida].iloc[0]
        mesmas = tab[repetida & (tab[ROTA + ["peso_max"]] == ex[ROTA + ["peso_max"]]).all(axis=1)]
        linhas = " e ".join(str(n) for n in sorted(mesmas["_linha"].unique()))
        raise ValueError(f"{nome}: há linhas repetidas para a mesma rota e faixa de peso "
                         f"({_rota_txt(ex)}, faixa até {_kg(ex['peso_max'])}): linhas {linhas}.")

    # Faixa faltando: a primeira faixa começa em 0 e cada faixa encosta no fim da anterior.
    ordenada = tab.sort_values(ROTA + ["peso_max"])
    anterior = ordenada.groupby(ROTA)[["peso_max", "_linha"]].shift()
    buraco = (ordenada["peso_min"] - anterior["peso_max"].fillna(0)) > TOLERANCIA_FAIXA_KG
    if buraco.any():
        ex = ordenada[buraco].iloc[0]
        ant = anterior[buraco].iloc[0]
        if pd.isna(ant["_linha"]):
            onde = f"primeira faixa na linha {int(ex['_linha'])}"
            de = 0.0
        else:
            onde = f"linhas {int(ant['_linha'])} e {int(ex['_linha'])}"
            de = ant["peso_max"]
        raise ValueError(f"{nome}: falta faixa de peso entre {_kg(de)} e {_kg(ex['peso_min'])} "
                         f"({_rota_txt(ex)}; {onde}). Cada UF precisa do bloco completo de faixas, começando em 0.")
    tab["prazo_dias"] = tab["prazo_dias"].astype(float)
    return tab[COLUNAS_TABELA]


def _preparar_entradas(
    pedidos: pd.DataFrame, tabela: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    ped = _preparar(
        normalizar_pedidos(pedidos), COLUNAS_PEDIDOS, ["peso_kg", "valor_mercadoria"], "Pedidos"
    )
    tab = preparar_tabela(tabela)
    if ped["pedido_id"].duplicated().any():
        raise ValueError("Pedidos: há pedido_id repetido.")
    ped["uf"] = ped["uf"].str.upper()
    ped["regiao"] = ped["uf"].map(REGIAO_POR_UF)
    desconhecidas = sorted(ped.loc[ped["regiao"].isna(), "uf"].unique())
    if desconhecidas:
        raise ValueError("Pedidos: UF não reconhecida: " + ", ".join(desconhecidas) + ".")
    return ped, tab


def _opcoes(ped: pd.DataFrame, tab: pd.DataFrame, prazo_max: float | None) -> pd.DataFrame:
    """Uma linha por pedido × transportadora que atende a rota e o peso.

    Faixa: a de menor peso_max que comporta o peso do pedido. Assim um peso que cai
    entre duas faixas (ex.: 0,2505 entre 0,250 e 0,251) vai para a faixa de cima.
    Pedido mais pesado que a maior faixa não é atendido, a não ser que exista uma
    faixa com peso_max vazio (excedente). Faixas faltando já foram recusadas em
    preparar_tabela.
    """
    rotas = tab[ROTA].drop_duplicates()
    rotas = rotas.merge(
        tab.groupby(ROTA, as_index=False)["peso_min"].min().rename(columns={"peso_min": "_peso_min_rota"}),
        on=ROTA,
    )
    base = ped.merge(rotas, on=["origem", "uf", "destino_tipo"], how="inner")
    base = base[base["peso_kg"] >= base["_peso_min_rota"]].drop(columns="_peso_min_rota")
    if base.empty:
        opcoes = base.reindex(columns=list(base.columns) + [c for c in COLUNAS_TABELA if c not in base.columns])
    else:
        opcoes = pd.merge_asof(
            base.sort_values("peso_kg"),
            tab.drop(columns="regiao").sort_values("peso_max"),
            left_on="peso_kg",
            right_on="peso_max",
            by=ROTA,
            direction="forward",
        ).dropna(subset=["custo_base"])
    excedente = (opcoes["peso_kg"] - opcoes["peso_min"]).clip(lower=0)
    opcoes["gris_adv_valor"] = (opcoes["gris_adv_pct"] / 100 * opcoes["valor_mercadoria"]).round(2)
    opcoes["custo_frete"] = (
        opcoes["custo_base"] + opcoes["custo_por_kg"] * excedente + opcoes["gris_adv_pct"] / 100 * opcoes["valor_mercadoria"]
    ).round(2)
    if prazo_max is not None:
        opcoes = opcoes[opcoes["prazo_dias"] <= prazo_max]
    return opcoes.sort_values(["pedido_id", "transportadora"]).reset_index(drop=True)


def calcular_opcoes(
    pedidos: pd.DataFrame, tabela: pd.DataFrame, prazo_max: float | None = None
) -> pd.DataFrame:
    """Todas as opções de frete de cada pedido (uma linha por pedido e transportadora).

    Frete = custo_base (valor da faixa) + custo_por_kg × (peso_kg − peso_min)
            + gris_adv_pct% × valor_mercadoria.
    No formato simples (sem faixas, peso_min 0) isso é custo_base + custo_por_kg × peso_kg.
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
        .drop_duplicates("pedido_id")[["pedido_id", "transportadora", "custo_frete", "gris_adv_valor", "prazo_dias"]]
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

    A variação vale para o valor da faixa, o custo por kg e o % de GRIS + Ad valorem,
    ou seja, para o frete inteiro da transportadora.

    Retorna dict com resultado da simulação ajustada e métricas de comparação.
    """
    tabela_ajustada = normalizar_tabela(tabela)
    mascara = tabela_ajustada["transportadora"] == transportadora
    for col in ["custo_base", "custo_por_kg", "gris_adv_pct"]:
        valores = pd.to_numeric(tabela_ajustada[col], errors="coerce")
        tabela_ajustada[col] = valores.where(~mascara, valores * (1 + variacao_pct / 100))
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

    # Uma rota por UF com faixas de peso + excedente, e uma linha por região.
    exemplo_tabela = pd.DataFrame([
        ["Transportadora A", "CD Leste", "SP", "", "Capital", 0.000, 0.250, 9.80, 0, 0.30, 2],
        ["Transportadora A", "CD Leste", "SP", "", "Capital", 0.251, 0.500, 10.40, 0, 0.30, 2],
        ["Transportadora A", "CD Leste", "SP", "", "Capital", 0.501, 30.000, 39.90, 0, 0.30, 2],
        ["Transportadora A", "CD Leste", "SP", "", "Capital", 30.000, None, 39.90, 1.10, 0.30, 2],
        ["Transportadora A", "CD Leste", "", "Nordeste", "Interior", 0, None, 18.00, 2.40, 0.50, 7],
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
        ["Tabela de frete", "uf", "UF de destino (ex: SP). Preencha uf, regiao ou as duas"],
        ["Tabela de frete", "regiao", "Sudeste, Sul, Centro-Oeste, Nordeste ou Norte. Linha só com regiao vale para todas as UFs da região; se houver linha da UF, vale a da UF"],
        ["Tabela de frete", "destino_tipo", "Capital ou Interior (deve bater com a do pedido)"],
        ["Tabela de frete", "peso_min", "Início da faixa de peso em kg (vazio = 0)"],
        ["Tabela de frete", "peso_max", "Fim da faixa de peso em kg (vazio = sem limite). O pedido cai na menor faixa que comporta o peso"],
        ["Tabela de frete", "custo_base", "Valor da faixa em R$ (ou custo fixo por envio, se não usar faixas)"],
        ["Tabela de frete", "custo_por_kg", "R$ por kg acima do peso_min. Com faixas, use 0; na linha de excedente (ex.: peso_min 30, peso_max vazio), o R$/kg excedente"],
        ["Tabela de frete", "gris_adv_pct", "GRIS + Ad valorem em % do valor de mercadoria: 0,30 = 0,30%. Não formate a célula como % (vazio = 0)"],
        ["Tabela de frete", "prazo_dias", "Prazo de entrega em dias úteis (número inteiro)"],
        ["Tabela de frete", "(cálculo)", "Frete = custo_base + custo_por_kg × (peso − peso_min) + gris_adv_pct% × valor de mercadoria"],
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
        normalizar_tabela(tabela).to_excel(escritor, sheet_name="Parametros", index=False)
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
