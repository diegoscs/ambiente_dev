-- Robos que rodam fora do ambiente_dev (ex.: sync do financas-app) registram
-- inicio/fim no hub por RPC, autenticados por um token proprio por robo.
create table if not exists private.tokens_carga (
  id_carga integer primary key references public.controle_cargas(id_carga),
  token_hash bytea not null,
  dta_add timestamptz not null default now()
);
alter table private.tokens_carga enable row level security;
revoke all on private.tokens_carga from anon, authenticated;

create or replace function public.registrar_execucao_carga(
  p_token text,
  p_id_carga integer,
  p_evento text,              -- 'inicio' | 'fim'
  p_status text default null, -- fim: 'SUCCESS' | 'ERROR'
  p_qtd integer default null,
  p_mensagem text default null,
  p_url text default null
) returns void
language plpgsql
security definer
set search_path = public, private, pg_temp
as $$
declare
  v_ini timestamptz;
begin
  if not exists (
    select 1 from private.tokens_carga t
    where t.id_carga = p_id_carga
      and t.token_hash = sha256(convert_to(coalesce(p_token, ''), 'UTF8'))
  ) then
    raise exception 'nao autorizado' using errcode = '42501';
  end if;

  if p_evento = 'inicio' then
    update public.controle_cargas
       set status = 'RUNNING', dta_ini = now(), dta_fim = null,
           mensagem = coalesce(left(p_mensagem, 500), 'rodando'),
           url_execucao = p_url, dta_modif = now()
     where id_carga = p_id_carga;

  elsif p_evento = 'fim' then
    if p_status not in ('SUCCESS', 'ERROR') then
      raise exception 'status invalido';
    end if;
    select dta_ini into v_ini from public.controle_cargas where id_carga = p_id_carga;
    insert into public.historico_cargas (id_carga, status, dta_ini, dta_fim, ambiente, qtd_itens, mensagem, url_execucao)
    values (p_id_carga, p_status, coalesce(v_ini, now()), now(), 'CLOUD', p_qtd, left(p_mensagem, 500), p_url);
    update public.controle_cargas
       set status = p_status, dta_fim = now(), mensagem = left(p_mensagem, 500),
           url_execucao = coalesce(p_url, url_execucao), dta_modif = now()
     where id_carga = p_id_carga;

  else
    raise exception 'evento invalido';
  end if;
end;
$$;

revoke all on function public.registrar_execucao_carga(text, integer, text, text, integer, text, text) from public;
grant execute on function public.registrar_execucao_carga(text, integer, text, text, integer, text, text) to anon, authenticated;
