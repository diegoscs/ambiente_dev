-- Minecraft: fim dos creditos do teste do Google (acabam em 18/01/2027).
-- Dispara o workflow minecraft_fim_creditos.yml, que decide o modo pela data
-- de Sao Paulo (antes de 17/01 = so backup; de 17/01 em diante = encerrar).
-- Detalhes em apps/minecraft/gcp/README.md.
--
-- Horarios em UTC (o pg_cron do Supabase roda em UTC; SP = UTC-3):
--   15/01 09:00 UTC = 06:00 SP  backup + conferencia das permissoes
--   17/01 09:00 UTC = 06:00 SP  desliga as VMs, backup final, corta o faturamento
--   17/01 15:00 UTC = 12:00 SP  repescagem, se o das 06:00 falhou
-- Cron nao tem ano: a guarda de data impede que disparem de novo em 2028.
-- Mesmo nome = substitui o job, entao rodar de novo e seguro.
select cron.schedule('minecraft_fim_creditos_backup', '0 9 15 1 *',
  $$select private.disparar_workflow('diegoscs/ambiente_dev', 'minecraft_fim_creditos.yml')
     where now() < '2027-01-16'::timestamptz$$);
select cron.schedule('minecraft_fim_creditos', '0 9 17 1 *',
  $$select private.disparar_workflow('diegoscs/ambiente_dev', 'minecraft_fim_creditos.yml')
     where now() < '2027-01-18'::timestamptz$$);
select cron.schedule('minecraft_fim_creditos_repescagem', '0 15 17 1 *',
  $$select private.disparar_workflow('diegoscs/ambiente_dev', 'minecraft_fim_creditos.yml')
     where now() < '2027-01-18'::timestamptz$$);
