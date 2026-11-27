-- Radar de ofertas: pausado a pedido do usuario em 27/11/2026 ("nao vou usar
-- mais por enquanto"). Os dois jobs ficam cadastrados, mas inativos; tabelas,
-- produtos, historico e o webhook do Vault continuam. Nada do radar roda.
--
-- Religar:
--   select cron.alter_job(jobid, active := true) from cron.job
--    where jobname in ('radar_ofertas', 'radar_resumo_diario');
--   update private.radar_fontes set ultimo_post = null;  -- opcional: recomeca pelos 20 posts mais novos
select cron.alter_job(jobid, active := false)
  from cron.job
 where jobname in ('radar_ofertas', 'radar_resumo_diario');
