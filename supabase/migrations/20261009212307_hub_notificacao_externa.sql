-- Robos de fora do ambiente_dev (ex.: sync do financas-app) deixam aviso no
-- feed do hub com o mesmo token por robo de registrar_execucao_carga.
create or replace function public.notificar_hub_externo(
  p_token text,
  p_id_carga integer,
  p_nivel text,
  p_titulo text,
  p_detalhe text default null,
  p_origem text default null
) returns void
language plpgsql
security definer
set search_path = public, private, pg_temp
as $$
begin
  if not exists (
    select 1 from private.tokens_carga t
    where t.id_carga = p_id_carga
      and t.token_hash = sha256(convert_to(coalesce(p_token, ''), 'UTF8'))
  ) then
    raise exception 'nao autorizado' using errcode = '42501';
  end if;
  if p_nivel not in ('info', 'atencao', 'resolvido') then
    raise exception 'nivel invalido';
  end if;
  insert into public.notificacoes_hub (origem, nivel, titulo, detalhe)
  values (coalesce(left(p_origem, 50), 'carga_' || p_id_carga), p_nivel, left(p_titulo, 200), left(p_detalhe, 1000));
end;
$$;

revoke all on function public.notificar_hub_externo(text, integer, text, text, text, text) from public;
grant execute on function public.notificar_hub_externo(text, integer, text, text, text, text) to anon, authenticated;
