# 002 — Check Supabase (keepalive)

Impede que o projeto Supabase do plano free seja **pausado por inatividade**.
Toda execução faz uma consulta real no projeto por **dois caminhos** — conexão
Postgres e API REST (PostgREST) — e registra o resultado em
`dbo.controle_cargas` (`id_carga = 2`).

> Projeto alvo: **financas-pipeline** (`mthipdxpedlfnkzddlar`, sa-east-1).

## Por que dois pings

O Supabase mede atividade por componente: banco e API REST têm contadores
próprios. Pingar só um deixa dúvida se conta como atividade para o outro — os
dois juntos custam ~2 segundos e resolvem. Se **qualquer um** dos dois falhar
depois de 3 tentativas, a carga fecha como `ERROR`: metade da atividade não
garante o projeto acordado.

## Os dois modos

| `MODO_EXECUCAO` | Onde roda | Controle de carga |
|---|---|---|
| `LOCAL` (padrão) | Agendador do Windows | `dbo.controle_cargas` no Postgres `dm` + espelho no Supabase |
| `CLOUD` | GitHub Actions | sem Postgres local — grava a carga direto no Supabase |

O `CLOUD` é rede de segurança: se a máquina ficar desligada uma semana, o
Agendador não salva o projeto. O cron do workflow roda a cada 2 dias.

## Configuração

### 1. Variáveis no `.env` da raiz (`D:\ambiente_dev\.env`)

Modelo completo em [`.env.example`](../../.env.example):

```
MODO_EXECUCAO=LOCAL
SUPABASE_URL=https://mthipdxpedlfnkzddlar.supabase.co
SUPABASE_KEY=<service_role>
SUPABASE_DB_URL=postgresql://postgres.mthipdxpedlfnkzddlar:<senha>@aws-0-sa-east-1.pooler.supabase.com:6543/postgres
TELEGRAM_TOKEN=<@BotFather>
TELEGRAM_CHAT_ID=<getUpdates>
```

- **`SUPABASE_KEY` precisa ser a `service_role`** (Settings → API). A `anon`
  esbarra na RLS da tabela de controle, que não tem policy nenhuma de propósito.
- **`SUPABASE_DB_URL`** é a connection string do *Transaction pooler*
  (porta 6543), em Settings → Database.

### 2. Banco local

Rodar **como dono da tabela** (`postgres` — o `robo_app` não tem `ALTER`):

```powershell
psql -U postgres -d dm -f D:\ambiente_dev\automacoes\002_check_supabase\cadastro_carga.sql
```

Isso adiciona `flg_sincronizado`/`dta_sync` em `dbo.controle_cargas` e cadastra
o robô com `id_carga = 2`, `dias_semana = {1..7}` (**DIÁRIA**).

### 3. Tabela espelho no Supabase

Já criada em `public.controle_cargas` (migration `criar_espelho_controle_cargas`),
com RLS ligada e sem policy — só a `service_role` escreve.

## Como rodar na mão

```powershell
cd D:\ambiente_dev\automacoes\002_check_supabase
$py = "C:\Users\ferna\AppData\Local\Python\bin\python.exe"

& $py 002_check_supabase.py --status     # configuração e último resultado, sem pingar
& $py 002_check_supabase.py --dry-run    # ping de verdade, sem gravar nada
& $py 002_check_supabase.py              # execução normal
```

`--status` e `--dry-run` **não registram status** na tabela: são manutenção, e
marcar `SUCCESS` neles mentiria no monitoramento. Pelo `.bat` a saída vai para
`NUL` (ele usa `pythonw.exe`) — para ver na tela, chame `python.exe` direto.

## Fluxo

1. Reenvia pendências de espelhamento de execuções anteriores
2. `status_inicio` → `RUNNING`, `dta_ini=now()`, `dta_fim=NULL`
3. Ping Postgres (`select now()`) e ping REST — 3 tentativas cada, 20 s de espera
4. `status_sucesso` → `SUCCESS` (ou `status_erro` → `ERROR` + alerta no Telegram)
5. Espelha a linha no Supabase via upsert em `id_carga`

**Falha no passo 5 nunca derruba o robô**: a linha fica com
`flg_sincronizado = false` e a próxima execução reenvia. A tabela local é a
fonte da verdade.

## Log: só em caso de erro

As linhas ficam em memória e só viram arquivo se a execução falhar:
`temp\erro_002_check_supabase_20260915_204512.txt`. Um arquivo por falha, com
carimbo de hora. **Execução bem-sucedida não deixa rastro em disco.**

## Task Scheduler

O robô **não tem tarefa própria** desde 25/09/2026. Quem o chama é a tarefa
única [`ambiente_dev - Robos`](../README.md), disparada **a cada logon** com 3
minutos de atraso, através do [`iniciar_robos.bat`](../iniciar_robos.bat).

Antes era uma tarefa diária às 08:00, criada pelo
[`criar_tarefa.ps1`](criar_tarefa.ps1) — que ficou **obsoleto** e só continua na
pasta como registro da configuração antiga (S4U, `StartWhenAvailable`, admin).
Não rode mais esse arquivo: ele recria a tarefa das 08:00.

O atraso de 3 min do gatilho novo existe por causa deste robô: no logon a rede
ainda está subindo, e tanto o ping Postgres quanto o REST falhariam por
indisponibilidade em vez de por configuração.

> Continua valendo o aviso da seção anterior: a tarefa local **não** cobre o
> cenário que causou a pausa do projeto, que é a máquina desligada — e o gatilho
> de logon não muda isso, só troca "horário fixo" por "quando você usa o PC".
> Quem protege de verdade é o cron do GitHub Actions.

## GitHub Actions (modo CLOUD)

