-- Robo 004 (clima nas praias) aposentado em 29/10/2026: tabelas, historico e
-- cadastro saem. Backup: dm_2026-11-24_1306Z.zip.
drop table public.previsao_praias, public.painel_praias;
delete from public.historico_cargas where id_carga = 4;
delete from public.controle_cargas where id_carga = 4;
