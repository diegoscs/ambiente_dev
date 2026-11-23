# 005 · Backup Supabase

Backup dos bancos Supabase fora da Supabase, **só com Python** (sem `pg_dump` e
sem PostgreSQL instalado): estrutura em SQL e dados em CSV num `.zip`,
criptografado com **age**. Nasceu na etapa 0 da migração dos projetos
([levantamento](../../docs/levantamento_migracao.md)): nenhum banco tinha
backup, e o plano grátis não inclui.

| | |
|---|---|
| Origem | financas-pipeline/DM e OpenFinance (`ALVOS` no robô). O Clientes entra na etapa 3; o OpenFinance sai quando for pausado |
| Destino hoje | pasta do PC, na mão (`--pasta`) |
| Destino depois | Google Drive pelo rclone, às 04:00 pelo `pg_cron`, com retenção de 30 dias |
| `id_carga` | 5 (só a execução automática registra) |

## O que vai no backup

Um arquivo por banco: `<banco>_<AAAA-MM-DD_HHMMZ>.zip.age`. Aberto, o zip tem:

| Arquivo | Conteúdo |
|---|---|
| `estrutura_1_antes_dos_dados.sql` | schemas, sequences, tabelas, funções, defaults, views, PK/unique/check |
| `dados/<schema>.<tabela>.csv` | todas as tabelas dos nossos schemas + `auth.users`, `auth.identities`, `cron.job`, `supabase_migrations.schema_migrations` |
| `estrutura_2_depois_dos_dados.sql` | FKs, índices, triggers, RLS, policies, grants, valores das sequences |
| `manifesto.json` | colunas, número de linhas e sha256 de cada CSV |
| `LEIA-ME.txt` | ordem do restore |

Tudo é lido numa transação só (`REPEATABLE READ READ ONLY`): todas as tabelas
saem do mesmo instante. Antes de criptografar, o robô reabre o zip e confere
cada CSV (sha256 e número de linhas contra o `count(*)` do banco).

**Fica de fora:** arquivos do Storage (decisão de 22/11/2026: o bronze é refeito
pelo sync), segredos do Vault (num restore, o `github_dispatch_token` é criado de
novo à mão), configuração do painel (Data API, Auth, SMTP), comentários e dono
dos objetos.

## Uso

```powershell
$py = "C:\Users\ferna\AppData\Local\Python\bin\python.exe"
$r  = "automacoes\005_backup_supabase\005_backup_supabase.py"
& $py $r --status                              # o que está configurado
& $py $r --dry-run                             # gera e confere numa pasta temporária, não grava nada
& $py $r --pasta D:\backups\supabase           # backup manual (pasta FORA do repositório)
& $py $r --pasta D:\backups\supabase --alvo dm # só um banco
& $py $r --conferir D:\backups\supabase\dm_<data>.zip.age --chave <arquivo da chave privada>
```

`--conferir` abre o backup com a chave privada numa pasta temporária e confere
cada CSV contra o manifesto, sem banco nenhum. A chave privada fica num arquivo
só durante o comando: crie a partir do gerenciador de senhas e apague logo depois.

Configuração no `.env` (veja o `.env.example`):

| Variável | O que é |
|---|---|
| `SUPABASE_DUMP_URL_DM` | string de conexão do DM. Opcional: sem ela, vale o `SUPABASE_DB_URL` |
| `SUPABASE_DUMP_URL_OPENFINANCE` | string de conexão do OpenFinance (Connect → Session pooler) |
| `BACKUP_AGE_RECIPIENT` | chave **pública** do age (`age1...`) |

## Restore

Ordem (também no `LEIA-ME.txt` de cada backup):

1. `estrutura_1_antes_dos_dados.sql`
2. cada CSV com `COPY <schema>.<tabela> (<colunas do manifesto>) FROM ... CSV HEADER`;
   `auth.users` e `auth.identities` antes das tabelas que apontam para elas, e
   só num projeto Supabase
3. `estrutura_2_depois_dos_dados.sql`

As triggers só são criadas no passo 3: carregar os dados não dispara nada (as
quantidades do estoque não são somadas de novo).

## Decisões

- **Sem `pg_dump` (23/11/2026).** Instalar o PostgreSQL no PC só para o backup
  foi descartado. O `psycopg`, que os robôs já usam, lê a estrutura do catálogo
  e os dados por `COPY`. O banco usa só tabelas, views, funções, triggers,
  policies, sequences e colunas identity (conferido em 23/11/2026); se aparecer
  enum, domínio ou view materializada, a exportação precisa aprender o tipo novo.
- **Qualquer pooler serve.** A exportação inteira é uma transação, com
  `prepare_threshold=None`: funciona no Transaction pooler (6543, o mesmo do
  robô 002) e no Session pooler (5432).
- **Criptografia com age e chave pública.** Quem tem o arquivo ou acesso ao PC,
  ao Actions ou ao Drive não abre o backup: a chave privada só existe no
  gerenciador de senhas. **Perder a chave privada = perder todos os backups.**
- **Nada passa pelo GitHub.** O `ambiente_dev` é público: nenhum backup vai para
  artifact, release ou log. A pasta do `--pasta` não pode ficar dentro do repositório.
- **Retry só em falha de conexão.** Erro de SQL ou permissão estoura na primeira.
- **Sem Telegram** (decisão de 22/11/2026): o alerta é o e-mail do GitHub (run
  vermelho); depois, o Discord.
- **Drive depois.** O client_id compartilhado do rclone deixa de funcionar em
  2026: a automação vai precisar de um client_id próprio no Google Cloud, com o
  app publicado (em "Teste" o token vence a cada 7 dias).

## Cadastro (para a execução automática)

Migration a aplicar antes do primeiro run automático:

```sql
insert into public.controle_cargas (
  id_carga, nome_carga, descricao, tempo_min, atraso_max_horas,
  dias_semana, flg_ativo, origem, script, workflow
)
values (
  5, '005 - Backup Supabase',
  'Backup dos bancos Supabase (estrutura + CSV), criptografado com age, 30 dias',
  20, 26, '{1,2,3,4,5,6,7}', true, 'Python/psycopg', '005_backup_supabase.py',
  'robo_005_backup_supabase.yml'
)
on conflict (id_carga) do nothing;
```

O horário (04:00 SP = `0 7 * * *` UTC) entra numa migration à parte.

## Estado

- **23/11/2026**: primeiro backup de verdade do DM em `D:ackups\supabase`
  (50 tabelas, 2.604 linhas, conferidas; 0,2 MB), **sem criptografia** porque a
  chave age não estava à mão. Faltam: o backup do OpenFinance (senha do banco),
  refazer os dois com a chave (e apagar o `.zip` em claro) e o `--conferir`.
