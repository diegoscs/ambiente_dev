-- O vigia passa a conferir se o GitHub aceitou os disparos do pg_cron.
-- private.disparar_workflow faz o POST pelo pg_net; a resposta fica 6 h em
-- net._http_response. 401/403/404 ali = token do Vault vencido, revogado ou sem
-- permissao: todos os robos param no mesmo dia, e so a reserva do vigia veria.
-- So leitura; so a chave de servico (o vigia) chama.
create or replace function public.disparos_github_recentes()
returns table (quando timestamptz, status_http integer, erro text)
language sql
stable
security definer
set search_path = ''
as $$
  select r.created, r.status_code, coalesce(r.error_msg, left(r.content, 200))
    from net._http_response r
   where r.created > now() - interval '24 hours'
   order by r.created desc;
$$;

revoke all on function public.disparos_github_recentes() from public, anon, authenticated;
grant execute on function public.disparos_github_recentes() to service_role;
