-- Robo 005: o pg_cron passa a disparar o backup DIRETO no repo privado
-- (diegoscs/backups-supabase), com o token do Vault. Decisao de 24/11/2026.
--
-- Antes, o job chamava o robo_005_backup_supabase.yml deste repo, que dispara o
-- de la com o FINANCAS_DISPATCH_TOKEN: dois tokens no caminho. Agora so o do
-- Vault, que ja alcanca o repo privado. O workflow do ambiente_dev continua para
-- o botao "Rodar agora" do hub (precisa do FINANCAS_DISPATCH_TOKEN com acesso).
-- Mesmo nome de job: o cron.schedule substitui o comando.
select cron.schedule('robo_005_backup_supabase', '0 7 * * *',
  $$select private.disparar_workflow('diegoscs/backups-supabase', 'backup_supabase.yml')$$);
