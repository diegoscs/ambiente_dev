-- Robo 007 - saude do DMP (banco pessoal), so leitura.
-- 03:00 de Sao Paulo = 06:00 UTC: unica hora cheia livre antes do vigia (09:00).
insert into public.controle_cargas (
  id_carga, nome_carga, descricao,
  tempo_min, atraso_max_horas,
  dias_semana, flg_ativo, origem, script, workflow
)
values (
  7, '007 - Saude do DMP',
  'Sites pessoais, Auth fechado, RLS, escrita do papel anonimo, tamanho, falhas do pg_cron e Vault do DMP (so leitura)',
  10, 26,
  '{1,2,3,4,5,6,7}', true, 'Python/API', '007_saude_dmp.py', 'robo_007_saude_dmp.yml'
)
on conflict (id_carga) do nothing;

select cron.schedule('robo_007_saude_dmp', '0 6 * * *',
  $$select private.disparar_workflow('diegoscs/ambiente_dev', 'robo_007_saude_dmp.yml')$$);
