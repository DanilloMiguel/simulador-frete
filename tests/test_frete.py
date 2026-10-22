import io

import numpy as np
import openpyxl
import pandas as pd
import pytest

import frete
import gerar_dados


def tabela(*linhas, regiao="Sudeste"):
    """(transportadora, origem, destino_tipo, custo_base, custo_por_kg, prazo_dias).

    A região é a mesma para todas as linhas (por padrão, Sudeste, a de SP e MG).
    """
    dados = [(t, o, regiao, d, b, k, p) for (t, o, d, b, k, p) in linhas]
    return pd.DataFrame(dados, columns=frete.COLUNAS_TABELA)


def pedidos(*linhas):
    """(pedido_id, origem, destino_tipo, uf, peso_kg, valor_pedido)"""
    return pd.DataFrame(linhas, columns=frete.COLUNAS_PEDIDOS)


P1 = ("P1", "CD", "Capital", "SP", 2.0, 100.0)


# ------------------------------------------------------------------ simulação
def test_escolhe_a_mais_barata():
    t = tabela(("A", "CD", "Capital", 10, 2, 5), ("B", "CD", "Capital", 9, 2, 5))
    r = frete.simular(pedidos(P1), t)
    assert r.loc[0, "transportadora"] == "B"
    assert r.loc[0, "custo_frete"] == 13.0


def test_empate_de_custo_decide_pelo_menor_prazo():
    t = tabela(("A", "CD", "Capital", 10, 2, 5), ("B", "CD", "Capital", 8, 3, 3))
    r = frete.simular(pedidos(P1), t)  # ambas custam 14
    assert r.loc[0, "transportadora"] == "B"


def test_respeita_prazo_maximo():
    t = tabela(("A", "CD", "Capital", 5, 1, 8), ("B", "CD", "Capital", 20, 2, 3))
    assert frete.simular(pedidos(P1), t, prazo_max=5).loc[0, "transportadora"] == "B"
    sem = frete.simular(pedidos(P1), t, prazo_max=2)
    assert sem.loc[0, "transportadora"] == frete.SEM_COBERTURA
    assert pd.isna(sem.loc[0, "custo_frete"])


def test_origem_fora_da_tabela_fica_sem_cobertura():
    t = tabela(("A", "OUTRO", "Capital", 10, 2, 5))
    r = frete.simular(pedidos(P1), t)
    assert r.loc[0, "transportadora"] == frete.SEM_COBERTURA


def test_regiao_vem_da_uf_do_pedido():
    sul = tabela(("A", "CD", "Capital", 10, 2, 5), regiao="Sul")
    assert frete.simular(pedidos(("P1", "CD", "Capital", "pr", 2.0, 100.0)), sul).loc[0, "transportadora"] == "A"
    assert frete.simular(pedidos(P1), sul).loc[0, "transportadora"] == frete.SEM_COBERTURA  # SP é Sudeste


def test_todas_as_ufs_tem_regiao():
    assert len(frete.REGIAO_POR_UF) == 27
    assert set(frete.REGIAO_POR_UF.values()) == set(frete.ORDEM_REGIOES)


def test_media_ponderada_nao_e_media_das_medias():
    t = tabela(("A", "CD", "Capital", 10, 0, 2), ("A", "CD", "Interior", 20, 0, 4))
    ped = pedidos(
        ("P1", "CD", "Capital", "SP", 1.0, 50.0),
        ("P2", "CD", "Interior", "MG", 1.0, 50.0),
        ("P3", "CD", "Interior", "MG", 1.0, 50.0),
        ("P4", "CD", "Interior", "MG", 1.0, 50.0),
    )
    res = frete.resumo(frete.simular(ped, t))
    total = res[res["origem"] == "TOTAL"].iloc[0]
    assert total["custo_medio"] == pytest.approx(17.5)  # 70 / 4
    assert total["custo_medio"] != pytest.approx(15.0)  # média simples de 10 e 20


# ------------------------------------------------------------------- validação
def test_pedido_id_repetido_gera_erro():
    t = tabela(("A", "CD", "Capital", 10, 2, 5))
    with pytest.raises(ValueError, match="repetido"):
        frete.simular(pedidos(P1, P1), t)


def test_coluna_faltando_gera_erro():
    t = tabela(("A", "CD", "Capital", 10, 2, 5)).drop(columns="prazo_dias")
    with pytest.raises(ValueError, match="prazo_dias"):
        frete.simular(pedidos(P1), t)


