# 004 — Clima nas praias (Ubatuba)

> **Aposentado em 03/11/2026.** O app público saiu da Vercel e o robô saiu do
> ar pela migration
> [20261103023000_aposenta_robo_004](../../supabase/migrations/20261103023000_aposenta_robo_004.sql):
> sem disparo no `pg_cron`, `flg_ativo = false` (fora do hub e do vigia) e sem
> leitura pública do `painel_praias`. O workflow está desativado no GitHub.
> Histórico e tabelas continuam no banco. O texto abaixo descreve o robô como
> funcionava.

Ranqueia 15 praias de Ubatuba por **chance de sol**, dia a dia, de amanhã até a
próxima terça-feira. Mostra o ranking no terminal (`rich`), gera um
`saida/ranking.html` que abre no celular e grava tudo em
`public.previsao_praias` no Supabase (`id_carga = 4`).

**App online: https://praias-ubatuba.vercel.app** (público, sem login). A página
é estática e lê o pacote que o robô grava em `public.painel_praias` a cada
execução: atualiza sozinha, sem redeploy.

Roda no **GitHub Actions** todo dia às 05:00 de São Paulo (08:00 UTC),
disparado pelo `pg_cron` do Supabase
([workflow](../../.github/workflows/robo_004_clima_praias.yml),
[cadastro](../../supabase/migrations/20261028134551_cadastro_robo_004.sql)).

## Como rodar

```powershell
$py = "C:\Users\ferna\AppData\Local\Python\bin\python.exe"
& $py -m pip install -r requirements.txt                       # uma vez (traz o rich)
& $py automacoes\004_clima_praias\004_clima_praias.py --dry-run  # terminal + HTML, sem Supabase
& $py automacoes\004_clima_praias\004_clima_praias.py --status   # periodo e configuracao, sem rede
start automacoes\004_clima_praias\saida\ranking.html
```

Execução real (grava no Supabase e registra a carga): `$env:MODO_EXECUCAO = "CLOUD"`
e rodar sem flag. No Actions, o `ranking.html` fica anexado ao run como
artifact `ranking-praias` (7 dias).

## Fluxo

1. Lê `data/praias_ubatuba.json` (nome, região, lat/lon)
2. Período: de amanhã até a próxima terça (numa terça, vai até a terça seguinte), em dias de São Paulo
3. **Uma requisição** à Open-Meteo com todas as coordenadas separadas por vírgula,
   dados horários e `timezone=America/Sao_Paulo` (3 tentativas, 20 s; 4xx estoura na hora)
4. Score por praia e dia ([src/score.py](src/score.py)), ranking no terminal e HTML
5. Upsert em `public.previsao_praias` por `(cidade, dia, praia)`
6. `SUCCESS` com `mensagem` = melhor e pior praia de amanhã e `qtd_itens` = linhas gravadas

## Score de sol (0–100)

Só no horário de praia: horas 9 a 16 (janela 9h–17h); manhã = 9–12, tarde = 13–16.

| Componente | Peso | Nota cheia | Nota zero |
|---|---|---|---|
| Probabilidade de chuva | 40% | 0% | 100% |
| Nebulosidade | 35% | 0% | 100% |
| Chuva em mm/h | 15% | 0 mm | ≥ 2 mm |
| Vento | 10% | ≤ 10 km/h | ≥ 30 km/h |

Score do dia = média das horas. Cores: **verde ≥ 70** (sol), **amarelo ≥ 45**
(nublado), **vermelho** abaixo (chuva). Céu 100% fechado, sem chuva e sem
vento dá 65: amarelo de propósito.

## Decisões

- **Grupo de previsão (A, B, C...).** A Open-Meteo usa modelos globais com
  grade de ~10–25 km. Em 28/10/2026 as 15 praias receberam só **5 previsões
  distintas**: Picinguaba (A) · Almada, Puruba (B) · Itamambuca, Vermelha do
  Norte e todo o centro menos Toninhas (C) · Toninhas, Enseada (D) · Lázaro,
  Domingas Dias, Lagoinha, Maranduba (E). Mesma letra = mesma previsão, então
  empate entre elas não é diferença real. O grupo sai da série de valores, não
  da lat/lon devolvida pela API: o `best_match` mistura modelos de grades
  diferentes, e a lat/lon dele mostrava 3 pontos para a cidade toda.
