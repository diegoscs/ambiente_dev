-- MODELO - vira supabase/migrations/<AAAAMMDDHHMMSS>_cadastro_robo_NNN.sql
-- e e aplicado como migration (nunca SQL solto no painel).
--
-- Com a linha cadastrada, o robo aparece sozinho no hub, no vigia e na
-- vw_saude_robos. Nenhum codigo do hub muda.
insert into public.controle_cargas (
  id_carga, nome_carga, descricao,
  tempo_min,          -- passou disso em RUNNING = TRAVADO
  atraso_max_horas,   -- sem execucao fechada ha mais que isso = ATRASADO
  dias_semana, flg_ativo, origem, script, workflow
)
values (
  999, '999 - Nome Robo', '<o que faz>',
  10,
  26,                 -- diario: 26 (24 h + folga da fila do GitHub)
  '{1,2,3,4,5,6,7}', true, 'Python/API', '999_nome_robo.py', 'robo_999_nome_robo.yml'
)
on conflict (id_carga) do nothing;
