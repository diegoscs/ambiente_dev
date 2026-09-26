-- O dono ja esta cadastrado: hub_acesso deixa de cadastrar o primeiro login.
-- Sem isso, se a conta do dono fosse apagada (on delete cascade), a tabela
-- esvaziaria e o proximo cadastro qualquer no projeto viraria dono do hub.
-- Leitor novo agora so por SQL: insert into private.hub_leitores (user_id) values (...);
create or replace function public.hub_acesso()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (select 1 from private.hub_leitores where user_id = (select auth.uid()));
$$;

comment on function public.hub_acesso() is 'True se o usuario logado pode ler o hub. So consulta; leitor novo e cadastrado por SQL em private.hub_leitores.';
comment on table private.hub_leitores is 'Usuarios do Supabase Auth que podem ler o hub dos robos. Cadastro so por SQL.';
