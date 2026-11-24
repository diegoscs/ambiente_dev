# Levantamento de impacto: migração Supabase (DM + Clientes)

Levantamento feito em 22/11/2026, **só leitura**: nenhum banco, secret, variável
ou código foi alterado. Fontes: repositórios `ambiente_dev`, `financas-app`,
`estoque-tattoo`, `daily-log`, `financas-pipeline` (arquivado), as pastas locais
`projetos/`, `clientes/` e `arquivo/`, consultas de leitura nos dois bancos
(catálogo, `pg_stat`, `cron.job`, nomes no Vault, contagem do Auth), a lista de
schemas expostos na Data API e os nomes das variáveis na Vercel e nos secrets do
GitHub. Nenhum valor de chave aparece aqui.

> Este repositório é público. O relatório cita nomes de tabelas, secrets e
> arquivos, nunca valores, e-mails ou IDs de conta.

Nomes usados abaixo: **FP** = financas-pipeline (`mthipdxpedlfnkzddlar`, vira o
DM); **OF** = projeto OpenFinance (`cjpgijunmpupvusppyij`); **CL** = projeto
Clientes (novo).

---

## 1. Resumo

O plano funciona, mas três pontos quebram a etapa 1 e a etapa 2 do jeito que estão
escritas:

1. **A conta do financas-app tem o mesmo e-mail da conta do hub no FP**, com
   outro ID. "Copiar a conta com o mesmo ID" bate na unique de e-mail do Auth. O
   caminho seguro é manter a conta que já existe no FP e trocar o `usuario_id`
   dos dados do openfinance (e o dono dos 573 arquivos do bucket) para ela.
   Apagar a conta do FP leva junto, por cascade, o acesso ao hub.
2. **O FP já tem um schema `openfinance`** (o antigo de 30/09, com dados em
   `contas`, `categorias` e `regras_categoria`) e o bucket `openfinance-bronze`
   com as mesmas policies de storage. A migration do financas-app usa
   `create schema if not exists` e `create policy` sem `if not exists`: ou falha
   ou mistura o antigo com o novo. O antigo precisa sair **na etapa 1**, não na 4.
3. **As migrations nos repositórios não reproduzem os bancos de produção.** No
   OF, a tabela `diagnostico_pluggy` só existe no banco (a migration não está no
   repo). No FP, a `produto_unico_por_categoria` do estoque foi aplicada mas não
   está registrada no histórico. E as triggers `ajustar_quantidade` em
   `compra_itens` e `usos` somam de novo a quantidade se os dados forem copiados
   com elas ligadas. Recriar a partir de um dump do schema (e copiar os dados com
   as triggers desligadas) é mais seguro que rodar as migrations.

Outros pontos de atenção: o OF guarda arquivos no Storage (573 JSON crus do
Pluggy, que o `pg_dump` não leva); a mudança de schema da etapa 4 exige mexer na
`lib_dscs` e republicar a VM; o `openfinance` não está exposto na Data API do FP.

---

## 2. Tabela de impacto

Risco: **A** alto (para algo em produção ou perde dado), **M** médio (quebra
algo secundário ou tem contorno fácil), **B** baixo (documentação, limpeza).

### Etapa 0: robô 005 de backup

