-- Robo 004 (clima nas praias) aposentado em 03/11/2026: o app praias-ubatuba
-- saiu da Vercel. Sai do disparo diario e fica inativo, o que o tira da
-- vw_saude_robos (hub e vigia). Historico e as tabelas previsao_praias e
-- painel_praias ficam no banco; religar = reverter estas tres partes.
select cron.unschedule('robo_004_clima_praias');

update public.controle_cargas
   set flg_ativo = false, dta_modif = now()
 where id_carga = 4;

-- Sem a pagina publica, a leitura anonima do painel nao tem mais motivo.
drop policy if exists leitura_publica on public.painel_praias;
revoke select on public.painel_praias from anon, authenticated;
