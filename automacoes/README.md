# automacoes — os robôs do ambiente_dev

Todos os robôs rodam no **GitHub Actions**, um workflow por robô em
[`.github/workflows`](../.github/workflows), e registram cada execução no
Supabase (`public.controle_cargas` + `public.historico_cargas`). O PC não é
agendador: robô que depende da máquina ligada para quando ela desliga, e
ninguém percebe.

| Robô | Workflow | Quando roda (São Paulo) |
|---|---|---|
| 003 · Sync Open Finance | `sync-openfinance.yml` no financas-app (botão: `robo_003_sync_openfinance.yml`) | 06:00 e 15:00 |
| [001 · Check GitHub](001_check_github/README.md) | `robo_001_check_github.yml` | 07:00 |
| [002 · Check Supabase](002_check_supabase/README.md) | `robo_002_check_supabase.yml` | 08:00 |
| [Vigia](vigia_robos.py) | `vigia_robos.yml` | 09:00 (reserva pelo `schedule` à tarde) |

Quem marca a hora é o `pg_cron` do Supabase: na hora cheia ele chama o
`workflow_dispatch` do robô, e o run começa em segundos
([migration](../supabase/migrations/20261027233340_robos_disparo_pg_cron.sql)).
O token fica no Vault (`github_dispatch_token`).

## Conferir se rodou

- **Hub** no celular: status, calendário de 14 dias e botão *Rodar agora*
  ([apps/hub/README.md](../apps/hub/README.md)).
- **Vigia**: todo dia lê a `vw_saude_robos`, deixa notificação no hub e deixa o
  run vermelho (e-mail do GitHub) se algum robô estiver com `ERRO`, `ATRASADO`,
  `TRAVADO` ou `NUNCA_RODOU`. No PC:

```powershell
& "C:\Users\ferna\AppData\Local\Python\bin\python.exe" automacoes\vigia_robos.py
```

Robô que não roda não escreve log, não muda status e não dispara alerta — o
silêncio dele é idêntico ao do sucesso. Por isso a saúde é medida por **atraso**
(`atraso_max_horas`), não só por erro.

## Rodar na mão

```powershell
$py = "C:\Users\ferna\AppData\Local\Python\bin\python.exe"
& $py automacoes\001_check_github\001_check_github.py --dry-run
& $py automacoes\002_check_supabase\002_check_supabase.py --status
```

`--dry-run` e `--status` não registram nada. Uma execução real no PC registra
com `ambiente = LOCAL` (o `MODO_EXECUCAO` do `.env`); no Actions, `CLOUD`.

## Robô novo

Siga o [PADRAO_ROBOS.md](PADRAO_ROBOS.md) e parta de [`_modelo/`](_modelo).

## Arquivos

```
automacoes\
├─ PADRAO_ROBOS.md          regras para robôs novos
├─ _modelo\                 esqueleto de robô, workflow e cadastro no Supabase
├─ vigia_robos.py           vigia diário (workflow vigia_robos.yml)
├─ 001_check_github\        robô 001 + README próprio
└─ 002_check_supabase\      robô 002 + README próprio
```

## Histórico

- **até 24/09/2026** — duas tarefas por horário no Agendador do Windows.
- **25/09/2026** — uma tarefa só, no logon, chamando um `.bat` que rodava os dois.
- **26/09/2026** — robôs no GitHub Actions; o Agendador ficou em paralelo
  ([docs/migracao_nuvem.md](../docs/migracao_nuvem.md)).
- **02/10/2026** — PC fora do caminho de vez: a tarefa `ambiente_dev - Robos`
  (que ainda estava **ativa**, apesar do checklist) foi removida, junto com os
  `.bat`, os scripts de criar/verificar a tarefa, o `cadastro_carga.sql` do
  Postgres local e o modo `LOCAL` do código dos robôs 001 e 002. Os arquivos
  continuam no histórico do git.
- **27/10/2026** — disparo em hora cheia pelo `pg_cron` do Supabase. O
  `schedule` do GitHub atrasou os robôs de 2 a 7 h entre 20 e 27/10 (001 marcado
  00:17 rodou entre 05:11 e 06:03; 002 marcado 06:12, entre 10:17 e 13:05). O
  `schedule` só ficou no vigia, como reserva (`--reserva`).
