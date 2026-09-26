# 002 — Check Supabase (keepalive)

Impede que o projeto Supabase do plano free seja **pausado por inatividade**.
Toda execução faz uma consulta real no projeto por **dois caminhos** — conexão
Postgres e API REST (PostgREST) — e registra o resultado no próprio Supabase:
`public.controle_cargas` (última execução) e `public.historico_cargas` (uma
linha por execução), `id_carga = 2`.

> **Desde 26/09/2026 o robô roda no GitHub Actions, todo dia.** O Agendador do
> Windows segue em paralelo até a migração fechar. Ver
> [docs/migracao_nuvem.md](../../docs/migracao_nuvem.md).

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
| `CLOUD` | GitHub Actions (**o principal**) | só o Supabase |
| `LOCAL` (padrão) | Agendador do Windows | Supabase + `dbo.controle_cargas` no Postgres `dm` |

Nos dois modos o registro oficial é o Supabase, gravado pela
[`lib_dscs`](../../lib_dscs/README.md) (`dl.registrar_carga_supabase`). No
`LOCAL` a tabela do Postgres `dm` continua sendo atualizada, mas deixou de ser
copiada: até 25/09 o robô espelhava a linha local no Supabase com uma fila de
pendências (`sync_supabase.py`), que saiu na migração.

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

### 3. Tabelas no Supabase

`public.controle_cargas`, `public.historico_cargas` e a view
`public.vw_saude_robos`, versionadas em
[`supabase/migrations`](../../supabase/migrations). RLS ligada e sem policy:
só a `service_role` lê e escreve.

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

1. `RUNNING` no Supabase (e no `dm`, no modo `LOCAL`), `dta_fim=NULL`
2. Ping Postgres (`select now()`) e ping REST — 3 tentativas cada, 20 s de espera
3. `SUCCESS` + uma linha em `historico_cargas` com as latências e o link do run
4. Na falha: `ERROR` + histórico + alerta no Telegram

**Falha ao registrar nunca derruba o robô**: vira linha de log. Se o Supabase
inteiro estiver fora, o ping falha e o registro também; quem pega esse caso é o
run vermelho no Actions (o GitHub manda e-mail) e o `ATRASADO` da
`vw_saude_robos` no hub.

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

**No ar desde 25/09/2026.** O workflow está em
[`.github/workflows/robo_002_check_supabase.yml`](../../.github/workflows/robo_002_check_supabase.yml)
— `cron: "12 9 * * *"` (todo dia, 06:12 em São Paulo) + `workflow_dispatch`.
Até 26/09 ele se chamava `supabase_keepalive.yml` e rodava a cada 2 dias.

Primeira execução disparada na mão em 25/09 às 17:20 UTC: **sucesso**, e a linha
`id_carga = 2` apareceu em `public.controle_cargas` com `SUCCESS` e os carimbos
batendo com o run. É a prova de que o modo CLOUD funciona sem o Postgres local.

Secrets cadastrados em *Settings → Secrets and variables → Actions*:
`SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_DB_URL`. Os dois do Telegram **não**
foram criados — secret ausente vira string vazia, e o robô só registra
"não configurado". Não quebra o workflow; só não há alerta se a nuvem falhar.

### O que travava o push, e por quê

Um PAT clássico com `repo` dá conta de tudo, **menos** de gravar dentro de
`.github/workflows/`. O GitHub recusa no servidor:

```
! [remote rejected] main -> main (refusing to allow a Personal Access Token
  to create or update workflow `.github/workflows/supabase_keepalive.yml`
  without `workflow` scope)
```

A restrição vale também para a Contents API, então não havia desvio: ou o token
ganhava o scope, ou o arquivo não subia. Resolvido marcando **`workflow`** no
mesmo token do `GITHUB_TOKEN` em <https://github.com/settings/tokens> — editar
os scopes **não muda o valor do token**, então o `.env` não precisou de nada.

> Segunda pegadinha, essa não documentada antes: o `credential.helper` daqui é o
> `manager`, e **não havia credencial do GitHub guardada**. Com o scope já
> concedido, o `git push` ainda parava num prompt de usuário/senha que pode
> passar despercebido — dá para achar que o push foi feito quando não foi.
> Conferência que não mente:
>
> ```powershell
> git ls-remote --heads origin        # o sha que o remoto tem de fato
> git status -sb                      # "## main...origin/main" sem ahead/behind
> ```

> O `.env` continua fora do commit — conferido com
> `git ls-files | Select-String "\.env$"`, que voltou vazio. Vale repetir a
> conferência antes de qualquer push futuro.

## Alerta no Telegram

