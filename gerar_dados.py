"""Gera os dados FICTÍCIOS de exemplo em data/.

Nomes de transportadoras, preços e pedidos são inventados. Nada aqui vem de
dados reais de nenhuma empresa. Rode: python gerar_dados.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).parent / "data"
SEED = 42
N_PEDIDOS = 600

ORIGENS = {"CD Norte": 0.45, "CD Sul": 0.35, "Loja": 0.20}
DESTINOS = {"Capital": 0.40, "Interior": 0.60}
UFS = ["SP", "MG", "GO", "RJ", "BA", "PR", "SC", "RS", "DF"]

# (custo base, custo por kg, ajuste de prazo em dias)
TRANSPORTADORAS = {
    "Transportadora Alfa": (9.0, 2.2, 0),
    "Transportadora Beta": (12.0, 1.4, 1),
    "Transportadora Gama": (15.0, 0.9, -1),
    "Transportadora Delta": (7.5, 2.8, 3),
}
MULT_ORIGEM = {"CD Norte": 1.0, "CD Sul": 1.1, "Loja": 0.8}
MULT_DESTINO = {"Capital": 1.0, "Interior": 1.35}
PRAZO_DESTINO = {"Capital": 2, "Interior": 5}
AJUSTE_PRAZO_ORIGEM = {"CD Norte": 0, "CD Sul": 0, "Loja": -1}


def gerar_pedidos(rng: np.random.Generator) -> pd.DataFrame:
    peso = np.clip(rng.lognormal(mean=0.6, sigma=0.7, size=N_PEDIDOS), 0.2, 15).round(2)
    return pd.DataFrame(
        {
            "pedido_id": [f"P{i:05d}" for i in range(1, N_PEDIDOS + 1)],
            "origem": rng.choice(list(ORIGENS), size=N_PEDIDOS, p=list(ORIGENS.values())),
            "destino_tipo": rng.choice(list(DESTINOS), size=N_PEDIDOS, p=list(DESTINOS.values())),
            "uf": rng.choice(UFS, size=N_PEDIDOS),
            "peso_kg": peso,
            "valor_pedido": rng.uniform(80, 1200, size=N_PEDIDOS).round(2),
        }
    )


def gerar_tabela() -> pd.DataFrame:
    linhas = []
    for nome, (base, por_kg, ajuste) in TRANSPORTADORAS.items():
        for origem, m_o in MULT_ORIGEM.items():
            for destino, m_d in MULT_DESTINO.items():
                prazo = PRAZO_DESTINO[destino] + ajuste + AJUSTE_PRAZO_ORIGEM[origem]
                linhas.append(
                    {
                        "transportadora": nome,
                        "origem": origem,
                        "destino_tipo": destino,
                        "custo_base": round(base * m_o * m_d, 2),
                        "custo_por_kg": round(por_kg * m_o * m_d, 2),
                        "prazo_dias": max(1, prazo),
                    }
                )
    return pd.DataFrame(linhas)


if __name__ == "__main__":
    DATA.mkdir(exist_ok=True)
    gerar_pedidos(np.random.default_rng(SEED)).to_csv(DATA / "pedidos_exemplo.csv", index=False)
    gerar_tabela().to_csv(DATA / "tabela_frete_exemplo.csv", index=False)
    print(f"Arquivos gerados em {DATA}")
