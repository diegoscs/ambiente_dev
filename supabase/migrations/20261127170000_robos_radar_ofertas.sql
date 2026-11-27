-- Radar de ofertas (27/11/2026): le canais publicos de promocao do Telegram e
-- avisa no Discord quando sai oferta de um produto da lista. Como a sentinela
-- de sites, roda dentro do DMP (pg_cron + pg_net), sem gastar Actions: o
-- usuario quer o aviso "quase na hora", e o Actions levaria minutos so para
-- subir a maquina.
--
-- Como le: a pagina publica https://t.me/s/<canal>?after=<ultimo post lido>
-- devolve ate 20 posts seguintes (do mais antigo para o mais novo), sem login.
-- A cada 20 s a rodada le a resposta do pedido anterior e faz um pedido novo:
-- o aviso chega 20 a 40 s depois do post. Canal com mais de 20 posts por
-- rodada so atrasa (a proxima pagina vem na rodada seguinte); nada se perde.
--
-- Cada oferta avisa uma vez (unique em radar_avisos). Falha de leitura so
-- avisa no #alertas depois de 5 min seguidos (15 rodadas), e de novo quando
-- volta. Uso e como incluir produto: docs/RADAR_OFERTAS.md.

create table if not exists private.radar_fontes (
  canal_telegram  text primary key,           -- nome publico: t.me/<nome>
  ativo           boolean not null default true,
  ultimo_post     bigint,                      -- ultimo post ja lido (null = comeca pelos 20 mais novos)
  estado          text not null default 'ok' check (estado in ('ok', 'falha')),
  falhas_seguidas integer not null default 0,
  pedido_id       bigint,                      -- pedido do pg_net em andamento
  pedido_em       timestamptz,
  lido_em         timestamptz,                 -- ultima leitura boa
  mudou_em        timestamptz
);
alter table private.radar_fontes enable row level security;
revoke all on private.radar_fontes from public, anon, authenticated;

create table if not exists private.radar_produtos (
  id         integer generated always as identity primary key,
  nome       text not null,
  termos     text[] not null check (cardinality(termos) > 0),  -- todos precisam aparecer; 'a|b' = um ou outro
  excluir    text[] not null default '{}',                      -- qualquer um que aparecer descarta o post
  preco_max  numeric(12,2),                                     -- null = avisa qualquer preco
  canal      text not null default 'alertas',                   -- canal do Discord (Vault: discord_webhook_<canal>)
  ativo      boolean not null default true,
  criado_em  timestamptz not null default now()
);
alter table private.radar_produtos enable row level security;
revoke all on private.radar_produtos from public, anon, authenticated;

create table if not exists private.radar_avisos (
  id             bigint generated always as identity primary key,
  id_produto     integer not null references private.radar_produtos (id) on delete cascade,
  canal_telegram text not null,
  id_post        bigint not null,
  preco          numeric(12,2),
  texto          text,
  dta_post       timestamptz,
  avisado_em     timestamptz not null default now(),
  unique (id_produto, canal_telegram, id_post)
);
alter table private.radar_avisos enable row level security;
revoke all on private.radar_avisos from public, anon, authenticated;

-- Primeiro canal e primeiro produto (pedido de 27/11/2026). ultimo_post 49530:
-- a primeira rodada ja pega o 5700X postado as 16:17 UTC (post 49539), e o
-- aviso de verdade serve de teste de ponta a ponta.
insert into private.radar_fontes (canal_telegram, ultimo_post) values ('Fraguas84Oficial', 49530)
on conflict (canal_telegram) do nothing;

insert into private.radar_produtos (nome, termos, excluir)
select 'Ryzen 7 5700X', '{5700x}', '{5700x3d}'
where not exists (select 1 from private.radar_produtos where nome = 'Ryzen 7 5700X');

-- ─── texto ──────────────────────────────────────────────────────────────────

-- Minusculo, sem acento, so letras e numeros separados por um espaco.
create or replace function private.radar_normalizar(p_texto text)
returns text
language sql
immutable
set search_path = pg_catalog, pg_temp
as $$
  select btrim(regexp_replace(
    translate(lower(coalesce(p_texto, '')), 'áàâãäéèêëíìîïóòôõöúùûüç', 'aaaaaeeeeiiiiooooouuuuc'),
    '[^a-z0-9]+', ' ', 'g'))
