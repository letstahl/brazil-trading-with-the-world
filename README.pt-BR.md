[English](README.md) &nbsp;·&nbsp; Português

# Brazil Trading with the World

*Um case de analytics engineering: um pipeline automatizado e gratuito para os dados de
comércio exterior do Brasil, desde os arquivos brutos do governo até um modelo governado
no BigQuery e um dashboard em produção.*

[**Dashboard ao vivo**](https://lookerstudio.google.com/reporting/2f914270-3b2c-4ff2-b403-bb4942022449) &nbsp;·&nbsp; [Guia de instalação](SETUP.md) &nbsp;·&nbsp; [MIT](LICENSE)

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Cloud Run](https://img.shields.io/badge/Cloud%20Run-functions-4285F4?logo=googlecloud&logoColor=white)
![Cloud Scheduler](https://img.shields.io/badge/Cloud%20Scheduler-mensal-4285F4?logo=googlecloud&logoColor=white)
![BigQuery](https://img.shields.io/badge/BigQuery-star%20schema-4285F4?logo=googlebigquery&logoColor=white)
![Looker Studio](https://img.shields.io/badge/Looker%20Studio-relat%C3%B3rio-4285F4?logo=looker&logoColor=white)
[![Project Status: WIP](https://www.repostatus.org/badges/latest/wip.svg)](https://www.repostatus.org/#wip)

## Visão geral

A maioria dos dashboards de comércio exterior é construída da mesma forma: alguém baixa
um CSV manualmente, roda um script de limpeza local, reenvia pra alguma ferramenta de BI
e repete tudo isso no mês seguinte. Este projeto automatiza exatamente essa parte.

Uma rotina agendada busca os dados oficiais de comércio exterior do Brasil (Comex Stat /
MDIC) todo mês, carrega num star schema particionado no BigQuery, e um relatório no
Looker Studio lê direto do data warehouse. Ninguém precisa rodar script ou reenviar
arquivo. O dashboard é a camada de demonstração; o pipeline por trás dele é o real
assunto deste repositório.

Construído como referência replicável: o [guia de instalação](SETUP.md) foi escrito para
que o mesmo padrão, ingestão, orquestração, armazenamento e relatório, possa ser adaptado
a qualquer outro dataset público recorrente, usando inteiramente a camada gratuita do
Google Cloud.

## Arquitetura

```
Comex Stat (MDIC)  →  Cloud Run function (mensal)  →  BigQuery  →  Looker Studio
   CSVs brutos          download, limpeza, carga       star schema    relatório ao vivo
                              ↑
                       Cloud Scheduler
```

- **Ingestão**: uma Cloud Run function (Python) acionada via HTTP, disparada mensalmente
  pelo Cloud Scheduler. Ela baixa os arquivos de exportação/importação do ano corrente
  mais quatro tabelas de referência (país, estado, código NCM, hierarquia SH) e recarrega
  tudo a cada execução.
- **Armazenamento**: BigQuery, particionado por ano e clusterizado por estado/país, de
  forma que a atualização mensal toque só o ano corrente (ainda incompleto), nunca uma
  reescrita da tabela inteira.
- **Modelagem**: um conjunto de views SQL fica entre as tabelas brutas e o relatório,
  pré-unindo as dimensões, calculando métricas derivadas (concentração de mercado via
  HHI) e resumindo a nomenclatura alfandegária bruta em nomes de produto legíveis.
- **Relatório**: Looker Studio, conectado direto às views do BigQuery. Nenhuma lógica de
  blend vive dentro do próprio relatório.

## Modelo de dados

Star schema: uma tabela fato, quatro dimensões, três views de relatório por cima.

| Tabela | Granularidade | Notas |
|---|---|---|
| `f_trading` | ano × código NCM × estado × país parceiro | Particionada por ano, clusterizada por estado/país |
| `d_country`, `d_state`, `d_ncm`, `d_sh` | uma linha por entidade | Dados de referência, recarregados por completo a cada execução |
| `v_trading_enriched` | fato pré-unido com todas as dimensões | O que o relatório de fato consulta |
| `v_country_concentration` | uma linha por ano | Índice Herfindahl-Hirschman de concentração de parceiros exportadores |
| `v_top_partner_by_year` | uma linha por ano | Maior parceiro exportador e sua participação |

DDL completo em `sql/schema.sql`, `sql/sh2_labels.sql` e `sql/views.sql`.

## Stack técnica

| Camada | Ferramenta | Por quê |
|---|---|---|
| Fonte | Comex Stat (MDIC) | Oficial, pública, atualizada mensalmente, sem autenticação |
| Computação | Cloud Run functions (Python) | Serverless, a camada gratuita cobre essa carga por completo |
| Orquestração | Cloud Scheduler | Disparo mensal baseado em cron |
| Data warehouse | BigQuery | Star schema particionado, views SQL para a lógica de relatório |
| Relatório | Looker Studio | Camada gratuita, sem limite de licença por visual |

## Estrutura do repositório

```
sql/
  schema.sql        DDL do star schema
  sh2_labels.sql    nomes curtos curados para os 97 capítulos de produto HS2
  views.sql         views de relatório (enriquecimento, HHI, maior parceiro)
cloud_function/
  main.py           job de ingestão: download, limpeza, carga
  requirements.txt
design/
  backgrounds/      imagens de fundo do relatório e da landing page
SETUP.md            guia passo a passo de implantação
LICENSE             MIT
```

## Primeiros passos

Veja o [SETUP.md](SETUP.md) (em inglês) para o passo a passo completo: criação do
projeto no GCP, deploy da Cloud Run function, agendamento da execução mensal, backfill do
histórico e conexão do Looker Studio.

## Dados

Fonte: [Comex Stat](https://www.gov.br/mdic/pt-br/assuntos/comercio-exterior/estatisticas/base-de-dados-bruta),
Ministério do Desenvolvimento, Indústria, Comércio e Serviços (MDIC). Dado público e
aberto, atualizado mensalmente, sem necessidade de autenticação.

## Licença

[MIT](LICENSE)

---

**Status**: v0.1, em desenvolvimento ativo. O pipeline está implantado e rodando no
agendamento previsto; o relatório no Looker Studio ainda está sendo refinado (estilo,
métricas adicionais). Espere mudanças estruturais no layout do dashboard antes de uma
primeira versão estável.