Só em falha, e só quando a execução registra status (não em `--status`,
`--dry-run` ou `DEBUG`). O envio **nunca levanta exceção**: se o Telegram
estiver fora, vira linha de log — o robô já está tratando um problema e não
pode trocar a causa real por uma falha de notificação.

Implementação compartilhada em `lib_dscs/notificacao.py`
(`dl.alertar_erro_robo`), disponível para os próximos robôs.

## Estado atual — 26/09/2026

**Migrado para a nuvem.** O run disparado na mão em 26/09
([36241478211](https://github.com/diegoscs/ambiente_dev/actions/runs/36241478211))
terminou em sucesso e gravou status, histórico e link do run no Supabase:

```
ping ok: postgres 1533.3 ms | rest 590.2 ms      ambiente = CLOUD
```

O `cadastro_carga.sql` pela metade (abaixo) **deixou de importar**: as colunas
`flg_sincronizado`/`dta_sync` só serviam ao espelho, que saiu.

## Estado em 25/09/2026

**O robô rodou pela primeira vez com sucesso**, às 11:59 de 25/09/2026:

```
[PING] postgres OK em 244.5 ms   [PING] rest OK em 445.6 ms
[ROBO002] RESULTADO FINAL: SUCESSO
```

`dbo.controle_cargas` tem a linha `id_carga = 2` em `SUCCESS`, e o espelho
`public.controle_cargas` no Supabase recebeu a linha — o caminho inteiro,
ponta a ponta, funciona.

O que destravou: as três variáveis do Supabase entraram no `.env` da raiz. A
senha do banco vai **percent-encoded** na `SUPABASE_DB_URL` (o `!` vira `%21`);
o host do pooler continua sendo `aws-0-sa-east-1`, como estava documentado.

### O `cadastro_carga.sql` foi aplicado pela metade

Só a **parte 2** (o `INSERT` do robô) rodou, com o `robo_app`. A **parte 1**
(`ALTER TABLE` + `COMMENT` + `GRANT`) exige o dono da tabela, que é o
`postgres` — conferido: `robo_app` não é superuser nem membro de `postgres`.

Efeito prático: `flg_sincronizado` e `dta_sync` não existem, então o robô **não
consegue marcar que espelhou**. Toda execução reenvia a linha e loga:

```
[SYNC] ⚠ nem a marcacao de pendencia funcionou: coluna "dta_sync" nao existe
```

**Isso não derruba o robô** — o resultado final continua `SUCESSO`, que é o
comportamento projetado (falha no passo 5 nunca derruba). O custo é um reenvio
redundante por execução e um aviso no log. Rodar o arquivo inteiro como
`postgres` fecha isso; ele é idempotente (`ADD COLUMN IF NOT EXISTS` e
`ON CONFLICT DO UPDATE`), então aplicar de novo por cima não conflita.

### Histórico — 21/09/2026

Escrito em 15/09, o keepalive não rodou uma única vez até 25/09 — e em 21/09 o
`financas-pipeline` foi encontrado `INACTIVE`, exatamente o desfecho que ele
existia para impedir. O projeto foi restaurado no mesmo dia.

Nada disso apareceu como erro em lugar nenhum, e é a mesma lição do robô 001:
robô que não roda não escreve log, não muda status e não dispara alerta — o
silêncio dele é idêntico ao do sucesso. Ali foi pior, porque a linha
`id_carga = 2` nem existia: não havia `dta_fim` velho para a consulta de atraso
encontrar.

### Pendências

- [x] ~~Preencher o `.env` da raiz~~ — feito em 25/09/2026, validado com ping
      real nos dois caminhos.
- [x] ~~Rodar o `cadastro_carga.sql` inteiro como `postgres`~~ — **não precisa
      mais** (26/09/2026). A parte 1 criava as colunas de controle do espelho,
      que saiu na migração para a nuvem.

- [x] ~~Dar o scope `workflow` ao token e rodar `git push`~~ — feito em
      25/09/2026. Remoto em `9815e24`, workflow no ar.
- [x] ~~Cadastrar os secrets~~ — os três do Supabase criados em 25/09/2026 e
      validados com um `workflow_dispatch` que terminou em sucesso. Os dois do
      Telegram seguem ausentes, de propósito (opcionais).

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
│                           (o registro no Supabase vem da lib_dscs)
├─ ping.py                  ping_postgres() e ping_rest() + retry
├─ 002_check_supabase.bat   o que o Agendador chama
├─ cadastro_carga.sql       ALTER + INSERT do robô (rodar como postgres)
├─ criar_tarefa.ps1         cria a tarefa no Agendador (rodar como admin)
└─ README.md
```