$$;

-- Termo -> regex sobre o texto normalizado. '5700x' casa "5700X" e "5700 x",
-- mas nao "5700X3D" (letra ou numero colado logo depois nao vale) nem "5700G".
-- 'a|b' = um ou outro.
create or replace function private.radar_regex(p_termo text)
returns text
language sql
immutable
set search_path = pg_catalog, pg_temp
as $$
  select '(?<![a-z0-9])(' || string_agg(
           replace(regexp_replace(regexp_replace(private.radar_normalizar(alt),
                     '([0-9])([a-z])', '\1 \2', 'g'), '([a-z])([0-9])', '\1 \2', 'g'),
                   ' ', '\s*'),
           '|') || ')(?![a-z0-9])'
    from unnest(string_to_array(p_termo, '|')) alt
   where private.radar_normalizar(alt) <> ''
$$;

create or replace function private.radar_casa(p_texto_norm text, p_termos text[], p_excluir text[])
returns boolean
language sql
immutable
set search_path = pg_catalog, pg_temp
as $$
  select coalesce((select bool_and(p_texto_norm ~ private.radar_regex(t)) from unnest(p_termos) t), false)
     and not exists (select 1 from unnest(p_excluir) e where p_texto_norm ~ private.radar_regex(e))
$$;

-- Primeiro "R$ 1.549,90" do post -> 1549.90 (null se nao tiver preco).
create or replace function private.radar_preco(p_texto text)
returns numeric
language sql
immutable
set search_path = pg_catalog, pg_temp
as $$
  select nullif(replace(replace(m[1], '.', ''), ',', '.'), '')::numeric
    from regexp_match(p_texto, 'R\$\s*([0-9][0-9.]*(?:,[0-9]{1,2})?)') m
$$;

