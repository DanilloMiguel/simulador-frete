"""Gera os dados FICTÍCIOS de exemplo em data/.

Nomes de transportadoras, preços e pedidos são inventados. Nada aqui vem de
dados reais de nenhuma empresa. Rode: python gerar_dados.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

from frete import COLUNAS_TABELA, ORDEM_REGIOES, REGIAO_POR_UF

DATA = Path(__file__).parent / "data"
SEED = 42
N_PEDIDOS = 3000

ORIGENS = {"CD Leste": 0.45, "CD Oeste": 0.35, "Loja": 0.20}
DESTINOS = {"Capital": 0.40, "Interior": 0.60}

# Peso relativo de cada UF nos pedidos (soma 100).
PESO_UF = {
    "SP": 25, "MG": 9, "RJ": 8, "ES": 2,
    "PR": 6, "SC": 5, "RS": 6,
    "DF": 3, "GO": 4, "MT": 2, "MS": 2,
    "BA": 6, "PE": 4, "CE": 4, "AL": 1, "SE": 1, "RN": 1, "PB": 1, "PI": 1, "MA": 2,
    "AM": 1.5, "PA": 2, "TO": 1, "RO": 1, "AC": 0.5, "AP": 0.5, "RR": 0.5,
}

# (custo base, custo por kg, ajuste de prazo em dias)
TRANSPORTADORAS = {
    "Transportadora Alfa": (9.0, 2.2, 0),
    "Transportadora Beta": (12.0, 1.4, 1),
    "Transportadora Gama": (15.0, 0.9, -1),
    "Transportadora Delta": (7.5, 2.8, 3),
}
# Onde cada transportadora é mais competitiva (menor = mais barata), por região.
AFINIDADE = {
    "Transportadora Alfa": {"Sudeste": 0.90, "Sul": 1.05, "Centro-Oeste": 1.10, "Nordeste": 1.15, "Norte": 1.20},
    "Transportadora Beta": {"Sudeste": 1.05, "Sul": 0.88, "Centro-Oeste": 1.00, "Nordeste": 1.10, "Norte": 1.15},
    "Transportadora Gama": {"Sudeste": 1.10, "Sul": 1.00, "Centro-Oeste": 0.80, "Nordeste": 1.05, "Norte": 1.05},
    "Transportadora Delta": {"Sudeste": 1.00, "Sul": 1.10, "Centro-Oeste": 1.05, "Nordeste": 0.85, "Norte": 0.88},
}
MULT_REGIAO = {"Sudeste": 1.0, "Sul": 1.15, "Centro-Oeste": 1.25, "Nordeste": 1.45, "Norte": 1.80}
PRAZO_REGIAO = {"Sudeste": 2, "Sul": 3, "Centro-Oeste": 4, "Nordeste": 6, "Norte": 9}
MULT_ORIGEM = {"CD Leste": 1.0, "CD Oeste": 1.08, "Loja": 0.85}
AJUSTE_PRAZO_ORIGEM = {"CD Leste": 0, "CD Oeste": 0, "Loja": -1}
MULT_DESTINO = {"Capital": 1.0, "Interior": 1.30}
PRAZO_DESTINO = {"Capital": 0, "Interior": 2}

# Faixas de peso (kg) até 30 kg + linha de excedente (peso_max vazio = sem limite).
# Tabelas reais costumam ter mais faixas (0–0,250, 0,251–0,500…); aqui são menos para
# a tabela de exemplo caber no editor.
FAIXAS = [(0.0, 1.0), (1.001, 2.0), (2.001, 5.0), (5.001, 10.0), (10.001, 20.0), (20.001, 30.0)]
PESO_EXCEDENTE = 30.0
# GRIS + Ad valorem (% do valor de mercadoria): 0,30 = 0,30%.
GRIS_ADV = {
    "Transportadora Alfa": 0.30,
    "Transportadora Beta": 0.40,
    "Transportadora Gama": 0.25,
    "Transportadora Delta": 0.50,
}
# Exceções por UF: o preço da UF sobrepõe o da região (multiplicador sobre o preço da região).
EXCECOES_UF = {
    ("Transportadora Alfa", "SP"): 0.90,
    ("Transportadora Delta", "BA"): 0.90,
    ("Transportadora Gama", "AM"): 1.20,
}


def gerar_pedidos(rng: np.random.Generator) -> pd.DataFrame:
    ufs = list(PESO_UF)
    probs = np.array(list(PESO_UF.values()), dtype=float)
    peso = np.clip(rng.lognormal(mean=0.6, sigma=0.7, size=N_PEDIDOS), 0.2, 15).round(2)
    return pd.DataFrame(
        {
            "pedido_id": [f"P{i:05d}" for i in range(1, N_PEDIDOS + 1)],
            "origem": rng.choice(list(ORIGENS), size=N_PEDIDOS, p=list(ORIGENS.values())),
            "destino_tipo": rng.choice(list(DESTINOS), size=N_PEDIDOS, p=list(DESTINOS.values())),
            "uf": rng.choice(ufs, size=N_PEDIDOS, p=probs / probs.sum()),
            "peso_kg": peso,
            "valor_mercadoria": rng.uniform(80, 1200, size=N_PEDIDOS).round(2),
        }
    )


def _linhas_rota(nome, origem, uf, regiao, destino, mult_extra=1.0) -> list[dict]:
    """Faixas de peso + excedente de uma rota. Preço da faixa = base + R$/kg × fim da faixa."""
    base, por_kg, ajuste = TRANSPORTADORAS[nome]
    mult = (
        MULT_ORIGEM[origem] * MULT_REGIAO[regiao] * AFINIDADE[nome][regiao] * MULT_DESTINO[destino] * mult_extra
    )
    prazo = max(1, PRAZO_REGIAO[regiao] + PRAZO_DESTINO[destino] + ajuste + AJUSTE_PRAZO_ORIGEM[origem])
    comum = {
        "transportadora": nome,
        "origem": origem,
        "uf": uf,
        "regiao": regiao if uf is None else None,
        "destino_tipo": destino,
        "gris_adv_pct": GRIS_ADV[nome],
        "prazo_dias": prazo,
    }
    linhas = [
        {**comum, "peso_min": ini, "peso_max": fim, "custo_base": round((base + por_kg * fim) * mult, 2), "custo_por_kg": 0.0}
        for ini, fim in FAIXAS
    ]
    linhas.append(
        {
            **comum,
            "peso_min": PESO_EXCEDENTE,
            "peso_max": None,
            "custo_base": round((base + por_kg * PESO_EXCEDENTE) * mult, 2),
            "custo_por_kg": round(por_kg * mult, 2),
        }
    )
    return linhas


def gerar_tabela() -> pd.DataFrame:
    """Linhas por região (valem para todas as UFs da região) + algumas exceções por UF."""
    linhas = []
    for nome in TRANSPORTADORAS:
        for origem in ORIGENS:
            for regiao in ORDEM_REGIOES:
                for destino in DESTINOS:
                    linhas += _linhas_rota(nome, origem, None, regiao, destino)
    for (nome, uf), mult in EXCECOES_UF.items():
        for origem in ORIGENS:
            for destino in DESTINOS:
                linhas += _linhas_rota(nome, origem, uf, REGIAO_POR_UF[uf], destino, mult)
    return pd.DataFrame(linhas, columns=COLUNAS_TABELA)


if __name__ == "__main__":
    assert set(PESO_UF) == set(REGIAO_POR_UF), "UFs de gerar_dados e frete divergem"
    DATA.mkdir(exist_ok=True)
    gerar_pedidos(np.random.default_rng(SEED)).to_csv(DATA / "pedidos_exemplo.csv", index=False)
    gerar_tabela().to_csv(DATA / "tabela_frete_exemplo.csv", index=False)
    print(f"Arquivos gerados em {DATA}")
