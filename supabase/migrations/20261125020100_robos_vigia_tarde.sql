-- Vigia tambem a tarde (decisao de 25/11/2026): 16:00 de Sao Paulo = 19:00 UTC,
-- depois do sync das 15:00. Manda o "resumo da tarde" no #resumo-diario e avisa
-- no #alertas o que tiver dado errado desde a manha. O turno sai do horario.
select cron.schedule('vigia_robos_tarde', '0 19 * * *',
  $$select private.disparar_workflow('diegoscs/ambiente_dev', 'vigia_robos.yml')$$);
