-- Robo 004 (clima nas praias de Ubatuba) no controle de cargas. Com a linha
-- cadastrada, ele aparece sozinho no hub, no vigia e na vw_saude_robos.
insert into public.controle_cargas (
  id_carga, nome_carga, descricao,
  tempo_min,          -- passou disso em RUNNING = TRAVADO
  atraso_max_horas,   -- sem execucao fechada ha mais que isso = ATRASADO
  dias_semana, flg_ativo, origem, script, workflow
)
values (
  4, '004 - Clima Praias',
  'Ranking das praias de Ubatuba por chance de sol (Open-Meteo), de amanha ate a proxima terca. Grava em public.previsao_praias',
  10,
  26,                 -- diario: 24 h + folga
  '{1,2,3,4,5,6,7}', true, 'Python/API', '004_clima_praias.py', 'robo_004_clima_praias.yml'
)
on conflict (id_carga) do nothing;

-- 05:00 SP = 08:00 UTC. Hora livre (06 sync, 07 robo 001, 08 robo 002, 09 vigia)
-- e com os modelos da rodada 00 UTC ja publicados. Mesmo nome = substitui.
select cron.schedule('robo_004_clima_praias', '0 8 * * *',
  $$select private.disparar_workflow('diegoscs/ambiente_dev', 'robo_004_clima_praias.yml')$$);
