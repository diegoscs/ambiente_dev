# 005 · Backup Supabase

Backup diário dos bancos Supabase, fora da Supabase: `pg_dump` pelo Session
pooler, criptografado com **age** e guardado no **Google Drive** (pasta
"Backups Supabase"), com retenção de 30 dias. Nasceu na etapa 0 da migração dos
projetos ([levantamento](../../docs/levantamento_migracao.md)): nenhum dos
bancos tinha backup, e o plano grátis não inclui.

| | |
|---|---|
| Origem | financas-pipeline/DM e OpenFinance (`ALVOS` no robô). O Clientes entra na etapa 3; o OpenFinance sai quando for pausado |
| Destino | `gdrive:Backups Supabase/<banco>_<AAAA-MM-DD_HHMMZ>.tar.age` |
| Quando | 04:00 de São Paulo, pelo `pg_cron` (depois do primeiro restore conferido) |
| `id_carga` | 5 |
| `qtd_itens` | backups que chegaram ao Drive |

## Fluxo

1. Valida variáveis, a porta 5432 de cada string de conexão, a chave pública e
   as ferramentas (`pg_dump`, `pg_restore`, `age`, `rclone`), antes de qualquer rede.
2. Para cada banco, dois `pg_dump --format=custom`:
   - **principal**: estrutura e dados de tudo que é nosso (`public`, `private`,
     `estoque`, `openfinance`…), sem os schemas que a Supabase administra;
   - **extras**: só dados de `auth.users`, `auth.identities`, `cron.job` e
     `supabase_migrations.schema_migrations`.
3. `pg_restore --list` em cada dump: dump que não abre não segue.
4. `tar` dos dois e `age` com a chave **pública**. O `.tar` em claro e os dumps
   são apagados na hora; a pasta temporária some no fim.
5. `rclone copyto` para o Drive (com retry).
6. Só depois de **todos** os envios: apaga do Drive os backups com mais de 30
   dias (vão para a lixeira do Drive, que guarda mais 30 dias). Só arquivos no
   formato `<banco>_*.tar.age` entram na limpeza.

## Configuração

Secrets do Actions (`ambiente_dev`):

| Secret | O que é |
|---|---|
| `SUPABASE_URL`, `SUPABASE_KEY` | os de sempre (registro no hub) |
| `SUPABASE_DUMP_URL_DM` | Session pooler (porta 5432) do financas-pipeline/DM |
| `SUPABASE_DUMP_URL_OPENFINANCE` | Session pooler (porta 5432) do OpenFinance |
| `BACKUP_AGE_RECIPIENT` | chave **pública** do age (`age1...`) |
| `BACKUP_RCLONE_CONF` | saída de `rclone config show gdrive` (com o token OAuth) |

No PC, as mesmas chaves no `.env` (veja o `.env.example`), menos a
`BACKUP_RCLONE_CONF`: lá o rclone usa a config padrão. `BACKUP_PG_BIN` aponta
para a pasta do `pg_dump` se ele não estiver no PATH.

## Uso

```powershell
$py = "C:\Users\ferna\AppData\Local\Python\bin\python.exe"
& $py automacoes\005_backup_supabase\005_backup_supabase.py --status      # config e versões
& $py automacoes\005_backup_supabase\005_backup_supabase.py --dry-run     # gera e confere, não envia
& $py automacoes\005_backup_supabase\005_backup_supabase.py --alvo dm     # só um banco
```

No Actions, o "Run workflow" tem as mesmas opções (`dry_run`, `alvo`).
Antes de cada etapa da migração: rodar na mão com `alvo` = o banco que vai mudar.

## Decisões

- **Session pooler, porta 5432.** O Transaction pooler (6543, o do robô 002)
  não serve para `pg_dump`, e a conexão direta da Supabase é só IPv6, que o
  runner do GitHub não tem. O robô recusa outra porta.
- **`pg_dump` 17**, igual ao servidor. O runner traz o 16; o 17 vem do
  repositório oficial do Postgres (`BACKUP_PG_BIN`). Para restaurar, qualquer
  `pg_restore` 17 ou mais novo serve (o PC usa o 18).
- **Criptografia com age e chave pública.** Quem tem acesso ao Actions ou ao
  Drive não consegue abrir o backup: a chave privada só existe no gerenciador
  de senhas. **Perder a chave privada = perder todos os backups.**
- **Nada passa pelo GitHub.** O `ambiente_dev` é público: nenhum dump vai para
  artifact, release ou log.
- **Drive pessoal com OAuth (rclone), não conta de serviço**, que não tem cota
  no Drive pessoal. Escopo `drive.file`: o rclone só enxerga o que ele mesmo
  criou. Por isso a pasta "Backups Supabase" é criada pelo rclone, nunca à mão.
  O token de acesso é renovado a cada execução; o de renovação fica no secret.
- **Fica fora do backup, de propósito:**
  - arquivos do Storage (o `openfinance-bronze` é refeito pelo sync, decisão de 22/11/2026);
  - segredos do Vault (o `pg_dump` levaria o valor cifrado, que não abre em outro
    projeto). Num restore, o `github_dispatch_token` é criado de novo à mão;
  - a configuração do projeto (Data API, Auth, SMTP), que fica no painel.
- **Dois dumps em vez de um.** O principal restaura num projeto novo sem brigar
  com o que a Supabase já cria; o "extras" traz as contas com os mesmos IDs, que
  as tabelas do estoque e do openfinance referenciam.
- **Sem trava de uma vez por dia:** rodar de novo antes de uma etapa da
  migração tem que funcionar. O carimbo com hora no nome evita sobrescrever.
- **Sem Telegram** (decisão de 22/11/2026): durante a migração o alerta é o
  e-mail do GitHub (run vermelho); depois, o Discord.

## Cadastro

Migration a aplicar antes do primeiro run de verdade (sem ela o registro falha
e o vigia não enxerga o robô):

```sql
insert into public.controle_cargas (
  id_carga, nome_carga, descricao, tempo_min, atraso_max_horas,
  dias_semana, flg_ativo, origem, script, workflow
)
values (
  5, '005 - Backup Supabase',
  'pg_dump dos bancos Supabase, criptografado (age) e guardado no Google Drive, 30 dias',
  20, 26, '{1,2,3,4,5,6,7}', true, 'Python/pg_dump', '005_backup_supabase.py',
  'robo_005_backup_supabase.yml'
)
on conflict (id_carga) do nothing;
```

O horário (04:00 SP = `0 7 * * *` UTC) entra numa migration à parte, depois do
primeiro restore conferido.

## Estado

- **23/11/2026**: código e workflow prontos; faltam os secrets, o cadastro e o
  primeiro run. Restore ainda não testado.
