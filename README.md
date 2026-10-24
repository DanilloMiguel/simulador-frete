# 🚚 Simulador de Frete

[![Testes](https://github.com/DanilloMiguel/simulador-frete/actions/workflows/tests.yml/badge.svg)](https://github.com/DanilloMiguel/simulador-frete/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Licença](https://img.shields.io/badge/licença-MIT-lightgrey)

🔗 **Demonstração online:** https://simulador-frete-eaobrqw25lon7caztx9qsh.streamlit.app/

App em **Streamlit** que compara transportadoras: escolhe, para cada pedido, a mais barata dentro do prazo, e mostra o ranking por região e por UF. Custos e prazos da tabela de frete podem ser alterados direto na tela para ver o impacto.

> **Todos os dados deste repositório são fictícios.** Transportadoras, preços e pedidos foram gerados por `gerar_dados.py`.

### Mapa do Brasil por UF 

<img width="1544" height="625" alt="image" src="https://github.com/user-attachments/assets/5c336a42-7e19-4334-8311-a8850f7a66d5" />

### Ranking por região

<img width="1566" height="688" alt="image" src="https://github.com/user-attachments/assets/bca9e7cc-250c-4023-8d54-22325d4d3f6b" />


## Que problema ele resolve

Quando uma operação de e-commerce trabalha com várias transportadoras, cada uma com tabela própria por origem, UF ou região, tipo de destino e faixa de peso, é difícil responder perguntas como:

- Qual transportadora é a mais barata em cada região, e por quanto?
- Quanto o custo total muda se eu limitar o prazo máximo de entrega?
- Se uma transportadora reajustar a tabela em 5%, quantos pedidos trocam de mãos e qual o impacto no custo?

O simulador responde a essas perguntas sobre uma base de pedidos, sem planilha manual.

## O que ele faz

**Simulação de pedidos**
- Lê uma base de pedidos e uma tabela de frete (CSV ou Excel).
- Calcula o custo de cada opção: valor da faixa de peso + excedente por kg + GRIS e Ad valorem (% do valor de mercadoria).
- Escolhe a transportadora mais barata; em caso de empate, a de menor prazo.
- Permite **editar custos e prazos** e **limitar o prazo máximo**.
- Mostra o impacto frente à tabela original (custo total e custo médio).
- Exporta um `.xlsx` com resultado, resumo, ranking de transportadoras e a tabela usada na rodada.

**Distribuição dos pedidos**
- Mapa do Brasil por UF: a cor mostra o frete médio e o tamanho da bolha mostra o número de pedidos, ou seja, onde está a maior demanda.
- Faixas de peso e de valor de mercadoria.
- **% custo de frete** = Frete ÷ Valor de mercadoria, pedido a pedido, com média, mediana e máximo. A explicação do cálculo aparece na própria tela.

**Análise de sensibilidade**
- Ajuste de 1 em 1 ponto percentual (de -30% a +30%) no custo de uma transportadora e veja quantos pedidos trocam de mão e o impacto no custo.

**Ranking por região**
- Top 3 geral, Top 3 por região e a transportadora mais barata de cada UF, com mapa de calor em frete e prazo.
- Filtros por transportadora, origem da coleta e região de destino.
- Variação de cada colocado em relação ao seguinte (Top 1 vs Top 2, Top 2 vs Top 3).

## Decisões e premissas

- **Chave de cruzamento:** cada pedido encontra as opções da tabela por `origem + UF + tipo de destino` e depois pela faixa de peso. Uma linha da tabela pode ser de uma UF ou de uma região inteira (vale para todas as UFs dela); se houver as duas para a mesma transportadora, origem e destino, **vale a da UF**. Assim dá para preencher por região e corrigir só as exceções.
- **Faixa de peso:** o pedido cai na menor faixa cujo `peso_max` comporta o peso. Um peso entre duas faixas (0,2505 kg entre 0,250 e 0,251, por exemplo) vai para a faixa de cima. Acima da última faixa, só há cobertura se existir uma linha de excedente (`peso_max` vazio).
- **Cálculo do frete:** `custo_base + custo_por_kg × (peso_kg − peso_min) + gris_adv_pct% × valor_mercadoria`. Com faixas, `custo_base` é o valor da faixa e `custo_por_kg` fica 0; na linha de excedente (ex.: `peso_min` 30, `peso_max` vazio), `custo_por_kg` é o R$ por kg acima de 30. Sem faixas (`peso_min` 0), volta a ser `custo_base + custo_por_kg × peso_kg`.
- **Escolha da vencedora:** menor custo; empate decidido pelo menor prazo e, persistindo, pelo nome da transportadora (ordem alfabética), para o resultado ser sempre reproduzível.
- **Prazo máximo:** opções com prazo acima do limite são descartadas. Pedido sem nenhuma opção restante (ou sem linha na tabela) aparece como **"Sem cobertura"**, e fica fora dos custos médios.
- **Médias ponderadas, não médias das médias:** frete e prazo por grupo são `total ÷ pedidos`. A linha TOTAL e o custo médio saem dos pedidos, não das linhas dos grupos, porque grupos de tamanhos diferentes não podem pesar igual. Há testes automatizados para isso.
- **% custo de frete:** a tela mostra a média simples dos percentuais (cada pedido pesa igual) e, para comparação, o percentual ponderado (soma do frete ÷ soma do valor de mercadoria). Os dois contam histórias diferentes e é útil ver ambos.
- **Sensibilidade:** o ajuste em % é aplicado ao `custo_base`, ao `custo_por_kg` e ao `gris_adv_pct` da transportadora escolhida, ou seja, ao frete inteiro; o prazo não muda. Depois disso, toda a simulação é refeita.
- **Ranking:** cada transportadora é avaliada aplicando a tabela dela aos pedidos do grupo (região ou UF), não só aos que ela venceria na simulação.
- **Onde o prazo máximo vale:** na simulação, na análise de sensibilidade e na distribuição dos pedidos. As abas de ranking e de cobertura comparam todas as opções da tabela, sem o limite.

## Limitações

- Não considera peso cubado, frete mínimo, pedágio, TDA/TRT nem outras taxas adicionais. GRIS e Ad valorem entram juntos em um único percentual.
- A tabela de frete é por UF (ou região) e tipo de destino (Capital ou Interior), não por faixa de CEP. Quem tem tabela por CEP pode usar a média da UF.
- Não há restrição de capacidade: uma transportadora pode "ganhar" todos os pedidos de uma região.
- Os dados de exemplo são sintéticos (`gerar_dados.py`, seed fixa). O desenho de quem é mais barata onde é uma premissa do gerador, **não uma conclusão sobre o mercado real**.

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

Para regerar os dados de exemplo: `python gerar_dados.py`.

Para rodar os testes (instala também o `pytest`):

```bash
pip install -r requirements-dev.txt
pytest
```

## Estrutura

```
app.py                interface (Streamlit): fluxo e abas
visual.py             formatação, cards, mapa de calor, mapa do Brasil e gráficos
frete.py              lógica de cálculo e ranking, sem dependência de Streamlit
gerar_dados.py        gera os dados fictícios em data/
data/                 pedidos_exemplo.csv, tabela_frete_exemplo.csv e brasil_ufs.geojson (contorno das UFs)
tools/                gerar_mapa_brasil.py: gera o brasil_ufs.geojson a partir de um GeoJSON de estados
tests/                testes automatizados da lógica
requirements.txt      dependências para rodar o app
requirements-dev.txt  dependências do app + pytest
pytest.ini            configuração do pytest
.streamlit/           tema do app (cores)
.devcontainer/        ambiente pronto para GitHub Codespaces
.github/workflows/    CI: roda os testes no Python 3.11 e 3.12 a cada push e pull request
LICENSE               licença do código
```

A lógica fica em `frete.py` de propósito: o mesmo código pode ser chamado por um script agendado, sem a interface.

## Formato dos arquivos

**Pedidos:** `pedido_id, origem, destino_tipo, uf, peso_kg, valor_mercadoria`
`valor_mercadoria` é o valor da mercadoria do pedido em R$, sem o frete. O nome antigo `valor_pedido` ainda é aceito.
A região é derivada da UF (as 27 UFs são reconhecidas).

**Tabela de frete:** `transportadora, origem, uf, regiao, destino_tipo, peso_min, peso_max, custo_base, custo_por_kg, gris_adv_pct, prazo_dias`

| Coluna | Obrigatória | O que é |
|---|---|---|
| `transportadora`, `origem`, `destino_tipo` | sim | `origem` e `destino_tipo` devem bater com os do pedido |
| `uf` | `uf` ou `regiao` | UF de destino; vazio = a linha vale para a região inteira |
| `regiao` | `uf` ou `regiao` | `Sudeste`, `Sul`, `Centro-Oeste`, `Nordeste` ou `Norte` |
| `peso_min`, `peso_max` | não | faixa de peso em kg; `peso_min` vazio = 0, `peso_max` vazio = sem limite |
| `custo_base` | sim | valor da faixa em R$ (ou custo fixo por envio, sem faixas) |
| `custo_por_kg` | sim (pode ser 0) | R$ por kg acima de `peso_min` |
| `gris_adv_pct` | não | GRIS + Ad valorem em % do valor de mercadoria: `0.30` = 0,30% (não formate a célula como %); vazio = 0 |
| `prazo_dias` | sim | prazo em dias úteis |

O formato antigo (`transportadora, origem, regiao, destino_tipo, custo_base, custo_por_kg, prazo_dias`) continua aceito e dá o mesmo resultado. A planilha modelo do app tem um exemplo com faixas, excedente e uma linha por região.

## Publicar

No [Streamlit Community Cloud](https://share.streamlit.io) dá para publicar direto deste repositório, **somente com dados fictícios**, pois o app fica público e roda fora de qualquer rede corporativa. Para dados reais, a recomendação é hospedar em servidor interno da empresa.

## Sobre o desenvolvimento

Projeto desenvolvido com o apoio do Claude (Anthropic). Os testes em `tests/` cobrem a lógica de cálculo e rodam automaticamente a cada push.

## Fonte do mapa

O arquivo `data/brasil_ufs.geojson` foi gerado por `tools/gerar_mapa_brasil.py` a partir do `brazil-states.geojson` do repositório público [codeforamerica/click_that_hood](https://github.com/codeforamerica/click_that_hood), com os contornos simplificados (tolerância de 0,03°, cerca de 3 km) para o app carregar rápido. O projeto de origem é MIT, mas **não informa de onde vêm os dados dos contornos nem a licença deles**; por isso a origem original não está documentada aqui. O mapa serve só para ilustrar a distribuição dos pedidos fictícios e não é adequado para medições ou limites oficiais.

## Licença

[MIT](LICENSE)
