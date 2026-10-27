# 002 — Check Supabase (keepalive)

Impede que o projeto Supabase do plano free seja **pausado por inatividade**.
Toda execução faz uma consulta real no projeto por **dois caminhos** — conexão
Postgres e API REST (PostgREST) — e registra o resultado no próprio Supabase:
`public.controle_cargas` (última execução) e `public.historico_cargas` (uma
linha por execução), `id_carga = 2`.

Roda no **GitHub Actions**, todo dia às 09:12 UTC (06:12 em São Paulo)
([workflow](../../.github/workflows/robo_002_check_supabase.yml)).

> Projeto alvo: **financas-pipeline** (`mthipdxpedlfnkzddlar`, sa-east-1).

## Por que dois pings

O Supabase mede atividade por componente: banco e API REST têm contadores
próprios. Pingar só um deixa dúvida se conta como atividade para o outro — os
dois juntos custam ~2 segundos e resolvem. Se **qualquer um** dos dois falhar
depois de 3 tentativas, a carga fecha como `ERROR`: metade da atividade não
garante o projeto acordado.

O projeto free pausa depois de ~7 dias sem atividade. Rodando todo dia, a pausa
só acontece se o workflow falhar uma semana inteira — e o hub mostra `ATRASADO`
bem antes disso.

## Fluxo

1. Valida `SUPABASE_URL`, `SUPABASE_KEY` e `SUPABASE_DB_URL` antes de qualquer rede
2. `RUNNING` no Supabase
3. Ping Postgres (`select now()`) e ping REST — 3 tentativas cada, 20 s de espera
4. `SUCCESS` + uma linha em `historico_cargas`, com `mensagem` = latências
   (`ping ok: postgres 180 ms | rest 95 ms`) e o link do run
5. Na falha: `ERROR` + histórico + alerta no Telegram + `erro_*.txt` como
   artifact `log-erro-002`

**Falha ao registrar nunca derruba o robô**: vira linha de log. Se o Supabase
inteiro estiver fora, o ping falha e o registro também; quem pega esse caso é o
run vermelho no Actions (o GitHub manda e-mail) e o `ATRASADO` da
`vw_saude_robos` no hub.

## Configuração

Secrets do Actions (*Settings → Secrets and variables → Actions*) e, no PC, o
`.env` da raiz ([`.env.example`](../../.env.example)):

| Variável | O quê |
|---|---|
| `SUPABASE_URL` | `https://mthipdxpedlfnkzddlar.supabase.co` |
| `SUPABASE_KEY` | **`service_role`** (Settings → API). A `anon` esbarra na RLS, que não tem policy de escrita de propósito |
| `SUPABASE_DB_URL` | connection string do *Transaction pooler* (porta 6543). A senha vai **percent-encoded** (`!` vira `%21`) |
| `TELEGRAM_TOKEN` / `TELEGRAM_CHAT_ID` | opcionais; sem eles a falha só avisa pelo e-mail do GitHub |

Tabelas e view (`controle_cargas`, `historico_cargas`, `vw_saude_robos`)
versionadas em [`supabase/migrations`](../../supabase/migrations).

## Como rodar na mão

```powershell
$py = "C:\Users\ferna\AppData\Local\Python\bin\python.exe"

& $py automacoes\002_check_supabase\002_check_supabase.py --status     # configuração, sem pingar
& $py automacoes\002_check_supabase\002_check_supabase.py --dry-run    # ping de verdade, sem registrar
```

`--status` e `--dry-run` **não registram status**: marcar `SUCCESS` neles
mentiria no monitoramento. Disparo real: botão *Rodar agora* do hub ou
`workflow_dispatch`. Execução real no PC registra `ambiente = LOCAL`.

## Log: só em caso de erro

As linhas ficam em memória e só viram arquivo se a execução falhar:
`temp\erro_002_check_supabase_<AAAAMMDD_HHMMSS>.txt`. **Execução bem-sucedida não
deixa rastro em disco.**

## Alerta no Telegram

Só em falha, e só quando a execução registra status. O envio **nunca levanta
exceção**: se o Telegram estiver fora, vira linha de log — o robô já está
tratando um problema e não pode trocar a causa real por uma falha de
notificação. Implementação em `lib_dscs/notificacao.py` (`dl.alertar_erro_robo`).

## Histórico

### O projeto pausou com o robô "funcionando" (21/09/2026)

Escrito em 15/09 para rodar pelo Agendador do Windows, o keepalive não rodou uma
única vez até 25/09 — e em 21/09 o `financas-pipeline` foi encontrado
`INACTIVE`, exatamente o desfecho que ele existia para impedir. O projeto foi
restaurado no mesmo dia.

Nada disso apareceu como erro em lugar nenhum: robô que não roda não escreve
log, não muda status e não dispara alerta — o silêncio dele é idêntico ao do
sucesso. E a tarefa local não cobria o cenário real, que é a máquina desligada.
Daí o cron no GitHub Actions, a `vw_saude_robos` medindo atraso e o vigia.

### O que travava o push do workflow (25/09/2026)

Um PAT clássico com `repo` dá conta de tudo, **menos** de gravar dentro de
`.github/workflows/`:

```
! [remote rejected] main -> main (refusing to allow a Personal Access Token
  to create or update workflow `.github/workflows/supabase_keepalive.yml`
  without `workflow` scope)
```

Resolvido marcando **`workflow`** no mesmo token — editar os scopes não muda o
valor do token. Conferência de push que não mente:

```powershell
git ls-remote --heads origin        # o sha que o remoto tem de fato
git status -sb                      # "## main...origin/main" sem ahead/behind
```

### Linha do tempo

- **15/09/2026** — primeira versão, com espelho do `dbo.controle_cargas` local
  no Supabase.
- **21/09/2026** — projeto restaurado de `INACTIVE`; tarefa no Agendador criada.
- **25/09/2026** — primeira execução com sucesso (postgres 244 ms, rest 445 ms);
  workflow no ar (`supabase_keepalive.yml`, a cada 2 dias); robô passa a rodar
  pela tarefa única de logon.
- **26/09/2026** — migra para o Actions, diário. Registro direto no Supabase; o
  `sync_supabase.py` (cópia com fila de pendências) sai. Run
  [36241478211](https://github.com/diegoscs/ambiente_dev/actions/runs/36241478211):
  `ping ok: postgres 1533.3 ms | rest 590.2 ms`, `ambiente = CLOUD`.
- **02/10/2026** — modo `LOCAL` removido: sem `.bat`, sem `criar_tarefa.ps1`,
  sem `cadastro_carga.sql` e sem gravação no `dbo.controle_cargas`.

## Arquivos

```
002_check_supabase\
├─ 002_check_supabase.py    main: controle de carga, orquestra o resto
├─ config_robo.py           constantes, leitura e validação do ambiente
├─ ping.py                  ping_postgres() e ping_rest() + retry
└─ README.md
```
