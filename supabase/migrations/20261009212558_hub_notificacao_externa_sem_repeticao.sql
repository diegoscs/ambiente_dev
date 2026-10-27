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
declare
  v_origem text := coalesce(left(p_origem, 50), 'carga_' || p_id_carga);
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

  -- Anti-spam: o mesmo aviso (origem + titulo + detalhe) so volta depois de 24 h.
  -- O sync roda 2x/dia e uma pendencia que persiste geraria o mesmo aviso sempre.
  if exists (
    select 1 from public.notificacoes_hub n
    where n.origem = v_origem
      and n.titulo = left(p_titulo, 200)
      and n.detalhe is not distinct from left(p_detalhe, 1000)
      and n.dta_add > now() - interval '24 hours'
  ) then
    return;
  end if;

  insert into public.notificacoes_hub (origem, nivel, titulo, detalhe)
  values (v_origem, p_nivel, left(p_titulo, 200), left(p_detalhe, 1000));
end;
$$;

revoke all on function public.notificar_hub_externo(text, integer, text, text, text, text) from public;
grant execute on function public.notificar_hub_externo(text, integer, text, text, text, text) to anon, authenticated;

-- Notificacoes antigas do vigia no formato novo
update public.notificacoes_hub
   set titulo = '✅ Tudo certo: ' || (regexp_match(titulo, '(\d+) robo'))[1] || ' robôs em dia'
 where origem = 'vigia' and titulo ~ '^Verificacao ok: \d+ robo\(s\) em dia$';