O workflow está em [`.github/workflows/supabase_keepalive.yml`](../../.github/workflows/supabase_keepalive.yml)
— `cron: "12 9 */2 * *"` (a cada 2 dias, 06:12 em São Paulo) + `workflow_dispatch`.

O repositório já existe: **`diegoscs/ambiente_dev`** (privado), com `origin`
apontado e **todo o código já publicado** — menos o workflow.

**Só o workflow ficou de fora, travado no scope do token.** Ele está isolado
no último commit local, justamente para o resto poder subir sem ele. Um PAT clássico com `repo` dá conta
do resto, mas **não** de gravar nada dentro de `.github/workflows/` — o GitHub
recusa no servidor:

```
! [remote rejected] main -> main (refusing to allow a Personal Access Token
  to create or update workflow `.github/workflows/supabase_keepalive.yml`
  without `workflow` scope)
```

A restrição vale também para a Contents API, então não há desvio: ou o token
ganha o scope, ou o arquivo não sobe. Em <https://github.com/settings/tokens>,
marcar **`workflow`** no mesmo token do `GITHUB_TOKEN` — é o do robô 001; se
preferir não ampliar o scope dele, um segundo token só para o push resolve.
Depois:

```powershell
cd D:\ambiente_dev
git push -u origin main
```

Feito o push, em **Settings → Secrets and variables → Actions**, criar os
secrets: `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_DB_URL`, `TELEGRAM_TOKEN`,
`TELEGRAM_CHAT_ID`. O `MODO_EXECUCAO=CLOUD` já está fixo no workflow.

> O `.env` está fora do commit — conferido com
> `git ls-files | Select-String "\.env$"`, que voltou vazio. Vale repetir a
> conferência antes de qualquer push futuro.

## Alerta no Telegram

Só em falha, e só quando a execução registra status (não em `--status`,
`--dry-run` ou `DEBUG`). O envio **nunca levanta exceção**: se o Telegram
estiver fora, vira linha de log — o robô já está tratando um problema e não
pode trocar a causa real por uma falha de notificação.

Implementação compartilhada em `lib_dscs/notificacao.py`
(`dl.alertar_erro_robo`), disponível para os próximos robôs.

## Estado atual — 21/09/2026

**O robô nunca executou, e o projeto chegou a ser pausado.** Escrito em 15/09,
o keepalive não rodou uma única vez — e em 21/09 o `financas-pipeline` foi
encontrado `INACTIVE`, exatamente o desfecho que ele existia para impedir. O
projeto foi restaurado no mesmo dia.

Nada disso apareceu como erro em lugar nenhum, e é a mesma lição do robô 001:
robô que não roda não escreve log, não muda status e não dispara alerta — o
silêncio dele é idêntico ao do sucesso. Aqui foi pior, porque a linha
`id_carga = 2` nem existe: não havia `dta_fim` velho para a consulta de atraso
encontrar.

### Pendências

- [ ] **Preencher o `.env` da raiz** com `SUPABASE_URL`, `SUPABASE_KEY`
      (a `service_role`, não a `anon`) e `SUPABASE_DB_URL` (pooler, porta 6543).
      É o primeiro bloqueio: sem eles o robô morre na `validar_configuracao`,
      antes de qualquer ping.
- [ ] **Rodar o [`cadastro_carga.sql`](cadastro_carga.sql) como `postgres`.**
      Hoje `dbo.controle_cargas` só tem `id_carga = 1`, e as colunas
      `flg_sincronizado`/`dta_sync` não existem — o espelhamento quebraria. O
      `robo_app` não serve: o dono da tabela é o `postgres`, e `ALTER` e `GRANT`
      pedem propriedade.
- [ ] **Dar o scope `workflow` ao token** e rodar `git push`: o arquivo do
      workflow é a única coisa que ficou de fora do repositório.
- [ ] **Cadastrar os cinco secrets** em *Settings → Secrets and variables →
      Actions*. Sem eles o workflow falha em toda execução do cron.

> A ordem importa: a tarefa local **não** cobre o cenário que causou a pausa,
> que é a máquina desligada. Quem protege de verdade é o cron do GitHub Actions;
> o Agendador é o complemento, não o contrário.

### Resolvido

- **Projeto restaurado** em 21/09/2026 — saiu de `INACTIVE`. É o que destrava
  o resto: com o projeto pausado, nem o `--dry-run` passa do ping Postgres.
- **Tarefa `002 - Check_Supabase` criada** em 21/09/2026, com `LogonType = S4U`
  e `StartWhenAvailable = True`. Primeira execução agendada para 22/09 às 08:00
  — ela vai **falhar** enquanto o `.env` e o `cadastro_carga.sql` não forem
  feitos, deixando `temp\erro_*.txt`. É esperado, e é melhor que o silêncio de
  antes.
- Repositório git inicializado na raiz em 21/09/2026, com `clientes/` e
  `pipelines/` no `.gitignore`: os dois têm `.git` próprio, e aninhar viraria
  submódulo sem ninguém ter pedido. Conferido que o `.env` ficou de fora.

## Arquivos

```
002_check_supabase\
├─ 002_check_supabase.py    main: controle de carga, orquestra o resto
├─ config_robo.py           constantes, leitura e validação do ambiente
├─ ping.py                  ping_postgres() e ping_rest() + retry
├─ sync_supabase.py         upsert no Supabase, pendências e modo CLOUD
├─ 002_check_supabase.bat   o que o Agendador chama
├─ cadastro_carga.sql       ALTER + INSERT do robô (rodar como postgres)
├─ criar_tarefa.ps1         cria a tarefa no Agendador (rodar como admin)
└─ README.md
```
