-- Retencao das tabelas que crescem no DMP (decisao de 24/11/2026).
--
-- Hoje o DMP tem 17 MB de 500: e prevencao, nao aperto. Prazos bem maiores
-- que o que alguem le (o hub mostra 14 e 30 dias; o vigia, o dia):
--   public.historico_cargas      execucoes com mais de 365 dias
--   public.notificacoes_hub      avisos JA LIDOS com mais de 90 dias
--   openfinance.sync_execucoes   log do sync com mais de 180 dias (o app so le a ultima)
-- Ficam de fora: minecraft_* (vira arquivo depois de 16/01/2027; o
-- minecraft_desempenho ja se limpa sozinho), cron.job_run_details (job
-- limpar_historico_pg_cron, 7 dias) e net._http_response (a Supabase limpa).
--
-- Roda todo dia 00:40 de Sao Paulo (03:40 UTC), junto da limpeza do pg_cron.
create or replace function private.aplicar_retencao()
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, pg_temp
as $$
declare
  v_hist bigint; v_notif bigint; v_sync bigint;
begin
  delete from public.historico_cargas where dta_ini < now() - interval '365 days';
  get diagnostics v_hist = row_count;
  delete from public.notificacoes_hub where lida and dta_add < now() - interval '90 days';
  get diagnostics v_notif = row_count;
  delete from openfinance.sync_execucoes where iniciado_em < now() - interval '180 days';
  get diagnostics v_sync = row_count;
  return jsonb_build_object('historico_cargas', v_hist, 'notificacoes_hub', v_notif,
                            'sync_execucoes', v_sync);
end;
$$;

revoke all on function private.aplicar_retencao() from public, anon, authenticated;

select cron.schedule('retencao_tabelas', '40 3 * * *', $$select private.aplicar_retencao()$$);
