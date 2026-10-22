# 🚚 Simulador de Frete

App em **Streamlit** que escolhe, para cada pedido, a transportadora mais barata dentro do prazo, e permite alterar custos e prazos da tabela de frete direto na tela para ver o impacto.

> **Todos os dados deste repositório são fictícios.** Transportadoras, preços e pedidos foram gerados por `gerar_dados.py`.

## O que ele faz

- Lê uma base de pedidos e uma tabela de frete (CSV ou Excel).
- Calcula o custo de cada opção: `custo_base + custo_por_kg × peso_kg`.
- Escolhe a transportadora mais barata; em caso de empate, a de menor prazo.
- Permite **editar custos e prazos** e **limitar o prazo máximo**.
- Mostra o impacto frente à tabela original (custo total e custo médio).
- Exporta um `.xlsx` com resultado, resumo, ranking de transportadoras e a tabela usada na rodada.

O custo médio é uma **média ponderada** (total de frete ÷ pedidos cobertos), e a linha TOTAL do resumo é calculada a partir dos pedidos, não pela média das médias dos grupos.

## Como rodar

```bash
git clone <url-do-repositorio>
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
app.py            interface (Streamlit)
frete.py          lógica de cálculo, sem dependência de Streamlit
gerar_dados.py    gera os dados fictícios em data/
data/             pedidos_exemplo.csv e tabela_frete_exemplo.csv
tests/            testes automatizados da lógica
```

A lógica fica em `frete.py` de propósito: o mesmo código pode ser chamado por um script agendado, sem a interface.

## Formato dos arquivos

**Pedidos:** `pedido_id, origem, destino_tipo, uf, peso_kg, valor_pedido`

**Tabela de frete:** `transportadora, origem, destino_tipo, custo_base, custo_por_kg, prazo_dias`

## Publicar

No [Streamlit Community Cloud](https://share.streamlit.io) dá para publicar direto deste repositório, **somente com dados fictícios**, pois o app fica público e roda fora de qualquer rede corporativa. Para dados reais, a recomendação é hospedar em servidor interno da empresa.
