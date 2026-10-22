# 🚚 Simulador de Frete

🔗 **Demonstração online:** https://simulador-frete-eaobrqw25lon7caztx9qsh.streamlit.app/

App em **Streamlit** que compara transportadoras: escolhe, para cada pedido, a mais barata dentro do prazo, e mostra o ranking por região e por UF. Custos e prazos da tabela de frete podem ser alterados direto na tela para ver o impacto.

> **Todos os dados deste repositório são fictícios.** Transportadoras, preços e pedidos foram gerados por `gerar_dados.py`.

## O que ele faz

**Simulação de pedidos**
- Lê uma base de pedidos e uma tabela de frete (CSV ou Excel).
- Calcula o custo de cada opção: `custo_base + custo_por_kg × peso_kg`.
- Escolhe a transportadora mais barata; em caso de empate, a de menor prazo.
- Permite **editar custos e prazos** e **limitar o prazo máximo**.
- Mostra o impacto frente à tabela original (custo total e custo médio).
- Exporta um `.xlsx` com resultado, resumo, ranking de transportadoras e a tabela usada na rodada.

**Ranking por região**
- Top 3 geral, Top 3 por região e a transportadora mais barata de cada UF, com mapa de calor em frete e prazo.
- Filtros por transportadora, origem da coleta e região de destino.
- Variação de cada colocado em relação ao seguinte (Top 1 vs Top 2, Top 2 vs Top 3).

Frete e prazo são **médias ponderadas** (total ÷ pedidos). A linha TOTAL do resumo e o custo médio são calculados a partir dos pedidos, não pela média das médias dos grupos.

## Como rodar

```bash
git clone https://github.com/DanilloMiguel/simulador-frete.git
cd simulador-frete
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

O app abre em `http://localhost:8501`.

Para regerar os dados de exemplo: `python gerar_dados.py`. Para rodar os testes: `pytest`.

## Estrutura

```
app.py            interface (Streamlit): fluxo e abas
visual.py         formatação, cards, mapa de calor e gráficos
frete.py          lógica de cálculo e ranking, sem dependência de Streamlit
gerar_dados.py    gera os dados fictícios em data/
data/             pedidos_exemplo.csv e tabela_frete_exemplo.csv
tests/            testes automatizados da lógica
```

A lógica fica em `frete.py` de propósito: o mesmo código pode ser chamado por um script agendado, sem a interface.

## Formato dos arquivos

**Pedidos:** `pedido_id, origem, destino_tipo, uf, peso_kg, valor_pedido`
A região é derivada da UF (as 27 UFs são reconhecidas).

**Tabela de frete:** `transportadora, origem, regiao, destino_tipo, custo_base, custo_por_kg, prazo_dias`
`regiao` deve ser `Sudeste`, `Sul`, `Centro-Oeste`, `Nordeste` ou `Norte`.

## Publicar

No [Streamlit Community Cloud](https://share.streamlit.io) dá para publicar direto deste repositório, **somente com dados fictícios**, pois o app fica público e roda fora de qualquer rede corporativa. Para dados reais, a recomendação é hospedar em servidor interno da empresa.
