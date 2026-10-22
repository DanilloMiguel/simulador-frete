"""Lógica da simulação de frete.

Fica separada da interface (app.py) para poder ser testada sem Streamlit
e reaproveitada em scripts ou em tarefas agendadas.
"""
from __future__ import annotations

import io

import pandas as pd
from openpyxl.styles import Font, PatternFill

COLUNAS_PEDIDOS = ["pedido_id", "origem", "destino_tipo", "uf", "peso_kg", "valor_pedido"]
COLUNAS_TABELA = [
    "transportadora",
    "origem",
    "destino_tipo",
    "custo_base",
    "custo_por_kg",
    "prazo_dias",
]
SEM_COBERTURA = "Sem cobertura"
CHAVE = ["origem", "destino_tipo"]

# Nomes amigáveis para exibição (tela e Excel). Internamente as colunas
# mantêm os nomes originais.
ROTULOS = {
    "pedido_id": "Pedido",
    "origem": "Origem",
    "destino_tipo": "Destino",
    "uf": "UF",
    "peso_kg": "Peso (kg)",
    "valor_pedido": "Valor do pedido (R$)",
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


def simular(
    pedidos: pd.DataFrame, tabela: pd.DataFrame, prazo_max: float | None = None
) -> pd.DataFrame:
    """Escolhe, para cada pedido, a transportadora mais barata dentro do prazo.

    Custo = custo_base + custo_por_kg * peso_kg. Empate de custo é decidido
    pelo menor prazo. Pedido sem nenhuma opção vira "Sem cobertura".
    """
    ped = _preparar(pedidos, COLUNAS_PEDIDOS, ["peso_kg", "valor_pedido"], "Pedidos")
    tab = _preparar(
        tabela, COLUNAS_TABELA, ["custo_base", "custo_por_kg", "prazo_dias"], "Tabela de frete"
    )
    if ped["pedido_id"].duplicated().any():
        raise ValueError("Pedidos: há pedido_id repetido.")

    opcoes = ped.merge(tab, on=CHAVE, how="inner")
    opcoes["custo_frete"] = (opcoes["custo_base"] + opcoes["custo_por_kg"] * opcoes["peso_kg"]).round(2)
    if prazo_max is not None:
        opcoes = opcoes[opcoes["prazo_dias"] <= prazo_max]

    vencedoras = (
        opcoes.sort_values(["pedido_id", "custo_frete", "prazo_dias", "transportadora"])
        .drop_duplicates("pedido_id")[["pedido_id", "transportadora", "custo_frete", "prazo_dias"]]
    )
    resultado = ped.merge(vencedoras, on="pedido_id", how="left")
    resultado["transportadora"] = resultado["transportadora"].fillna(SEM_COBERTURA)
    return resultado


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