def test_valor_invalido_gera_erro():
    t = tabela(("A", "CD", "Capital", "dez", 2, 5))
    with pytest.raises(ValueError, match="inválido"):
        frete.simular(pedidos(P1), t)


def test_uf_desconhecida_gera_erro():
    t = tabela(("A", "CD", "Capital", 10, 2, 5))
    with pytest.raises(ValueError, match="XX"):
        frete.simular(pedidos(("P1", "CD", "Capital", "XX", 2.0, 100.0)), t)


# --------------------------------------------------------------------- ranking
def test_ranking_top3_e_variacao_contra_o_seguinte():
    t = tabela(
        ("A", "CD", "Capital", 10, 0, 3),
        ("B", "CD", "Capital", 12, 0, 4),
        ("C", "CD", "Capital", 15, 0, 5),
        ("D", "CD", "Capital", 20, 0, 6),
    )
    ped = pedidos(P1, ("P2", "CD", "Capital", "MG", 3.0, 100.0))
    r = frete.ranking(frete.calcular_opcoes(ped, t), ["regiao"])
    assert list(r["transportadora"]) == ["A", "B", "C"]  # D fica fora do Top 3
    assert list(r["posicao"]) == [1, 2, 3]
    assert r.loc[0, "var_pct"] == pytest.approx((10 / 12 - 1) * 100)
    assert r.loc[1, "var_pct"] == pytest.approx((12 / 15 - 1) * 100)
    assert pd.isna(r.loc[2, "var_pct"])


def test_ranking_usa_media_ponderada_dos_pedidos():
    t = tabela(("A", "CD", "Capital", 10, 0, 2), ("A", "CD", "Interior", 20, 0, 4))
    ped = pedidos(
        ("P1", "CD", "Capital", "SP", 1.0, 50.0),
        ("P2", "CD", "Interior", "SP", 1.0, 50.0),
        ("P3", "CD", "Interior", "SP", 1.0, 50.0),
        ("P4", "CD", "Interior", "SP", 1.0, 50.0),
    )
    r = frete.ranking(frete.calcular_opcoes(ped, t), ["regiao"])
    assert r.loc[0, "frete"] == pytest.approx(17.5)  # 70 / 4, e não (10 + 20) / 2
    assert r.loc[0, "prazo"] == pytest.approx(3.5)  # (2 + 4 + 4 + 4) / 4


def test_ranking_empate_decide_pelo_prazo():
    t = tabela(("A", "CD", "Capital", 10, 0, 5), ("B", "CD", "Capital", 10, 0, 3))
    r = frete.ranking(frete.calcular_opcoes(pedidos(P1), t), ["uf"])
    assert list(r["transportadora"]) == ["B", "A"]


def test_ranking_geral_sem_agrupamento():
    t = tabela(("A", "CD", "Capital", 10, 0, 5), ("B", "CD", "Capital", 12, 0, 3))
    r = frete.ranking(frete.calcular_opcoes(pedidos(P1), t), [])
    assert list(r["transportadora"]) == ["A", "B"]


def test_dados_de_exemplo_sao_coerentes():
    ped = gerar_dados.gerar_pedidos(np.random.default_rng(1))
    tab = gerar_dados.gerar_tabela()
    assert set(gerar_dados.PESO_UF) == set(frete.REGIAO_POR_UF)
    assert len(tab) == 120
    assert (frete.simular(ped, tab)["transportadora"] != frete.SEM_COBERTURA).all()


# ----------------------------------------------------------------------- excel
def test_excel_tem_as_quatro_abas():
    t = tabela(("A", "CD", "Capital", 10, 2, 5))
    r = frete.simular(pedidos(P1), t)
    dados = frete.exportar_excel(r, frete.resumo(r), frete.por_transportadora(r), t)
    wb = openpyxl.load_workbook(io.BytesIO(dados))
    assert wb.sheetnames == ["Resultado", "Resumo", "Transportadoras", "Parametros"]


def test_excel_usa_rotulos_e_mantem_parametros_reutilizaveis():
    t = tabela(("A", "CD", "Capital", 10, 2, 5))
    r = frete.simular(pedidos(P1), t)
    dados = frete.exportar_excel(r, frete.resumo(r), frete.por_transportadora(r), t)
    wb = openpyxl.load_workbook(io.BytesIO(dados))
    cabecalho = lambda aba: [c.value for c in wb[aba][1]]
    assert "Frete (R$)" in cabecalho("Resultado")
    assert "Custo médio (R$)" in cabecalho("Resumo")
    assert cabecalho("Parametros") == frete.COLUNAS_TABELA  # pode voltar como entrada
