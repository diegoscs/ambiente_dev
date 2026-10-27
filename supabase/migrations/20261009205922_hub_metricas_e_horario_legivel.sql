-- Horario legivel em Sao Paulo: "hoje 07:38", "ontem 13:09", "seg 07:12", "02/10 07:38"
create or replace function public.fmt_quando(p_ts timestamptz)
returns text language sql stable set search_path = pg_catalog, public as $$
  select case
    when p_ts is null then null
    when (p_ts at time zone 'America/Sao_Paulo')::date = (now() at time zone 'America/Sao_Paulo')::date
      then 'hoje ' || to_char(p_ts at time zone 'America/Sao_Paulo', 'HH24:MI')
    when (p_ts at time zone 'America/Sao_Paulo')::date = (now() at time zone 'America/Sao_Paulo')::date - 1
      then 'ontem ' || to_char(p_ts at time zone 'America/Sao_Paulo', 'HH24:MI')
    when (p_ts at time zone 'America/Sao_Paulo')::date > (now() at time zone 'America/Sao_Paulo')::date - 7
      then (array['dom','seg','ter','qua','qui','sex','sab'])[extract(dow from p_ts at time zone 'America/Sao_Paulo')::int + 1]
           || ' ' || to_char(p_ts at time zone 'America/Sao_Paulo', 'HH24:MI')
    else to_char(p_ts at time zone 'America/Sao_Paulo', 'DD/MM HH24:MI')
  end
$$;

-- "ha 5 min", "ha 2 h", "ha 3 dias"
create or replace function public.fmt_ha_quanto(p_ts timestamptz)
returns text language sql stable set search_path = pg_catalog, public as $$
  select case
    when p_ts is null then null
    when now() - p_ts < interval '1 minute' then 'agora'
    when now() - p_ts < interval '1 hour' then 'há ' || floor(extract(epoch from now() - p_ts) / 60)::int || ' min'
    when now() - p_ts < interval '1 day' then 'há ' || floor(extract(epoch from now() - p_ts) / 3600)::int || ' h'
    else 'há ' || floor(extract(epoch from now() - p_ts) / 86400)::int
         || case when now() - p_ts < interval '2 days' then ' dia' else ' dias' end
  end
$$;

-- "28s", "1m 12s"
create or replace function public.fmt_duracao(p_seg numeric)
returns text language sql immutable set search_path = pg_catalog as $$
  select case
    when p_seg is null then null
    when p_seg < 60 then round(p_seg)::int || 's'
    else floor(p_seg / 60)::int || 'm ' || lpad((round(p_seg)::int % 60)::text, 2, '0') || 's'
  end
$$;

-- Cards de metricas por robo (ultimos 30 dias)
create or replace view public.vw_metricas_robos with (security_invoker = true) as
with h as (
  select h.*, extract(epoch from (h.dta_fim - h.dta_ini)) as dur_s
  from public.historico_cargas h
  where h.dta_ini >= now() - interval '30 days'
),
ult as (
  select distinct on (id_carga) id_carga, status, dta_ini, dta_fim, qtd_itens, dur_s
  from h order by id_carga, dta_ini desc
)
select
  c.id_carga,
  c.nome_carga,
  count(h.*)::int                                              as execucoes_30d,
  count(h.*) filter (where h.status = 'SUCCESS')::int          as sucessos_30d,
  count(h.*) filter (where h.status = 'ERROR')::int            as erros_30d,
  round(100.0 * count(h.*) filter (where h.status = 'SUCCESS') / nullif(count(h.*), 0), 1) as taxa_sucesso_pct,
  round(avg(h.dur_s)::numeric, 1)                              as duracao_media_s,
  round(max(h.dur_s)::numeric, 1)                              as duracao_max_s,
  public.fmt_duracao(avg(h.dur_s)::numeric)                    as duracao_media_txt,
  round(avg(h.qtd_itens)::numeric, 1)                          as itens_medio,
  coalesce(sum(h.qtd_itens), 0)::int                           as itens_total_30d,
  u.status                                                     as ultima_status,
  u.dta_ini                                                    as ultima_ini,
  public.fmt_quando(u.dta_ini)                                 as ultima_quando,
  public.fmt_ha_quanto(coalesce(u.dta_fim, u.dta_ini))         as ultima_ha_quanto,
  public.fmt_duracao(u.dur_s::numeric)                         as ultima_duracao_txt
from public.controle_cargas c
left join h   on h.id_carga = c.id_carga
left join ult u on u.id_carga = c.id_carga
where c.flg_ativo
group by c.id_carga, c.nome_carga, u.status, u.dta_ini, u.dta_fim, u.dur_s;

-- Serie diaria para graficos (ultimos 30 dias, dia em Sao Paulo)
create or replace view public.vw_execucoes_diarias with (security_invoker = true) as
select
  h.id_carga,
  (h.dta_ini at time zone 'America/Sao_Paulo')::date           as dia,
  to_char((h.dta_ini at time zone 'America/Sao_Paulo')::date, 'DD/MM') as dia_txt,
  count(*)::int                                                as execucoes,
  count(*) filter (where h.status = 'SUCCESS')::int            as sucessos,
  count(*) filter (where h.status = 'ERROR')::int              as erros,
  round(avg(extract(epoch from (h.dta_fim - h.dta_ini)))::numeric, 1) as duracao_media_s,
  coalesce(sum(h.qtd_itens), 0)::int                           as itens
from public.historico_cargas h
where h.dta_ini >= now() - interval '30 days'
group by 1, 2, 3;

-- Historico com horario legivel (lista de execucoes)
create or replace view public.vw_historico_legivel with (security_invoker = true) as
select
  h.id, h.id_carga, c.nome_carga, h.status, h.qtd_itens, h.mensagem, h.url_execucao,
  h.dta_ini, h.dta_fim,
  public.fmt_quando(h.dta_ini)                                 as quando,
  public.fmt_ha_quanto(coalesce(h.dta_fim, h.dta_ini))         as ha_quanto,
  to_char(h.dta_ini at time zone 'America/Sao_Paulo', 'DD/MM/YYYY HH24:MI:SS') as data_hora_completa,
  public.fmt_duracao(extract(epoch from (h.dta_fim - h.dta_ini))::numeric) as duracao_txt
from public.historico_cargas h
join public.controle_cargas c using (id_carga);

grant select on public.vw_metricas_robos, public.vw_execucoes_diarias, public.vw_historico_legivel to authenticated;
grant execute on function public.fmt_quando(timestamptz), public.fmt_ha_quanto(timestamptz), public.fmt_duracao(numeric) to authenticated;
