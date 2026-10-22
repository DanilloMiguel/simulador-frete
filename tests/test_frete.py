import io

import openpyxl
import pandas as pd
import pytest

import frete


def tabela(*linhas):
    """(transportadora, origem, destino_tipo, custo_base, custo_por_kg, prazo_dias)"""
    return pd.DataFrame(linhas, columns=frete.COLUNAS_TABELA)


def pedidos(*linhas):
    """(pedido_id, origem, destino_tipo, uf, peso_kg, valor_pedido)"""
    return pd.DataFrame(linhas, columns=frete.COLUNAS_PEDIDOS)


P1 = ("P1", "CD", "Capital", "SP", 2.0, 100.0)


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


def test_excel_tem_as_quatro_abas():
    t = tabela(("A", "CD", "Capital", 10, 2, 5))
    r = frete.simular(pedidos(P1), t)
    dados = frete.exportar_excel(r, frete.resumo(r), frete.por_transportadora(r), t)
    wb = openpyxl.load_workbook(io.BytesIO(dados))
    assert wb.sheetnames == ["Resultado", "Resumo", "Transportadoras", "Parametros"]
