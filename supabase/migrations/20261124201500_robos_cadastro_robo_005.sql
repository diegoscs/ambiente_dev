-- Robo 005 - backup diario dos bancos Supabase (DMP e DMC).
--
-- O backup roda no repo PRIVADO diegoscs/backups-supabase; o pg_cron dispara o
-- robo_005_backup_supabase.yml deste repo, que aciona o de la e acompanha.
-- 04:00 de Sao Paulo = 07:00 UTC: antes do sync (06:00) e do vigia (09:00).
insert into public.controle_cargas (
  id_carga, nome_carga, descricao,
  tempo_min,          -- passou disso em RUNNING = TRAVADO
  atraso_max_horas,   -- sem execucao fechada ha mais que isso = ATRASADO
  dias_semana, flg_ativo, origem, script, workflow
)
values (
  5, '005 - Backup Supabase',
  'Backup do DMP e do DMC (estrutura + CSV), restaurado e conferido; fica so o mais recente no repo privado',
  30,
  26,
  '{1,2,3,4,5,6,7}', true, 'Python/psycopg', '005_backup_supabase.py', 'robo_005_backup_supabase.yml'
)
on conflict (id_carga) do nothing;

select cron.schedule('robo_005_backup_supabase', '0 7 * * *',
  $$select private.disparar_workflow('diegoscs/ambiente_dev', 'robo_005_backup_supabase.yml')$$);
