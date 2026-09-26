-- Acesso do hub web (Vercel): leitura do status dos robos so para quem esta
-- em private.hub_leitores. O schema private nao e exposto pela API.
create schema if not exists private;

create table if not exists private.hub_leitores (
  user_id uuid primary key references auth.users (id) on delete cascade,
  dta_add timestamptz not null default now()
);
alter table private.hub_leitores enable row level security;

comment on table private.hub_leitores is 'Usuarios do Supabase Auth que podem ler o hub dos robos. O primeiro login no hub se cadastra via public.hub_acesso(); depois disso so por SQL.';

-- Usada pelas policies. security definer para ler hub_leitores sem policy propria.
create or replace function private.eh_leitor_hub()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (select 1 from private.hub_leitores where user_id = (select auth.uid()));
$$;

-- Chamada pelo hub logo apos o login. Cadastra o usuario SO se ainda nao
-- houver nenhum leitor (primeiro acesso do dono); depois so responde se o
-- usuario atual tem acesso.
create or replace function public.hub_acesso()
returns boolean
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
  uid uuid := (select auth.uid());
begin
  if uid is null then
    return false;
  end if;
  if not exists (select 1 from private.hub_leitores) then
    insert into private.hub_leitores (user_id) values (uid);
  end if;
  return exists (select 1 from private.hub_leitores where user_id = uid);
end;
$$;

revoke all on function public.hub_acesso() from public, anon;
grant execute on function public.hub_acesso() to authenticated;

revoke all on function private.eh_leitor_hub() from public, anon;
grant usage on schema private to authenticated;
grant execute on function private.eh_leitor_hub() to authenticated;

-- Leitura para o leitor do hub. Escrita continua so com a service_role.
grant select on public.controle_cargas, public.historico_cargas, public.vw_saude_robos to authenticated;

drop policy if exists hub_leitura on public.controle_cargas;
create policy hub_leitura on public.controle_cargas
  for select to authenticated using ((select private.eh_leitor_hub()));

drop policy if exists hub_leitura on public.historico_cargas;
create policy hub_leitura on public.historico_cargas
  for select to authenticated using ((select private.eh_leitor_hub()));
