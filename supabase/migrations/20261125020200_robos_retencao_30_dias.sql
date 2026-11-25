-- Retencao: tudo com 30 dias (decisao de 25/11/2026; antes 365/90/180).
-- O hub mostra os ultimos 30 dias e os avisos agora vao para o Discord, entao
-- nada alem disso e lido. notificacoes_hub: apaga lidas e nao lidas.
create or replace function private.aplicar_retencao()
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, pg_temp
as $$
declare
  v_hist bigint; v_notif bigint; v_sync bigint;
begin
  delete from public.historico_cargas where dta_ini < now() - interval '30 days';
  get diagnostics v_hist = row_count;
  delete from public.notificacoes_hub where dta_add < now() - interval '30 days';
  get diagnostics v_notif = row_count;
  delete from openfinance.sync_execucoes where iniciado_em < now() - interval '30 days';
  get diagnostics v_sync = row_count;
  return jsonb_build_object('historico_cargas', v_hist, 'notificacoes_hub', v_notif,
                            'sync_execucoes', v_sync);
end;
$$;

revoke all on function private.aplicar_retencao() from public, anon, authenticated;
