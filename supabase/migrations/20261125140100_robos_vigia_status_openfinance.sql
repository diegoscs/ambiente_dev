-- O vigia passa a falar do Open Finance so por status: "tudo em dia" ou
-- "nao sincroniza desde <dia>" (decisao de 25/11/2026: nada de movimentacao
-- nova ou lancamento para conferir no Discord).
--
-- Por conta ativa no Pluggy: a ultima execucao do sync que deu certo
-- (ok/vazio) e quando o Pluggy tinha atualizado o banco naquela hora
-- (item_atualizado_em, migration do financas-app de 25/11/2026). O vigia usa
-- a mais antiga das duas: sync rodando com a conexao parada no Pluggy tambem
-- e "nao sincroniza".
--
-- So leitura; so a chave de servico (o vigia) chama.
create or replace function public.status_openfinance()
returns table (conta text, ultimo_sync timestamptz, pluggy_atualizado timestamptz)
language sql
stable
security definer
set search_path = ''
as $$
  select c.nome, s.iniciado_em, s.item_atualizado_em
    from openfinance.pluggy_contas p
    join openfinance.contas c on c.id = p.conta_id
    left join lateral (
      select e.iniciado_em, e.item_atualizado_em
        from openfinance.sync_execucoes e
       where e.conta_id = p.conta_id
         and e.status in ('ok', 'vazio')
       order by e.iniciado_em desc
       limit 1
    ) s on true
   where p.ativo
   order by c.nome;
$$;

revoke all on function public.status_openfinance() from public, anon, authenticated;
grant execute on function public.status_openfinance() to service_role;
