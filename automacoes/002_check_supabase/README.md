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

Criar a tarefa apontando para o `.bat` (nunca para o `.py` direto):

| Campo | Valor |
|---|---|
| Nome | `002_check_supabase` |
| Gatilho | Diariamente, **08:00** |
| Ação | Iniciar um programa |
| Programa | `D:\ambiente_dev\automacoes\002_check_supabase\002_check_supabase.bat` |
| Iniciar em | `D:\ambiente_dev\automacoes\002_check_supabase` |

Marcar, em **Geral**:
- ☑ **Executar estando o usuário conectado ou não** — sem isso a tarefa só roda
  com a sessão aberta, que é justamente o dia em que ela precisa rodar sozinha
- ☐ Não armazenar senha (deixe **desmarcado**: sem a senha a tarefa não acessa
  a rede nem o `D:`)
- ☑ Executar com privilégios mais altos — opcional, não é necessário

Em **Condições**:
- ☐ Iniciar a tarefa somente se o computador estiver ocioso — **desmarcar**
- ☑ Ativar o computador para executar esta tarefa — opcional, útil se a máquina
  dorme

Em **Configurações**:
- ☑ **Executar a tarefa assim que possível após uma inicialização agendada ter
  sido perdida** — máquina desligada às 08:00 roda quando ligar
- ☑ Se houver falha, reiniciar a cada **10 minutos**, até **3** tentativas
- ☑ Interromper a tarefa se ela for executada por mais de **1 hora**

O jeito curto é o [`criar_tarefa.ps1`](criar_tarefa.ps1), que já traz essa
configuração inteira — **PowerShell como administrador**, porque criar tarefa
com `RunLevel Highest` devolve *Acesso negado* em sessão comum:

```powershell
powershell -ExecutionPolicy Bypass -File D:\ambiente_dev\automacoes\002_check_supabase\criar_tarefa.ps1
```

Via linha de comando (PowerShell como administrador):

```powershell
schtasks /Create /TN "002_check_supabase" /TR "D:\ambiente_dev\automacoes\002_check_supabase\002_check_supabase.bat" /SC DAILY /ST 08:00 /RU "$env:USERNAME" /RP * /RL LIMITED /F
```

O `/RP *` pede a senha interativamente — é o equivalente a "executar mesmo sem
usuário logado". As opções de "execução perdida" e retry o `schtasks` não expõe;
ajuste-as depois na interface, ou importe um XML.

## GitHub Actions (modo CLOUD)

O workflow está em [`.github/workflows/supabase_keepalive.yml`](../../.github/workflows/supabase_keepalive.yml)
— `cron: "12 9 */2 * *"` (a cada 2 dias, 06:12 em São Paulo) + `workflow_dispatch`.

O repositório já existe: **`diegoscs/ambiente_dev`** (privado), com `origin`
apontado e o primeiro commit pronto localmente.

**O push está travado no scope do token.** Um PAT clássico com `repo` dá conta
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

**O robô nunca executou, e o projeto já foi pausado.** O `financas-pipeline`
está `INACTIVE` no Supabase: o keepalive não chegou a rodar uma vez desde que
foi escrito, em 15/09.

Nada disso apareceu como erro em lugar nenhum, e é a mesma lição do robô 001:
robô que não roda não escreve log, não muda status e não dispara alerta — o
silêncio dele é idêntico ao do sucesso. Aqui foi pior, porque a linha
`id_carga = 2` nem existe: não havia `dta_fim` velho para a consulta de atraso
encontrar.

### Pendências

- [ ] **Restaurar o projeto no Supabase.** Enquanto estiver `INACTIVE`, a string
      do pooler não conecta e nem o `--dry-run` passa do ping Postgres.
- [ ] **Preencher o `.env` da raiz** com `SUPABASE_URL`, `SUPABASE_KEY`
      (a `service_role`, não a `anon`) e `SUPABASE_DB_URL` (pooler, porta 6543).
      É o primeiro bloqueio: sem eles o robô morre na `validar_configuracao`,
      antes de qualquer ping.
- [ ] **Rodar o [`cadastro_carga.sql`](cadastro_carga.sql) como `postgres`.**
      Hoje `dbo.controle_cargas` só tem `id_carga = 1`, e as colunas
      `flg_sincronizado`/`dta_sync` não existem — o espelhamento quebraria. O
      `robo_app` não serve: o dono da tabela é o `postgres`, e `ALTER` e `GRANT`
      pedem propriedade.
- [ ] **Criar a tarefa** com o [`criar_tarefa.ps1`](criar_tarefa.ps1).
- [ ] **Ativar o modo CLOUD**: `git push` do repositório e os cinco secrets em
      *Settings → Secrets and variables → Actions*. Enquanto isso não for feito,
      o workflow falha em toda execução do cron por falta de variável.

> A ordem importa: a tarefa local **não** cobre o cenário que causou a pausa,
> que é a máquina desligada. Quem protege de verdade é o cron do GitHub Actions;
> o Agendador é o complemento, não o contrário.

### Resolvido

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
