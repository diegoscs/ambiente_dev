-- Minecraft: adianta um dia o encerramento do fim dos creditos (antes 15 e
-- 17/01, agora 14 e 16/01), para o reembolso do pre-pagamento poder ser
-- pedido no dia 17, ainda dentro do teste. O workflow decide o modo pela data
-- de SP (antes de 16/01 = so backup; de 16/01 em diante = encerrar).
--
-- Horarios em UTC (SP = UTC-3):
--   14/01 09:00 UTC = 06:00 SP  backup + conferencia das permissoes
--   16/01 09:00 UTC = 06:00 SP  desliga as VMs, backup final, corta o faturamento
--   16/01 15:00 UTC = 12:00 SP  repescagem, se o das 06:00 falhou
-- Mesmos nomes da 20261118190000: cron.schedule substitui os jobs.
select cron.schedule('minecraft_fim_creditos_backup', '0 9 14 1 *',
  $$select private.disparar_workflow('diegoscs/ambiente_dev', 'minecraft_fim_creditos.yml')
     where now() < '2027-01-15'::timestamptz$$);
select cron.schedule('minecraft_fim_creditos', '0 9 16 1 *',
  $$select private.disparar_workflow('diegoscs/ambiente_dev', 'minecraft_fim_creditos.yml')
     where now() < '2027-01-17'::timestamptz$$);
select cron.schedule('minecraft_fim_creditos_repescagem', '0 15 16 1 *',
  $$select private.disparar_workflow('diegoscs/ambiente_dev', 'minecraft_fim_creditos.yml')
     where now() < '2027-01-17'::timestamptz$$);
