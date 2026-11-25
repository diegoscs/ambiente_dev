-- Robo 006 - saude do DMC (banco dos apps de clientes), so leitura.
-- 05:00 de Sao Paulo = 08:00 UTC: depois do backup (04:00) e antes do vigia (09:00).
insert into public.controle_cargas (
  id_carga, nome_carga, descricao,
  tempo_min,          -- passou disso em RUNNING = TRAVADO
  atraso_max_horas,   -- sem execucao fechada ha mais que isso = ATRASADO
  dias_semana, flg_ativo, origem, script, workflow
)
values (
  6, '006 - Saude do DMC',
  'Site, API, Auth, Edge Functions, RLS, tamanho e assinaturas dos apps de clientes no DMC (so leitura)',
  10,
  26,
  '{1,2,3,4,5,6,7}', true, 'Python/API', '006_saude_dmc.py', 'robo_006_saude_dmc.yml'
)
on conflict (id_carga) do nothing;

select cron.schedule('robo_006_saude_dmc', '0 8 * * *',
  $$select private.disparar_workflow('diegoscs/ambiente_dev', 'robo_006_saude_dmc.yml')$$);
