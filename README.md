# Monitor Eleição 2026

**Link:** https://eleicao.andrefreitas.eng.br/ — abas Pesquisas · Apuração ao vivo · Balanço · RN
(governador do RN: `painel/rn.html` e `painel/rn-apuracao.html`).

## Tudo automático (GitHub Actions)

| Robô | Quando | O que faz |
|---|---|---|
| `pesquisas.yml` | de hora em hora | lê a Wikipédia (presidente e RN), atualiza os dados e o site; avisa novidades |
| `alertas.yml` | a cada commit de dados | avisa boletim ou pesquisa nova do analista; botão manual manda um alerta de teste |
| `apuracao.yml` | dom 25/10, 16h45 (reserva 17h30) | duas disputas em paralelo, lendo o TSE a cada minuto: presidente → ramo `ao-vivo`, governador do RN → ramo `ao-vivo-rn` |

Alertas por e-mail: o robô comenta no aviso nº 1 mencionando @andretab e o GitHub envia o e-mail. Só há
alerta com novidade real (pesquisa nova, pesquisa registrada no TSE, boletim do analista).

A página de pesquisas recarrega a cada 15 min; a da apuração busca o `estado.json` a cada 75 s.
Ensaio manual: aba Actions → apuracao → Run workflow (simular = sim). Depois do ensaio, apagar os ramos
(`git push origin --delete ao-vivo ao-vivo-rn`) para as páginas voltarem a "Aguardando a apuração".

Acompanhamento do 2º turno de 25/10/2026: presidente (Lula × Flávio) e governador do RN (Cadu × Allyson).
Pesquisas até a véspera, corrigidas pelo erro de cada instituto no 1º turno, e, no dia, a apuração ao vivo
com projeção por UF (presidente) ou por município (RN) e a chance de virada.

## RN · governador

- `dados/rn/tse-1t/`: TSE, 1º turno por município (eleição 6259, cargo 3); `scripts/extrair_rn.py` resume em
  `dados/rn/primeiro-turno-mun.json` (a = Cadu, b = Allyson, terceiro = Álvaro Dias).
- `scripts/atualizar_pesquisas_rn.py`: pesquisas da Wikipédia → `dados/rn/pesquisas.json` e `painel/dados-rn.js`.
  O erro de cada instituto usa só pesquisas da reta final do 1º turno (a partir de 15/9).
- `scripts/gerar_paginas_rn.py`: gera `rn.html` e `rn-apuracao.html` a partir das páginas nacionais. Rodar de
  novo sempre que `index.html` ou `apuracao.html` mudarem.
- Apuração: `python apuracao/coletor.py --corrida rn` (2º turno = eleição 6260, 167 arquivos por minuto).
- Mapa: `python scripts/gerar_mapa.py --rn <malha de municípios do IBGE>` → `painel/mapa-rn.js`.

## Estrutura

| Pasta | O quê |
|---|---|
| `dados/tse-1t/` | Arquivos oficiais do TSE do 1º turno, um por UF (`br` = Brasil, `zz` = exterior) |
| `dados/primeiro-turno-uf.json` | Resumo por UF gerado de `tse-1t/` (Lula, Flávio, outros, válidos, comparecimento) |
| `dados/pesquisas.json` | Pesquisas: última de cada instituto no 1º turno, todas do 2º turno, agenda a divulgar |
| `painel/` | `index.html`, `apuracao.html`, `balanco.html`, `rn.html`, `rn-apuracao.html`; `graficos.js` e `estilo.css` compartilhados |
| `apuracao/` | Apuração ao vivo: `coletor.py` (laço), `corridas.py` (as disputas), `modelo.py` (projeção e virada), `fontes.py` (TSE e simulador) |
| `scripts/` | `extrair_1t.py` (TSE → resumo) e `gerar_dados_js.py` (JSON → `painel/dados.js`) |

## Rotina para lançar uma pesquisa nova

1. Acrescentar a linha em `dados/pesquisas.json` → `segundo_turno` (e tirar de `segundo_turno_a_divulgar`).
2. `python scripts/gerar_dados_js.py`
3. Recarregar o painel.

## API de resultados do TSE

- Configuração: `https://resultados.tse.jus.br/oficial/comum/config/ele-c.json`
- Presidente 1º turno = eleição **6257**; 2º turno = **6258**.
- Resultado por UF: `https://resultados.tse.jus.br/oficial/ele2026/<eleicao>/dados/<uf>/<uf>-c0001-e00<eleicao>-u.json`
- Abstenção/andamento por UF: `.../dados/br/br-e00<eleicao>-ab.json`
- Os arquivos do 2º turno só existem a partir da totalização de 25/10.

## Método (e seus limites)

- **Votos válidos.** 1º turno: percentual ÷ (100 − indecisos/brancos/nulos). 2º turno: participação na soma dos dois.
- **Erro do instituto.** Vantagem Flávio − Lula na última pesquisa do 1º turno menos a vantagem real (+1,87).
- **Correção.** Devolve esse erro à vantagem do 2º turno. Instituto sem pesquisa de 1º turno na base usa o erro médio.
  Pressupõe que o viés se repete, o que não é garantido: parte do erro do 1º turno foi migração de última hora.
- **Média.** Última pesquisa de cada instituto, peso √amostra (teto 5.000) × e^(−dias/7).
- **Chance.** Normal com desvio = dispersão dos erros dos institutos no 1º turno. Estimativa grosseira, não previsão.

## Noite da apuração (25/10)

```
python apuracao/coletor.py
```

Abra `painel/apuracao.html` com duplo clique: a página recarrega sozinha a cada 10 s. O coletor lê as 28
UFs a cada 60 s (`--intervalo`), guarda o bruto do TSE em `apuracao/bruto-2t/` e para quando chegar a 100%.

Ensaio antes do dia, com uma noite fictícia (faixa laranja "SIMULAÇÃO" no painel):

```
python apuracao/coletor.py --simular                       # 1 s real = 1 min de apuração
python apuracao/coletor.py --simular --velocidade 2000     # noite inteira em segundos
python apuracao/coletor.py --simular --ate 110             # para às 18:50, para ver o meio da noite
python apuracao/coletor.py --simular --sim-transferencia 0.62 --sim-swing 0.01   # cenário de virada
```

### Modelo da apuração

- **Por UF.** Esperado = votos de Lula no 1º turno + `--transferencia` (padrão 0,5) dos votos dos demais candidatos.
- **Swing nacional.** Desvio médio entre o apurado e o esperado nas UFs com 5% ou mais de seções; corrige as UFs que contaram pouco.
- **Votos que faltam.** Total estimado da UF (apurado ÷ fração de seções) − apurado; a parcela de Lula mistura o observado na UF com esperado + swing.
- **Virada.** Avança a apuração no tempo no ritmo medido de cada UF (seções/min nos últimos 15 min) e marca quando o placar troca de líder.
- **Limite.** Dentro da UF, capitais chegam antes do interior. No ensaio com viés de capital de −4 p.p. no N/NE, a projeção subestimou Lula em ~1 p.p. no início e convergiu ao exato no fim.
- **Referência 2022** (imprensa, conferir): no 2º turno, Lula passou Bolsonaro com ~67,8% das seções, às 18h44.