- **Sem trava diária.** A previsão melhora ao longo do dia, e o destino é upsert:
  rodar de novo (botão "Rodar agora") só troca pela previsão mais nova.
- **Coordenadas do OpenStreetMap.** Centro do polígono `natural=beach` de cada
  praia, consultado no Nominatim em 28/10/2026. Há duas "Praia da Almada" no
  OSM; a usada é a do norte, vizinha do Ubatumirim (a outra, perto do Prumirim,
  parece erro de cadastro).
- **Regiões como pedidas.** Enseada está em "sul", mas fica colada em Toninhas
  (centro) e recebe a mesma previsão dela.
- **Página em template.** O `ranking.html` sai de
  [src/templates/ranking.html](src/templates/ranking.html) (CSS, gráficos em SVG
  e interação, sem biblioteca externa); o `report.py` só injeta o JSON
  (`dados_pagina`). Mostra a semana em blocos, o ranking do dia por grupo de
  previsão e gráficos hora a hora (6h–19h) do grupo escolhido: chance de chuva,
  mm, nuvens, temperatura, vento e UV, com o horário de praia sombreado.
- **Mapa "Onde vai chover".** Segunda requisição à Open-Meteo com uma grade de
  117 pontos (área e passo em `mapa` no JSON da cidade, 0,05° ≈ 5 km),
  `cell_selection=nearest` para o mar não virar terra. Mostra mm ou chance de
  chuva por hora (6h–19h), com controle de horário e animação, ligado aos
  gráficos. É **previsão de modelo, não radar**: radar só existe para o agora.
  Se essa consulta falhar, a página sai sem o mapa e o resumo do hub ganha
  "(sem mapa)"; o ranking já gravado não cai por causa dela. Fundo da Esri
  (Gray Canvas) porque OSM e CARTO recusam a página aberta de arquivo local.
  Abrir com `ranking.html?dia=N` vai direto ao dia N (0 = amanhã).
- **App na Vercel lendo do Supabase (28/10/2026).** O repositório é privado,
  então GitHub Pages não serve no plano gratuito. Em vez de redeploy diário (que
  pediria token da Vercel no Actions), o robô grava o JSON da página em
  `public.painel_praias` ([migration](../../supabase/migrations/20261028140943_painel_praias_publico.sql)),
  com **leitura pública** (é só previsão do tempo) e escrita só pela
  `service_role`; a página publicada em `web/` busca esse JSON com a chave
  publicável, a mesma do hub. Redeploy só quando o template mudar:

  ```powershell
  & $py automacoes\004_clima_praias\004_clima_praias.py --site   # gera web/index.html
  cd automacoes\004_clima_praias\web; vercel deploy --prod       # projeto praias-ubatuba
  ```
- **Módulos separados** (`src/fetch.py`, `src/score.py`, `src/report.py`) mesmo
  com menos de 400 linhas, ao contrário do padrão: a ideia é o painel web (mapa,
  radar, outras cidades) reaproveitar coleta e cálculo. Outra cidade = outro
  `data/praias_<cidade>.json`; a tabela já tem a coluna `cidade`.
- **05:00 de SP.** Hora livre antes do vigia, com a rodada 00 UTC dos modelos já
  publicada.

## Configuração

Só os secrets padrão (`SUPABASE_URL`, `SUPABASE_KEY` com a `service_role`,
`TELEGRAM_*` opcionais). A Open-Meteo é gratuita e sem chave. Tabela em
[20261028134535_previsao_praias.sql](../../supabase/migrations/20261028134535_previsao_praias.sql):
RLS ligada, escrita revogada de `anon`/`authenticated`, leitura para o leitor do hub.

## Estado (28/10/2026)

- `--dry-run` e `--status` ok; execução local com `MODO_EXECUCAO=CLOUD` gravou
  90 linhas (15 praias × 6 dias) e o pacote do app, e o robô aparece `OK` na `vw_saude_robos`.
- Migrations aplicadas e salvas no repositório; job `robo_004_clima_praias` no `pg_cron`.
- App publicado em https://praias-ubatuba.vercel.app, conferido no navegador
  (dados do Supabase, mapa e CSP ok); leitura anônima de outras tabelas segue bloqueada.

## Estado (03/11/2026)

- Aposentado: projeto `praias-ubatuba` excluído da Vercel, workflow desativado
  no GitHub e migration de aposentadoria no repositório.
