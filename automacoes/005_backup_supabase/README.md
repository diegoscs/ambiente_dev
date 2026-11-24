# 005 · Backup Supabase

Backup diário dos bancos Supabase fora da Supabase, **só com Python** (sem
`pg_dump` e sem PostgreSQL instalado): estrutura em SQL e dados em CSV num
`.zip` por banco. Todo backup é **restaurado e conferido** antes de ser guardado.
Nasceu na etapa 0 da migração dos projetos
([levantamento](../../docs/levantamento_migracao.md)): nenhum banco tinha
backup, e o plano grátis não inclui.

| | |
|---|---|
| Origem | DMP (`mthipdxpedlfnkzddlar`) e clientes (`oaqhgdewlfjtepjfaiml`) (`ALVOS` no robô). O OpenFinance saiu em 24/11/2026, quando foi pausado |
| Onde roda | repo **privado** `diegoscs/backups-supabase` (workflow `backup_supabase.yml`), com o código deste repo |
| Destino | artifact da execução no repo privado, **30 dias** |
| Quando | 04:00 de São Paulo: `pg_cron` → [`robo_005_backup_supabase.yml`](../../.github/workflows/robo_005_backup_supabase.yml) (disparador) → repo privado |
| `id_carga` | 5 (só a execução na nuvem registra) |

## Fluxo da execução diária

1. O `pg_cron` (ou o botão do hub) dispara o `robo_005_backup_supabase.yml`
   deste repo, que dispara o `backup_supabase.yml` do repo privado e acompanha.
2. O repo privado baixa este código, sobe um Postgres da Supabase
   (`supabase/postgres`, mesma versão do DM) num container e roda
   `005_backup_supabase.py --pasta ... --testar-restore`.
3. Para cada banco: exporta (uma transação `REPEATABLE READ READ ONLY`, todas as
   tabelas do mesmo instante), confere o zip contra o banco, **restaura** no
   container e confere linhas por tabela e objetos por tipo. O restore é
   desfeito no fim.
4. Os zips sobem como artifact (30 dias). Se o envio falhar, o registro vira ERROR.

## O que vai em cada zip

| Arquivo | Conteúdo |
|---|---|
| `estrutura_1_antes_dos_dados.sql` | schemas, extensões, sequences, tabelas, funções, defaults, views, PK/unique/check |
| `dados/<schema>.<tabela>.csv` | todas as tabelas dos nossos schemas + `auth.users`, `auth.identities`, `cron.job`, `supabase_migrations.schema_migrations` |
| `estrutura_2_depois_dos_dados.sql` | FKs, índices, triggers, RLS, policies, grants, valores das sequences |
| `estrutura.json` | os mesmos comandos, um por item (o restore executa um a um) |
| `manifesto.json` | colunas, linhas e sha256 de cada CSV; contagem de objetos |
| `LEIA-ME.txt` | ordem do restore |

**Fica de fora:** arquivos do Storage (o bronze é refeito pelo sync), segredos
do Vault (num restore, o `github_dispatch_token` é criado de novo à mão),
configuração do painel (Data API, Auth, SMTP), comentários e dono dos objetos.

## Uso no PC

```powershell
$py = "C:\Users\ferna\AppData\Local\Python\bin\python.exe"
$r  = "automacoes\005_backup_supabase\005_backup_supabase.py"
& $py $r --status                              # o que está configurado
& $py $r --dry-run                             # gera e confere numa pasta temporária, não grava nada
& $py $r --pasta D:\backups\supabase           # backup na mão (pasta FORA do repositório)
& $py $r --pasta D:\backups\supabase --alvo dmp # só um banco
& $py $r --conferir D:\backups\supabase\dm_<data>.zip   # confere um zip, sem banco
```

No PC o robô não registra no hub (modo LOCAL) e não testa o restore (não há
Postgres). Baixar um backup do repo privado:
`gh run download -R diegoscs/backups-supabase --name backups-<id> -D D:\backups\supabase`.

| Variável | O que é |
|---|---|
| `SUPABASE_DUMP_URL_DMP` | string de conexão do DMP. Opcional: sem ela, vale o `SUPABASE_DB_URL` |
| `SUPABASE_DMC_DB_URL` | string de conexão do DMC (`aws-1-sa-east-1.pooler.supabase.com`) |
| `BACKUP_RESTORE_URL` | Postgres do teste de restore (no Actions, o container) |

## Restore de verdade

Ordem (também no `LEIA-ME.txt`): `estrutura_1` → cada CSV por `COPY` (com as
colunas do manifesto; `auth.users`/`auth.identities` só num projeto Supabase e
antes das tabelas que apontam para elas) → `estrutura_2`. As triggers só nascem
no fim, então carregar os dados não dispara nada (as quantidades do estoque não
são somadas de novo). O `restaurar.py` faz isso com `confirmar=True`; é o
caminho da etapa 1 da migração.

