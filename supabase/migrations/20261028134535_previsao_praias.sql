-- Robo 004 (clima nas praias): score de sol por praia e por dia, de amanha
-- ate a proxima terca. Quem escreve: o robo no Actions (service_role), upsert
-- por (cidade, dia, praia) - rodar de novo so troca pela previsao mais nova.
-- Quem le: o leitor do hub (base do painel web: mapa, outras cidades).
create table if not exists public.previsao_praias (
  cidade           text not null,
  dia              date not null,
  praia            text not null,
  regiao           text not null,
  score            numeric(4,1) not null check (score between 0 and 100),
  score_manha      numeric(4,1) check (score_manha between 0 and 100),
  score_tarde      numeric(4,1) check (score_tarde between 0 and 100),
  faixa            text not null check (faixa in ('sol', 'nublado', 'chuva')),
  grupo_previsao   text not null,
  chuva_prob_max   smallint,
  chuva_mm_total   numeric(5,1),
  nuvens_media     smallint,
  vento_medio_kmh  numeric(4,1),
  temp_max         numeric(4,1),
  uv_max           numeric(3,1),
  latitude         double precision not null,
  longitude        double precision not null,
  dta_coleta       timestamptz not null,
  primary key (cidade, dia, praia)
);

comment on table public.previsao_praias is 'Score de sol (0-100, 9h-17h) por praia e dia, calculado pelo robo 004 a partir da Open-Meteo. Uma linha por (cidade, dia, praia), sempre com a previsao mais recente.';
comment on column public.previsao_praias.grupo_previsao is 'Praias com a mesma letra receberam a mesma previsao do modelo (grade de ~10-25 km): empate entre elas nao e diferenca real.';
comment on column public.previsao_praias.dta_coleta is 'Quando a previsao foi consultada (UTC).';

create index if not exists ix_previsao_praias_dia on public.previsao_praias (dia, score desc);

-- ─── acesso ─────────────────────────────────────────────────────────────────
alter table public.previsao_praias enable row level security;

-- O Supabase concede tudo por padrao: tira e devolve so a leitura.
revoke all on public.previsao_praias from anon, authenticated;
grant select on public.previsao_praias to authenticated;

create policy hub_leitura on public.previsao_praias
  for select to authenticated using ((select private.eh_leitor_hub()));
