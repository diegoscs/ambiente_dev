-- Sentinela de sites (decisao de 26/11/2026): de 15 em 15 minutos, de dentro do
-- DMP (pg_cron + pg_net), sem gastar Actions. Complementa os robos 006/007, que
-- abrem os sites so uma vez por dia.
--
-- Cada rodada: le a resposta do pedido anterior de cada site e faz um pedido
-- novo. Site "fora" = 2 falhas seguidas (nao alarma por um soluco); "voltou" =
-- 1 resposta boa. So avisa na MUDANCA, no #alertas e, se o site for de
-- cliente, tambem no canal dele. Webhooks do Discord no Vault do DMP
-- (discord_webhook_alertas, discord_webhook_estoque), nunca no repositorio.

create table if not exists private.sentinela_sites (
  nome            text primary key,
  url             text not null,
  canal           text not null default 'alertas',   -- canal extra alem do #alertas
  ativo           boolean not null default true,
  estado          text not null default 'no_ar' check (estado in ('no_ar', 'fora')),
  falhas_seguidas integer not null default 0,
  pedido_id       bigint,
  pedido_em       timestamptz,
  ultimo_codigo   integer,
  ultimo_ms       integer,
  conferido_em    timestamptz,
  mudou_em        timestamptz
);
alter table private.sentinela_sites enable row level security;
revoke all on private.sentinela_sites from public, anon, authenticated;

insert into private.sentinela_sites (nome, url, canal) values
  ('hub-robos',      'https://hub-robos.vercel.app',               'alertas'),
  ('server-galera',  'https://server-galera.vercel.app',           'alertas'),
  ('financas-app',   'https://financas-app-delta-rose.vercel.app', 'alertas'),
  ('estoque-tattoo', 'https://estoque-tattoo-rho.vercel.app',      'estoque')
on conflict (nome) do nothing;

-- Posta no Discord pelo webhook do Vault. Sem o segredo, so um warning no log.
create or replace function private.sentinela_avisar(p_canal text, p_texto text)
returns void
language plpgsql
security definer
set search_path = pg_catalog, pg_temp
as $$
declare
  v_url text;
begin
  select decrypted_secret into v_url from vault.decrypted_secrets
   where name = 'discord_webhook_' || p_canal;
  if v_url is null or v_url = '' then
    raise warning 'sentinela: sem o segredo discord_webhook_% no Vault', p_canal;
    return;
  end if;
  perform net.http_post(
    url := v_url,
    body := jsonb_build_object('username', 'sentinela', 'content', p_texto,
                               'allowed_mentions', jsonb_build_object('parse', jsonb_build_array())),
    headers := jsonb_build_object('Content-Type', 'application/json', 'User-Agent', 'sentinela-dmp'),
    timeout_milliseconds := 10000
  );
end;
$$;

create or replace function private.sentinela_rodada()
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, pg_temp
as $$
declare
  s record;
  r record;
  v_ok boolean;
  v_txt text;
  v_mudancas integer := 0;
begin
  for s in select * from private.sentinela_sites where ativo order by nome loop
    if s.pedido_id is not null then
      select * into r from net._http_response where id = s.pedido_id;
      v_ok := found and not coalesce(r.timed_out, false) and r.status_code between 200 and 399;
      v_txt := case when not found then 'sem resposta'
                    when coalesce(r.timed_out, false) then 'demorou mais de 10 s'
                    when r.status_code is null then coalesce(left(r.error_msg, 80), 'erro de rede')
                    else 'HTTP ' || r.status_code end;

      if v_ok then
        update private.sentinela_sites
           set falhas_seguidas = 0, ultimo_codigo = r.status_code,
               ultimo_ms = (extract(epoch from (r.created - s.pedido_em)) * 1000)::int,
               conferido_em = now(),
               estado = 'no_ar',
               mudou_em = case when s.estado = 'fora' then now() else mudou_em end
         where nome = s.nome;
        if s.estado = 'fora' then
          v_mudancas := v_mudancas + 1;
          v_txt := format('✅ **%s voltou** (%s). Ficou fora por cerca de %s min.', s.nome, v_txt,
                          greatest(1, round(extract(epoch from (now() - s.mudou_em)) / 60)));
          perform private.sentinela_avisar('alertas', v_txt);
          if s.canal <> 'alertas' then perform private.sentinela_avisar(s.canal, v_txt); end if;
        end if;
      else
        update private.sentinela_sites
           set falhas_seguidas = falhas_seguidas + 1, ultimo_codigo = r.status_code, conferido_em = now()
         where nome = s.nome;
        if s.estado = 'no_ar' and s.falhas_seguidas + 1 >= 2 then
          update private.sentinela_sites set estado = 'fora', mudou_em = now() where nome = s.nome;
          v_mudancas := v_mudancas + 1;
          v_txt := format('🔴 **%s fora do ar** (%s) em 2 checagens seguidas. %s', s.nome, v_txt, s.url);
          perform private.sentinela_avisar('alertas', v_txt);
          if s.canal <> 'alertas' then perform private.sentinela_avisar(s.canal, v_txt); end if;
        end if;
      end if;
    end if;

    update private.sentinela_sites
       set pedido_id = net.http_get(url := s.url,
                                    headers := jsonb_build_object('User-Agent', 'sentinela-dmp'),
                                    timeout_milliseconds := 10000),
           pedido_em = now()
     where nome = s.nome;
  end loop;
  return jsonb_build_object('mudancas', v_mudancas);
end;
$$;

revoke all on function private.sentinela_avisar(text, text) from public, anon, authenticated;
revoke all on function private.sentinela_rodada() from public, anon, authenticated;

select cron.schedule('sentinela_sites', '*/15 * * * *', $$select private.sentinela_rodada()$$);