## Copiar um schema entre projetos

`copiar_schema.py` (24/11/2026) leva **um** schema de um projeto para outro:
estrutura do catálogo (mesmo gerador do backup), dados por `COPY` direto entre
os bancos e, se pedido, as contas do Auth. Tudo numa transação no destino,
conferida (linhas por tabela e objetos por tipo); sem `--confirmar` é ensaio.

```powershell
& $py automacoes\005_backup_supabase\copiar_schema.py --origem VAR --destino VAR --schema NOME `
    [--trocar-usuario ID_ORIGEM=ID_DESTINO] [--copiar-contas] [--substituir] [--confirmar]
```

Usado na migração: `openfinance` OpenFinance → DM com `--trocar-usuario` (mesmo
e-mail, outro ID) e `--substituir` (o antigo de 30/09 saiu); `estoque` DM →
clientes com `--copiar-contas` (mesmos IDs e senhas). Senha com `@` ou `/`
na string de conexão vai codificada (`%40`, `%2F`).

## Decisões

- **Sem `pg_dump` (23/11/2026).** Instalar o PostgreSQL no PC foi descartado. O
  `psycopg` lê a estrutura do catálogo e os dados por `COPY`. Os bancos usam só
  tabelas, views, funções, triggers, policies, sequences e colunas identity
  (conferido em 23/11/2026); um tipo novo (enum, domínio, view materializada)
  faz o teste de restore falhar, e aí a exportação precisa aprender o tipo.
- **Teste de restore todo dia.** Backup que não restaura não serve. O container
  é a imagem oficial da Supabase, com os papéis e o schema `auth`.
- **Repo privado em vez de Google Drive (23/11/2026).** O Drive exigia app
  próprio no Google Cloud (o client_id compartilhado do rclone sai em 2026). O
  artifact do Actions já tem retenção de 30 dias e não precisa de credencial nova.
- **Sem criptografia (23/11/2026).** O repo privado é o controle de acesso. Ele
  **precisa continuar privado**, e nenhum backup pode passar pelo `ambiente_dev`,
  que é público.
- **Qualquer pooler serve.** A exportação é uma transação só, com
  `prepare_threshold=None`: funciona no Transaction pooler (6543) e no Session (5432).
- **Retry só em falha de conexão.** Erro de SQL ou permissão estoura na primeira.
- **Sem Telegram** (22/11/2026): alerta é o e-mail do GitHub (run vermelho); depois, o Discord.

## Cadastro

Migration a aplicar antes da primeira execução automática:

```sql
insert into public.controle_cargas (
  id_carga, nome_carga, descricao, tempo_min, atraso_max_horas,
  dias_semana, flg_ativo, origem, script, workflow
)
values (
  5, '005 - Backup Supabase',
  'Backup dos bancos Supabase (estrutura + CSV), restaurado e conferido, 30 dias no repo privado',
  30, 26, '{1,2,3,4,5,6,7}', true, 'Python/psycopg', '005_backup_supabase.py',
  'robo_005_backup_supabase.yml'
)
on conflict (id_carga) do nothing;

select cron.schedule('robo_005_backup_supabase', '0 7 * * *',
  $$select private.disparar_workflow('diegoscs/ambiente_dev', 'robo_005_backup_supabase.yml')$$);
```

## Estado

- **23/11/2026**: backups manuais do DM (50 tabelas, 2.604 linhas) e do
  OpenFinance (14 tabelas, 2.626 linhas) em `D:\backups\supabase`, conferidos.
  Execução diária pronta no código; faltam criar o repo privado, os secrets dele,
  o primeiro teste de restore na nuvem, o cadastro e o horário.
- **23/11/2026 (02:42 UTC)**: repo privado `backups-supabase` criado, com os
  4 secrets. Primeira execução na nuvem (disparada lá, com o código da branch)
  passou: DM 47 tabelas/2.539 linhas e OpenFinance 12 tabelas/2.620 linhas
  restauradas e conferidas; artifact de 0,4 MB. O registro no hub falhou
  (sem `id_carga = 5`), como esperado.
  - O container `supabase/postgres` não tem o Auth completo: `auth.identities`,
    `cron.job` e `schema_migrations` são puladas no teste e `auth.users` entra só
    com as colunas básicas. Essas tabelas estão no zip; o teste só não as confere.
- **24/11/2026**: falta, nesta ordem: juntar o PR; conferir se o
  `FINANCAS_DISPATCH_TOKEN` alcança o `backups-supabase` (primeiro "Rodar agora"
  pelo `robo_005_backup_supabase.yml`); aplicar o cadastro e o horário.
- **24/11/2026 (tarde)**: alvos passam a ser DM e clientes (OpenFinance
  pausado). No repo privado faltam o secret `SUPABASE_DMC_DB_URL` e a
  linha dele no workflow; o `SUPABASE_DUMP_URL_OPENFINANCE` pode sair.