| Onde | O que referencia | O que quebra | Ação necessária | Risco |
|---|---|---|---|---|
| Secret `SUPABASE_DB_URL` (ambiente_dev), usado em [config_robo.py:46](../automacoes/002_check_supabase/config_robo.py#L46) | Pooler em modo *transaction* (porta 6543, [README do 002](../automacoes/002_check_supabase/README.md)) | `pg_dump` não funciona bem pelo pooler transacional; a conexão direta `db.<ref>.supabase.co` é só IPv6 e o runner do Actions não tem IPv6 | Secret próprio do backup com a string do **Session pooler** (porta 5432 no host do pooler) | A |
| Runner `ubuntu-latest` | Postgres 17 nos dois bancos | `pg_dump` mais velho que o servidor se recusa a rodar | Instalar `postgresql-client-17` no workflow | M |
| Bucket `openfinance-bronze` no OF (573 objetos, o mais novo de hoje) | JSON cru do Pluggy, gravado em [sync-openfinance.mts:305](https://github.com/diegoscs/financas-app/blob/main/scripts/sync-openfinance.mts#L305) | `pg_dump` não copia arquivos do Storage | Backup do Storage à parte (ou decisão explícita de não guardar) | M |
| Vault do FP (`github_dispatch_token`) | Lido por `private.disparar_workflow` | O dump leva o segredo cifrado; a chave fica fora do banco, então um restore em outro projeto não decifra | Anotar que, num restore, o token é recriado à mão no Vault | M |
| Repositório `ambiente_dev` | Público | Artefato ou release com dump, mesmo cifrado, fica visível para qualquer um | Destino fora do GitHub (Drive/R2, como no diagrama) e senha num secret; nunca anexar ao run | A |
| [config.py:25](../lib_dscs/config.py#L25) `PREFIXOS_AMBIENTE` | Lista branca de variáveis do `.env` | Secret com prefixo novo (`BACKUP_`, `R2_`, `GDRIVE_`) não chega ao robô | Incluir o prefixo novo na lista | B |
| `public.controle_cargas` | Cadastro do robô | Sem a linha `id_carga = 5`, o registro falha e o robô não aparece no hub | Migration de cadastro com `workflow`, `tempo_min` e `atraso_max_horas`, e job no pg_cron | B |

### Etapa 1: renomear FP → DM, trazer o openfinance, pausar o OF

| Onde | O que referencia | O que quebra | Ação necessária | Risco |
|---|---|---|---|---|
| Auth do FP x Auth do OF | A conta do dono no FP (hub, `perfil`, finanças antigas, openfinance antigo) e a conta única do OF têm **o mesmo e-mail e IDs diferentes** | Inserir a conta do OF com o ID dela viola a unique de e-mail; apagar a do FP dispara cascade em `private.hub_leitores` (perde o hub), `perfil` e nas finanças antigas | Manter a conta do FP. Na cópia, trocar `usuario_id` em `openfinance.contas`, `categorias`, `regras_categoria` e `diagnostico_pluggy` para o ID do FP. As outras tabelas seguem pelas policies via `conta_id` | A |
| `storage.objects` do OF | `owner_id` = conta do OF nos 573 arquivos; policy `openfinance_bronze_select` filtra por dono | Depois da troca de ID, a conta não lê os arquivos antigos (o sync só grava, então o sync não para) | Ao copiar os arquivos, gravar com o dono novo ou atualizar o `owner_id` | M |
| Schema `openfinance` no FP | Antigo de 30/09: `contas` (4), `categorias` (16), `regras_categoria` (96), resto vazio; migrations `openfinance_01..04` no histórico | [20261002170632_schema_openfinance.sql:17](https://github.com/diegoscs/financas-app/blob/main/supabase/migrations/20261002170632_schema_openfinance.sql#L17) faz `create schema if not exists` e `create table`: falha ou mistura com o antigo | Exportar e apagar (ou renomear para `openfinance_antigo`) **antes** de trazer o novo | A |
| Bucket `openfinance-bronze` e policies `openfinance_bronze_insert/select` no FP | Criados pelo openfinance antigo (bucket vazio) | A migration do financas-app (linhas 238 a 244) faz `insert` no bucket e `create policy`: erro de duplicado | Apagar bucket e policies antigos junto com o schema antigo | M |
| Repo `financas-app`, `supabase/migrations/` | 4 migrations | Falta a `20261011202357_diagnostico_pluggy`, aplicada só no banco do OF; quem recriar pelo repo fica sem a tabela que o script de diagnóstico usa | Trazer a migration para o repo antes, ou recriar pelo dump do schema | M |
| Data API do FP | Schemas expostos hoje: `public`, `graphql_public`, `estoque` | Sem `openfinance` na lista, todas as consultas do financas-app voltam 406 ([supabase.ts:19-25](https://github.com/diegoscs/financas-app/blob/main/src/lib/supabase.ts#L19-L25)) | Adicionar `openfinance` em Exposed schemas no DM | A |
| Vercel `financas-app` | `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` (só Production) | O app continua no OF até a troca, e para quando o OF pausar | Trocar as duas e fazer Redeploy (variável `NEXT_PUBLIC_*` entra no build) | A |
| GitHub `financas-app`: [sync-openfinance.yml:88-91](https://github.com/diegoscs/financas-app/blob/main/.github/workflows/sync-openfinance.yml#L88-L91) e `diagnostico-pluggy.yml` | Secrets `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `FINANCAS_EMAIL`, `FINANCAS_SENHA` | O sync das 06:00 e das 15:00 grava no OF até a troca; depois da pausa, falha | Trocar URL e chave. `FINANCAS_SENHA` passa a ser a senha da conta do **DM** (pode ser diferente da do OF) | A |
| GitHub `financas-app`: secrets `HUB_SUPABASE_URL`, `HUB_PUBLISHABLE_KEY`, `HUB_LOG_TOKEN` | RPC `public.registrar_execucao_carga` e `public.notificar_hub_externo` no FP | Nada: o hub já está no FP, que continua com a mesma URL | Nenhuma agora. Depois da etapa 1, `HUB_SUPABASE_URL` e `SUPABASE_URL` apontam para o mesmo projeto (dá para simplificar mais tarde) | B |
| `.env.local` em `projetos/financas-app` | `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `FINANCAS_EMAIL`, `FINANCAS_SENHA` | Rodar o app ou os scripts no PC continua usando o OF | Trocar junto | B |
| Docs do financas-app: `CLAUDE.md:14-15`, `README.md:13`, `README.md:53`, `README.md:107`, `docs/SETUP.md:6`, `.env.example:3` | Projeto OF como banco do app | Instrução errada para quem for mexer | Atualizar para DM | B |
| OF pausado | Plano grátis | Projeto grátis pausado por mais de 90 dias não volta pelo painel (só o download do backup) | Tratar a pausa como "apagar em 90 dias": exportar dados e Storage antes | M |
| pg_cron do FP: `robo_003_sync_manha` (09:00 UTC) e `robo_003_sync_tarde` (18:00 UTC) | Disparam `sync-openfinance.yml` no financas-app | Sync roda no meio da migração e grava no banco errado | Desligar `OPENFINANCE_ENABLED` (variável do repo) durante a cópia e ligar depois da troca dos secrets | M |
| Nome do projeto FP → DM | URL e chaves ficam iguais | Nada no código (todos usam o ref ou a URL). Só textos | Atualizar o nome em [CLAUDE.md:53](../CLAUDE.md#L53) e no [README do 002](../automacoes/002_check_supabase/README.md) | B |

### Etapa 2: criar o Clientes e mudar o estoque

| Onde | O que referencia | O que quebra | Ação necessária | Risco |
|---|---|---|---|---|
| Plano grátis da Supabase | FP + OF ativos | Projeto grátis tem limite de projetos ativos por dono, somando as orgs: o CL só cabe depois do OF pausado | Manter a ordem: etapa 1 completa (OF pausado) antes de criar o CL | M |
| `estoque.compra_itens` e `estoque.usos`: trigger `ajustar_quantidade` (AFTER INSERT/UPDATE/DELETE) | Soma ou subtrai em `estoque.produtos.quantidade` | Copiar `produtos` com a quantidade atual e depois inserir compras e usos soma tudo de novo: estoque errado para a cliente | Copiar com as triggers desligadas (`session_replication_role = replica`, ou `disable trigger`) e conferir as quantidades contra o FP no fim | A |
| FKs para `auth.users` em `acessos` (cascade), `produtos`, `compras`, `compra_itens`, `usos`, `ganhos`, `pagamentos` (set null) | IDs das 2 contas do estoque | Dados copiados antes das contas falham na FK; contas com ID novo deixam `usuario_id` órfão e cortam o acesso (`estoque.tem_acesso()` usa `acessos.usuario_id = auth.uid()`) | Copiar `auth.users` **e** `auth.identities` das 2 contas com os mesmos IDs antes dos dados | A |
| Repo `estoque-tattoo`, `supabase/migrations/` | 7 migrations | No FP, a `20261118120000_produto_unico_por_categoria` está aplicada (índice `produtos_nome_por_categoria` existe) mas não está no histórico. O banco ainda tem uma versão antiga sobrando de `salvar_compra` (5 parâmetros) e a função `salvar_tatuagem` | Recriar o schema no CL pelo dump do `estoque` do FP, ou rodar as 7 migrations e comparar o catálogo (funções, índices, policies) antes de copiar dados | M |
| Clone local `clientes/estoque-tattoo` | Parado no PR #8 | Não tem a migration `20261122190034_pagamentos_parcelados` (PR #9) | `git pull` antes de usar as migrations | B |
| Vercel `estoque-tattoo` | `NEXT_PUBLIC_SUPABASE_URL` e `NEXT_PUBLIC_SUPABASE_ANON_KEY` em **Production, Preview e Development** | A troca só em Production deixa as prévias de PR no banco antigo (e vice-versa) | Trocar nos três ambientes, ou decidir usar Preview para testar o CL antes, e fazer Redeploy | A |
| Data API do CL | App usa `db: { schema: 'estoque' }` ([supabase.ts:18](https://github.com/diegoscs/estoque-tattoo/blob/main/src/lib/supabase.ts#L18)) | Sem `estoque` exposto, o app mostra "schema estoque não exposto" ([dados.tsx:74](https://github.com/diegoscs/estoque-tattoo/blob/main/src/lib/dados.tsx#L74)) | Expor `estoque` no CL | A |
| RPC `estoque.salvar_compra` e `estoque.salvar_ganho` ([dados.tsx:301](https://github.com/diegoscs/estoque-tattoo/blob/main/src/lib/dados.tsx#L301), [dados.tsx:317](https://github.com/diegoscs/estoque-tattoo/blob/main/src/lib/dados.tsx#L317)) | Funções no schema | Sem as funções, comprar e lançar ganho param | Vêm no dump ou nas migrations; testar uma compra e um ganho logo depois | M |
| Sessões abertas no celular da cliente | Token do FP | Depois da troca, a sessão antiga não vale no CL: a cliente cai na tela de login | Avisar a cliente e combinar o horário | M |
| Auth do CL | SMTP padrão da Supabase | Recuperar senha usa o e-mail padrão, com limite baixo de envios | Configurar o SMTP próprio antes de liberar | M |
| `estoque-tattoo`: `.env.example:1-4`, `.env.local:1`, `CLAUDE.md:10-19`, `README.md:42`, `README.md:117`, `supabase/migrations/20261112132934_schema_estoque.sql:3`; `.devcontainer/devcontainer.json` copia o `.env.example` | Ref do FP, "projeto do hub" | Codespace novo nasce apontando para o FP; a documentação manda mexer no banco errado | Atualizar para o CL | B |
| Memória do assistente (fora do repo) | "estoque no Supabase do hub" | Instrução velha em sessões futuras | Atualizar depois da migração | B |

### Etapa 3: keepalive, backup e saúde do Clientes

| Onde | O que referencia | O que quebra | Ação necessária | Risco |
|---|---|---|---|---|
| [config_robo.py:37-46](../automacoes/002_check_supabase/config_robo.py#L37-L46) e [ping.py:30-79](../automacoes/002_check_supabase/ping.py#L30-L79) | Um projeto só: `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_DB_URL` | Não pinga o CL; o CL pausa depois de ~7 dias sem uso (se a cliente passar uma semana sem abrir) | Lista de alvos no 002 e secrets novos do CL com prefixo `SUPABASE_` (já na lista branca), ex.: `SUPABASE_CLIENTES_URL`, `SUPABASE_CLIENTES_KEY`, `SUPABASE_CLIENTES_DB_URL` | M |
| [ping.py:56](../automacoes/002_check_supabase/ping.py#L56) | Ping REST em `controle_cargas` | Essa tabela não existe no CL (e o `public` dele pode nem estar exposto) | No CL, pingar uma tabela do `estoque` com `Accept-Profile: estoque`, ou um RPC próprio de ping | M |
| Registro no hub | `lib_dscs` grava sempre no `SUPABASE_URL` | Se o robô trocar `SUPABASE_URL` para o CL, o status vai para o lugar errado | Variáveis separadas: as do hub continuam `SUPABASE_URL`/`SUPABASE_KEY` | M |
| Robô 006 (saúde do CL) | Novo | Ainda não existe | Cadastro em `controle_cargas` e job no pg_cron do DM | B |
| Disparo pelo pg_cron do DM | `private.disparar_workflow` + `github_dispatch_token` no Vault | Os robôs do CL dependem do DM acordado e do token válido | O PAT precisa de `Actions: read/write` no `ambiente_dev`. Anotar a data de validade do PAT | M |

### Etapa 4: limpeza, schemas por assunto e bot do Discord

| Onde | O que referencia | O que quebra | Ação necessária | Risco |
|---|---|---|---|---|
| [lib_dscs/supabase.py:66-81](../lib_dscs/supabase.py#L66-L81) | `/rest/v1/<tabela>` sem `Accept-Profile`/`Content-Profile` | Todos os robôs, o vigia e os monitores do Minecraft param de registrar (404) quando as tabelas saírem de `public` | Cabeçalho de schema por tabela na lib (ex.: `robos` para controle/histórico/notificações, `minecraft` para `minecraft_*`) e versão nova da lib | A |
| [ping.py:56](../automacoes/002_check_supabase/ping.py#L56) e [config_robo.py:49-60](../automacoes/002_check_supabase/config_robo.py#L49-L60) | REST direto em `controle_cargas`, cabeçalhos próprios | O keepalive falha e o projeto pode pausar | Mesmo cabeçalho de schema (ou usar a lib) | A |
| [apps/hub/index.html:401](../apps/hub/index.html#L401), [424-436](../apps/hub/index.html#L424-L436), [506](../apps/hub/index.html#L506), [528](../apps/hub/index.html#L528) | `rpc("hub_acesso")`, `from()` em `vw_saude_robos`, `historico_cargas`, `notificacoes_hub`, `vw_metricas_robos`, `vw_execucoes_diarias`, `minecraft_status`, `minecraft_eventos`, `minecraft_comandos` | Hub vazio ou com erro | `sb.schema('robos').from(...)` e `sb.schema('minecraft').from(...)`; manter `hub_acesso` onde o hub chama | A |
| [apps/hub/api/rodar.js:18](../apps/hub/api/rodar.js#L18) | `/rest/v1/controle_cargas` | Botão "rodar" do hub responde 403 ("sem acesso") | Cabeçalho `Accept-Profile: robos` | M |
| [apps/minecraft/hub/api/_comum.js:30-36](../apps/minecraft/hub/api/_comum.js#L30-L36), [estado.js:102-110](../apps/minecraft/hub/api/estado.js#L102-L110), [ligar.js:40](../apps/minecraft/hub/api/ligar.js#L40), [52](../apps/minecraft/hub/api/ligar.js#L52), [71](../apps/minecraft/hub/api/ligar.js#L71) | `minecraft_*` em `public` | server-galera sem dados; ligar a VM não registra | Cabeçalho de schema em `supa()` | M |
| VM (`/opt/monitor`): [monitor_vm.py](../apps/minecraft/gcp/vm/monitor_vm.py) via cópia da `lib_dscs` | `minecraft_status`, `_eventos`, `_comandos`, `_sessoes`, `_jogadores`, `_desempenho`, `_backups` | A VM só recebe lib nova pelo [publicar_vm.ps1](../apps/minecraft/gcp/publicar_vm.ps1) com a VM ligada; sem isso, o monitor para de gravar | Mover o Minecraft só **depois de 16/01/2027** (VMs desligadas de vez), ou republicar as duas VMs no mesmo dia | M |
| [monitor_minecraft.py](../apps/minecraft/monitor/monitor_minecraft.py) (PC) | Mesmas tabelas pela lib | Igual à VM, se ainda for usado | Confirmar se ainda roda (não há tarefa agendada no Windows hoje) | B |
| `private.minecraft_status_carimbo` (trigger em `public.minecraft_status`) | Tabela | `alter table ... set schema` leva a trigger junto; nada a fazer se o corpo só usa `NEW` | Conferir depois de mover | B |
| `public.registrar_execucao_carga` e `public.notificar_hub_externo` (`search_path = public, private`) | `controle_cargas`, `historico_cargas`, `notificacoes_hub`, `private.tokens_carga` | O sync do financas-app chama `/rest/v1/rpc/registrar_execucao_carga` ([sync-openfinance.yml:69](https://github.com/diegoscs/financas-app/blob/main/.github/workflows/sync-openfinance.yml#L69), [155](https://github.com/diegoscs/financas-app/blob/main/.github/workflows/sync-openfinance.yml#L155)) e [hub.ts:43](https://github.com/diegoscs/financas-app/blob/main/src/lib/ingestao/pluggy/hub.ts#L43); com as tabelas fora de `public`, a função quebra; com a função fora de `public`, a URL precisa do `Content-Profile` | Atualizar o `search_path` (ou qualificar os nomes) e manter as duas funções onde estão, para o financas-app não mudar | A |
| Views `vw_saude_robos`, `vw_metricas_robos`, `vw_execucoes_diarias`, `vw_historico_legivel` e funções `fmt_quando`, `fmt_ha_quanto`, `fmt_duracao` | `controle_cargas`, `historico_cargas` | Movem junto; os grants para `authenticated` precisam ir junto | Migration com `set schema`, `grant usage on schema robos to authenticated` e os grants das views | M |
| Data API do DM | Hoje: `public`, `graphql_public`, `estoque` | `robos` e `minecraft` não expostos = 406 em tudo | Expor `robos` e `minecraft` antes de subir o código novo; tirar `estoque` depois da etapa 2 | A |
| `public.vw_ultima_execucao` | **Depende de `public.ingestion_log` (finanças antigas)**, não dos robôs | No diagrama ela está no schema `robos`; apagar `ingestion_log` derruba a view | Apagar junto com as finanças antigas (ninguém usa) | B |
| `public.previsao_praias`, `public.painel_praias` e o robô 004 | [004_clima_praias.py:47-53](../automacoes/004_clima_praias/004_clima_praias.py#L47-L53), [web/index.html:162](../automacoes/004_clima_praias/web/index.html#L162), [robo_004_clima_praias.yml](../.github/workflows/robo_004_clima_praias.yml) | Nada em produção (robô inativo desde 29/10; o painel não é um dos 4 projetos da Vercel) | Exportar, apagar as tabelas, o cadastro `id_carga = 4` e, se quiser, a pasta do robô e o workflow | B |
| Finanças antigas em `public` | Só o app arquivado [`financas-pipeline/web`](https://github.com/diegoscs/financas-pipeline) (não publicado na Vercel) | Rodar esse app no PC deixa de funcionar | Exportar e apagar (seção 4) | B |
| Bucket `bronze` no FP | 8 arquivos de 30/07 (pipeline antigo) | Nada | Exportar e apagar | B |
| Bot do Discord (Edge Function no DM) | `vw_saude_robos`, `historico_cargas` | Se as tabelas mudarem de schema depois do bot, ele quebra | Fazer o bot depois da troca de schema, já lendo `robos.*` | B |

---

## 3. Secrets e variáveis a trocar

Só nomes. "Igual" = continua apontando para o mesmo lugar.

### Etapa 0

| Lugar | Nome | Ação |
|---|---|---|
| GitHub `ambiente_dev` | (novo) string do Session pooler do DM, ex.: `SUPABASE_DB_URL_SESSAO` | criar |
| GitHub `ambiente_dev` | (novo) senha de criptografia do backup, ex.: `BACKUP_SENHA` | criar (prefixo em `PREFIXOS_AMBIENTE`) |
| GitHub `ambiente_dev` | (novo) credencial do destino (R2 ou Drive) | criar |
| GitHub `ambiente_dev` | (novo) acesso ao Storage do OF, se o backup dos arquivos for antes da etapa 1 | criar e apagar depois |

### Etapa 1

| Lugar | Nome | Ação |
|---|---|---|
| Vercel `financas-app` (Production) | `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` | trocar para o DM + Redeploy |
| GitHub `financas-app` | `SUPABASE_URL`, `SUPABASE_ANON_KEY` | trocar para o DM |
| GitHub `financas-app` | `FINANCAS_EMAIL` | igual (mesmo e-mail) |
| GitHub `financas-app` | `FINANCAS_SENHA` | senha da conta no DM |
| GitHub `financas-app` | `HUB_SUPABASE_URL`, `HUB_PUBLISHABLE_KEY`, `HUB_LOG_TOKEN` | igual |
| GitHub `financas-app` (variável) | `OPENFINANCE_ENABLED` | `false` durante a cópia, depois volta |
| `.env.local` em `projetos/financas-app` | `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `FINANCAS_SENHA` | trocar |
| `.env.local` em `arquivo/financas-openfinance/web` | `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` | arquivado, só se for rodar de novo |
| GitHub `ambiente_dev`, Vercel `hub-robos`, Vercel `server-galera`, VM | todos | igual (nome do projeto muda, URL e chaves não) |

### Etapa 2

| Lugar | Nome | Ação |
|---|---|---|
| Vercel `estoque-tattoo` (Production, Preview, Development) | `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` | trocar para o CL + Redeploy |
| `.env.local` e `.env.example` em `clientes/estoque-tattoo` | `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` | trocar (o `.env.example` é versionado e alimenta o devcontainer) |
| GitHub `estoque-tattoo` | nenhum secret hoje | nada |
| Auth do CL (painel) | SMTP (host, usuário, senha) | configurar |

### Etapa 3

| Lugar | Nome | Ação |
|---|---|---|
| GitHub `ambiente_dev` | (novos) `SUPABASE_CLIENTES_URL`, `SUPABASE_CLIENTES_KEY`, `SUPABASE_CLIENTES_DB_URL` | criar (002, 005 e 006) |
| GitHub `ambiente_dev` | `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_DB_URL` | igual (continuam sendo o DM/hub) |
| Vault do DM | `github_dispatch_token` | igual (conferir validade e acesso ao `ambiente_dev`) |

### Etapa 4

| Lugar | Nome | Ação |
|---|---|---|
| Painel do DM, Data API | Exposed schemas | incluir `robos`, `minecraft`; tirar `estoque` |
| Vault do DM | (novos) chaves do bot do Discord | criar |
| VM `/opt/monitor/.env` | `SUPABASE_URL`, `SUPABASE_KEY`, `DUCKDNS_TOKEN` | igual; só a lib muda (republicar), se as VMs ainda existirem |
| Vercel `server-galera` | `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `GCP_SA_KEY` | igual |
| Vercel `hub-robos` | `GH_DISPATCH_TOKEN` | igual (URL e chave pública estão fixas no código: [index.html:245-246](../apps/hub/index.html#L245-L246) e o fallback em [rodar.js:9-10](../apps/hub/api/rodar.js#L9-L10)) |

---

## 4. Tabelas antigas em `public` (FP)

Leitura por `pg_stat_user_tables` (as estatísticas não foram zeradas) e busca no
código de todos os repositórios e pastas locais.

| Tabela | Linhas | Último dado | Quem usa hoje |
|---|---|---|---|
| `transacoes` | 191 | 21/09 | ninguém em produção; app arquivado `financas-pipeline/web` |
| `contas` | 4 | — | idem; views `vw_conferencia_cartao`, `vw_patrimonio_mensal` |
| `faturas` | 6 | — | idem |
| `categorias` | 16 | — | idem; views `vw_fila_revisao`, `vw_fluxo_mensal` |
| `regras_categoria` | 96 | — | idem |
| `snapshots_saldo` | 21 | 01/10 | idem; views `vw_conferencia_cartao`, `vw_patrimonio_mensal` |
| `ingestion_log` | 16 | 23/09 | idem; view `vw_ultima_execucao` |
| `perfil` | 1 | — | app arquivado ([perfil.ts](https://github.com/diegoscs/financas-pipeline/blob/main/web/src/lib/perfil.ts)) |
| `usuarios` | 0 | — | ninguém |
| `ativos` | 1 | — | app arquivado (`carteira.ts`, `carteiraApi.ts`, `onboarding`) |
| `posicoes` | 1 | — | app arquivado (`carteira.ts`, `carteiraApi.ts`) |
| `proventos` | 2 | — | app arquivado (`carteira.ts`) |
| `investimentos_historico` | 1 | ref. 25/09 | app arquivado (`historicoApi.ts`) |
| `cotacoes` | 8 | 03/11 | app arquivado (`api/mercado/route.ts`, cache de cotação: a gravação de 03/11 veio dele rodando no PC) |
| `indices` | 11 | 30/10 | app arquivado (`api/mercado/route.ts`) |
| `previsao_praias` | 90 | 29/10 | robô 004 (inativo) |
| `painel_praias` | 1 | 29/10 | página estática do robô 004 (fora da Vercel) |
| Views `vw_conferencia_cartao`, `vw_fila_revisao`, `vw_fluxo_mensal`, `vw_patrimonio_mensal`, `vw_reconciliacao_mensal`, `vw_ultima_execucao` | — | — | ninguém no código ativo |

Nenhum workflow, robô, hub ou app publicado lê essas tabelas. O
`financas-app` usa só o schema `openfinance` (11 tabelas, todas com
`openfinance.` via `db.schema`). Antes de apagar: exportar (CSV ou dump do
schema), conferir que `ativos`/`posicoes`/`proventos`/`investimentos_historico`
não fazem falta no financas-app novo, e apagar as views primeiro.

Ficam no DM (não são legado): `controle_cargas`, `historico_cargas`,
`notificacoes_hub`, `vw_saude_robos`, `vw_metricas_robos`,
`vw_execucoes_diarias`, `vw_historico_legivel` e as 7 `minecraft_*`.

---

## 5. Perguntas para você

1. **Conta extra no Auth do FP.** Das 4 contas, uma é a sua (hub e finanças), duas
   são do estoque e **uma não está ligada a nada** (criada em 11/08, um login só).
   É de teste? Pode apagar?
2. **As duas contas do estoque**: as duas são do estúdio (ex.: tatuador e
   ajudante), ou uma é sua para suporte? No CL "nenhuma conta minha" vale também
   para suporte?
3. **Senha da conta no DM**: você lembra da senha da conta do hub? Ela vai virar o
   login do financas-app (o `FINANCAS_SENHA`). Se não, dá para redefinir antes.
4. **Openfinance antigo no FP**: as `regras_categoria` (96) e `categorias` (16) de
   lá têm algo que o novo (122 regras) não tem, ou pode descartar?
5. **Storage do OF** (573 JSON crus do Pluggy): quer levar para o DM, guardar só no
   backup, ou descartar?
6. **Exposed schemas**: conferi pela própria API que o DM expõe `public`,
   `graphql_public` e `estoque`. Não consegui ver as outras configurações da Data
   API do OF (limite de linhas, por exemplo); vale abrir o painel e copiar igual.
7. **Variáveis da Vercel**: o MCP da Vercel recusou listar (403); os nomes vieram
   do `vercel env ls` nas pastas ligadas. Nenhum valor foi lido. Falta confirmar
   se há variáveis em nível de time (não apareceram).
8. **Telegram**: os workflows passam `TELEGRAM_TOKEN`/`TELEGRAM_CHAT_ID`, mas
   esses secrets **não existem** no `ambiente_dev`. Hoje o alerta é só o e-mail
   do GitHub e o hub. É de propósito (já pensando no Discord)?
9. **Minecraft depois de 16/01/2027**: as tabelas `minecraft_*` ficam como
   histórico, ou exportar e apagar em vez de mover para um schema `minecraft`?
10. **Clientes e o plano grátis**: um app vendido em projeto grátis pausa após 7
    dias sem uso e não tem backup da Supabase. Ok manter grátis com o 002 e o 005
    cobrindo, até a primeira assinatura?

---

## 6. Sugestões de ajuste na ordem

1. **Levar a limpeza do `openfinance` antigo da etapa 4 para o começo da etapa 1.**
   É pré-requisito para trazer o novo (mesmo nome de schema, bucket e policies).
   No diagrama, "openfinance antigo de 30/09" está em "Sai do DM", mas sem
   etapa; ele precisa sair antes.
2. **Etapa 1 com remapeamento de conta, não cópia.** Trocar "copiar a conta do
   financas-app" por "trocar o `usuario_id` dos dados para a conta que já existe
   no DM". Ordem sugerida: backup → `OPENFINANCE_ENABLED=false` → apagar o
   openfinance antigo → criar o schema novo pelo dump do OF (inclui
   `diagnostico_pluggy`) → copiar dados com o ID trocado → copiar o Storage →
   expor `openfinance` → trocar secrets e Vercel → ligar o sync → conferir uma
   rodada → pausar o OF.
3. **Etapa 0 cobre também o Storage do OF**, ou pelo menos uma cópia única antes
   de pausar.
4. **Etapa 2 pelo dump do schema, não pelas migrations.** Depois, gerar no repo
   do estoque uma migration "base" que bata com o CL, para o histórico voltar a
   valer. Copiar os dados com as triggers desligadas e comparar
   `produtos.quantidade` linha a linha com o FP.
5. **Etapa 4 em duas partes.** (a) Limpeza (finanças antigas, praias, `estoque`,
   bucket `bronze`) pode vir logo depois da etapa 2: não mexe em nada vivo.
   (b) Mudança de schema dos robôs e do Minecraft precisa de PR coordenado
   (lib_dscs + hub + server-galera + 002 + RPCs) e, de preferência, depois de
   16/01/2027, quando a VM não precisar mais ser republicada. Uma opção para
   não quebrar nada no meio: mover as tabelas e deixar views de compatibilidade
   em `public` por algumas semanas.
6. **Ajustes no diagrama:**
   - `vw_ultima_execucao` não é dos robôs: depende de `public.ingestion_log` e
     sai junto com as finanças antigas.
   - A tabela do schema `openfinance` está certa (11 tabelas, incluindo
     `transacoes_pendentes` e `diagnostico_pluggy`).
   - A linha "Alertas: Telegram" do "Antes" não corresponde ao que existe: os
     secrets do Telegram não estão configurados.
   - Faltam os jobs do Minecraft no pg_cron (14/01 e 16/01 de 2027), que
     dependem do DM e do Vault até lá.
   - Falta o Storage: bucket `openfinance-bronze` vem para o DM; bucket `bronze`
     sai.
7. **Bot do Discord por último**, já lendo `robos.*`, para não ser reescrito.

---

## 7. Decisões e cronograma (24/11/2026)

Respostas às perguntas da seção 5 e ajustes aceitos da seção 6.

| # | Decisão |
|---|---|
| 1 | Senha da conta do hub: o dono troca e grava direto no secret `FINANCAS_SENHA` do financas-app |
| 2 | 4ª conta do Auth do FP (11/08, sem uso): apagar só depois do backup da etapa 0 restaurado com sucesso |
| 3 | Bucket `openfinance-bronze` do OF (573 arquivos): descartar; não vai para o DM nem para o backup. O sync volta a gravar no DM |
| 4 | Openfinance antigo do FP: comparado em 24/11 — as 16 categorias são iguais e as 96 regras estão todas no novo (que tem 122). Vai no backup e é descartado |
| 5 | Migrations com o schema na frente do nome (`robos_...`, `estoque_...`), sempre aplicadas pelo mesmo caminho. O CL já nasce assim |
| 6 | Auth do CL: e-mails com a marca neutra "Candido Digital" |
| 7 | Schema `plataforma` (clientes, produtos, assinaturas): fora da migração, só quando houver cobrança |
| 8 | Robôs e Minecraft saem de `public` só depois de 16/01/2027, num PR único |
| 9 | Token de disparo do pg_cron: conferir validade, aviso no vigia e reserva do keepalive pelo `schedule` do GitHub |
| 10 | Alertas: sem Telegram. Durante a migração, e-mail do GitHub; depois, só Discord |
| 11 | Cliente do estoque já avisado da troca |
| 12 | Backup: artifact de 30 dias no repo privado `backups-supabase`, sem criptografia, restore testado todo dia (ver o [README do 005](../automacoes/005_backup_supabase/README.md); substitui o plano de Drive + age) |

Ordem: limpeza do openfinance antigo no começo da etapa 1; schemas recriados a
partir do dump, não das migrations.

| Etapa | Previsto |
|---|---|
| 0 · Backup | 23 a 29/11 |
| 1 · OpenFinance → DM | 02 a 08/12 |
| Pausa (nenhuma mudança nos bancos) | 12 a 19/12 |
| 2 · Estoque → Clientes | 20 a 28/12 |
| 3 · Robôs cobrindo os dois | 04 a 06/01 |
| 4 · Limpeza (schemas depois de 16/01) | 09 a 23/01 |