-- HTML do texto do post -> texto puro. O Telegram escreve o cifrao como
-- &#036; ("R&#036; 855"): sem decodificar, o preco nao aparece.
create or replace function private.radar_texto_html(p_html text)
returns text
language sql
immutable
set search_path = pg_catalog, pg_temp
as $$
  select btrim(replace(replace(replace(replace(replace(replace(replace(replace(replace(
           regexp_replace(regexp_replace(coalesce(p_html, ''), '<br\s*/?>', E'\n', 'gi'), '<[^>]+>', '', 'g'),
           '&#036;', '$'), '&#36;', '$'), '&#039;', ''''), '&quot;', '"'), '&#39;', ''''),
           '&lt;', '<'), '&gt;', '>'), '&nbsp;', ' '), '&amp;', '&'))
$$;

-- Pagina t.me/s/<canal> -> um registro por post. O padrao do texto comeca com
-- quantificador nao guloso de proposito: no Postgres isso faz o padrao inteiro
-- pegar o trecho mais curto (ate o primeiro </div>).
create or replace function private.radar_posts(p_html text)
returns table (id_post bigint, dta_post timestamptz, texto text)
language sql
immutable
set search_path = pg_catalog, pg_temp
as $$
  select (regexp_match(b, 'data-post="[^"/]+/([0-9]+)"'))[1]::bigint,
         (regexp_match(b, 'datetime="([^"]+)"'))[1]::timestamptz,
         private.radar_texto_html((regexp_match(b, 'tgme_widget_message_text[^>]*?>(.*?)</div>'))[1])
    from unnest(string_to_array(p_html, 'class="tgme_widget_message_wrap')) with ordinality as x(b, n)
   where n > 1
     and b ~ 'data-post="[^"/]+/[0-9]+"'
$$;

-- ─── aviso ──────────────────────────────────────────────────────────────────

-- Posta um embed no Discord pelo webhook do Vault. Canal sem webhook cai no
-- #alertas (ex.: um #ofertas ainda nao criado).
create or replace function private.radar_avisar(p_canal text, p_titulo text, p_texto text,
                                                p_url text default null, p_quando timestamptz default null,
                                                p_cor integer default 3111499)
returns void
language plpgsql
security definer
set search_path = pg_catalog, pg_temp
as $$
declare
  v_webhook text;
begin
  select decrypted_secret into v_webhook from vault.decrypted_secrets
   where name = 'discord_webhook_' || p_canal;
  if coalesce(v_webhook, '') = '' then
    select decrypted_secret into v_webhook from vault.decrypted_secrets
     where name = 'discord_webhook_alertas';
  end if;
  if coalesce(v_webhook, '') = '' then
    raise warning 'radar: sem webhook do Discord no Vault (discord_webhook_%)', p_canal;
    return;
  end if;
  perform net.http_post(
    url := v_webhook,
    body := jsonb_build_object(
      'username', 'radar de ofertas',
      'embeds', jsonb_build_array(jsonb_strip_nulls(jsonb_build_object(
        'title', left(p_titulo, 250),
        'url', p_url,
        'description', left(p_texto, 3500),
        'color', p_cor,
        'timestamp', p_quando))),
      'allowed_mentions', jsonb_build_object('parse', jsonb_build_array())),
    headers := jsonb_build_object('Content-Type', 'application/json', 'User-Agent', 'radar-ofertas-dmp'),
    timeout_milliseconds := 10000
  );
end;
$$;

-- ─── rodada (pg_cron a cada 20 s) ───────────────────────────────────────────

create or replace function private.radar_rodada()
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, pg_temp
as $$
declare
  f record;
  r record;
  p record;
  pr record;
  v_achou boolean;
  v_ok boolean;
  v_motivo text;
  v_max bigint;
  v_lidos integer := 0;
  v_avisos integer := 0;
  v_norm text;
  v_preco numeric;
  v_id bigint;
  v_url text;
  v_preco_txt text;
begin
  for f in select * from private.radar_fontes where ativo order by canal_telegram loop
    if f.pedido_id is not null then
      select * into r from net._http_response where id = f.pedido_id;
      v_achou := found;
      if not v_achou and f.pedido_em > now() - interval '20 seconds' then
        continue;  -- resposta ainda a caminho: espera, sem pedir de novo
      end if;

      -- 200 sem o cabecalho do canal = pagina mudou ou bloqueio: conta como falha.
      v_ok := v_achou and not coalesce(r.timed_out, false) and r.status_code = 200
              and position('tgme_channel_info' in coalesce(r.content, '')) > 0;

      if v_ok then
        v_max := f.ultimo_post;
        for p in select * from private.radar_posts(r.content)
                  where id_post > coalesce(f.ultimo_post, 0) order by id_post loop
          v_lidos := v_lidos + 1;
          v_max := greatest(coalesce(v_max, 0), p.id_post);
          v_norm := private.radar_normalizar(p.texto);
          v_preco := private.radar_preco(p.texto);

          for pr in select * from private.radar_produtos
                     where ativo
                       and private.radar_casa(v_norm, termos, excluir)
                       and (preco_max is null or v_preco is null or v_preco <= preco_max) loop
            v_id := null;
            insert into private.radar_avisos (id_produto, canal_telegram, id_post, preco, texto, dta_post)
            values (pr.id, f.canal_telegram, p.id_post, v_preco, p.texto, p.dta_post)
            on conflict do nothing
            returning id into v_id;

            if v_id is not null then
              v_avisos := v_avisos + 1;
              v_url := format('https://t.me/%s/%s', f.canal_telegram, p.id_post);
              v_preco_txt := regexp_replace(replace(to_char(v_preco, 'FM9999999990.00'), '.', ','), ',00$', '');
              perform private.radar_avisar(
                pr.canal,
                '🔥 ' || pr.nome || coalesce(' por R$ ' || v_preco_txt, ''),
                p.texto || format(E'\n\n[Abrir o post no Telegram](%s) · t.me/%s', v_url, f.canal_telegram),
                v_url, p.dta_post);
            end if;
          end loop;
        end loop;

        update private.radar_fontes
           set ultimo_post = v_max, falhas_seguidas = 0, lido_em = now(), estado = 'ok',
               mudou_em = case when f.estado = 'falha' then now() else mudou_em end
         where canal_telegram = f.canal_telegram;

        if f.estado = 'falha' then
          perform private.radar_avisar('alertas',
            format('✅ Radar de ofertas voltou a ler t.me/%s', f.canal_telegram),
            format('Ficou sem ler por cerca de %s min.',
                   greatest(1, round(extract(epoch from (now() - f.mudou_em)) / 60))),
            p_cor := 3111499);
        end if;
      else
        v_motivo := case when not v_achou then 'sem resposta'
                         when coalesce(r.timed_out, false) then 'demorou mais de 15 s'
                         when r.status_code is null then coalesce(left(r.error_msg, 80), 'erro de rede')
                         when r.status_code <> 200 then 'HTTP ' || r.status_code
                         else 'pagina sem o cabecalho do canal (mudou o formato?)' end;

        update private.radar_fontes set falhas_seguidas = falhas_seguidas + 1
         where canal_telegram = f.canal_telegram;

        if f.estado = 'ok' and f.falhas_seguidas + 1 >= 15 then
          update private.radar_fontes set estado = 'falha', mudou_em = now()
           where canal_telegram = f.canal_telegram;
          perform private.radar_avisar('alertas',
            format('🔴 Radar de ofertas sem ler t.me/%s', f.canal_telegram),
            format('%s, há 5 min seguidos. Ofertas desse canal não estão sendo avisadas.', v_motivo),
            p_cor := 11680306);
        end if;
      end if;

      -- A pagina tem ~30-110 KB: apaga ja, sem esperar as 6 h do pg_net.
      delete from net._http_response where id = f.pedido_id;
    end if;

    update private.radar_fontes
       set pedido_id = net.http_get(
             url := 'https://t.me/s/' || canal_telegram || coalesce('?after=' || ultimo_post, ''),
             headers := jsonb_build_object('User-Agent', 'Mozilla/5.0 (radar-ofertas-dmp)'),
             timeout_milliseconds := 15000),
           pedido_em = now()
     where canal_telegram = f.canal_telegram;
  end loop;

  return jsonb_build_object('posts_lidos', v_lidos, 'avisos', v_avisos);
end;
$$;

revoke all on function private.radar_normalizar(text) from public, anon, authenticated;
revoke all on function private.radar_regex(text) from public, anon, authenticated;
revoke all on function private.radar_casa(text, text[], text[]) from public, anon, authenticated;
revoke all on function private.radar_preco(text) from public, anon, authenticated;
revoke all on function private.radar_texto_html(text) from public, anon, authenticated;
revoke all on function private.radar_posts(text) from public, anon, authenticated;
revoke all on function private.radar_avisar(text, text, text, text, timestamptz, integer) from public, anon, authenticated;
revoke all on function private.radar_rodada() from public, anon, authenticated;

-- ─── retencao e agendamento ─────────────────────────────────────────────────

-- radar_avisos entra na retencao de 30 dias (resto igual a 20261125020200).
-- Apagar aviso antigo nao reavisa: ultimo_post so anda para frente.
create or replace function private.aplicar_retencao()
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, pg_temp
as $$
declare
  v_hist bigint; v_notif bigint; v_sync bigint; v_radar bigint;
begin
  delete from public.historico_cargas where dta_ini < now() - interval '30 days';
  get diagnostics v_hist = row_count;
  delete from public.notificacoes_hub where dta_add < now() - interval '30 days';
  get diagnostics v_notif = row_count;
  delete from openfinance.sync_execucoes where iniciado_em < now() - interval '30 days';
  get diagnostics v_sync = row_count;
  delete from private.radar_avisos where avisado_em < now() - interval '30 days';
  get diagnostics v_radar = row_count;
  return jsonb_build_object('historico_cargas', v_hist, 'notificacoes_hub', v_notif,
                            'sync_execucoes', v_sync, 'radar_avisos', v_radar);
end;
$$;

revoke all on function private.aplicar_retencao() from public, anon, authenticated;

-- A cada 20 s sao ~4.300 linhas por dia em cron.job_run_details: as do radar
-- ficam so 1 dia (o resto continua com 7). Mesmo nome = substitui o job.
select cron.schedule('limpar_historico_pg_cron', '30 3 * * *',
  $$delete from cron.job_run_details
     where end_time < now() - interval '7 days'
        or (jobid = (select jobid from cron.job where jobname = 'radar_ofertas')
            and end_time < now() - interval '1 day')$$);
