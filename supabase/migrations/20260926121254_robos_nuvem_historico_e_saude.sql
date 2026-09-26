-- Colunas novas na linha de controle: onde rodou, o que aconteceu e o link do run.
alter table public.controle_cargas
  add column if not exists ambiente text,
  add column if not exists mensagem text,
  add column if not exists url_execucao text,
  add column if not exists atraso_max_horas integer not null default 26;

comment on column public.controle_cargas.ambiente is 'LOCAL (Agendador do Windows) ou CLOUD (GitHub Actions) - quem fez a ultima execucao';
comment on column public.controle_cargas.mensagem is 'Resumo da ultima execucao, ou o erro';
comment on column public.controle_cargas.url_execucao is 'Link do run no GitHub Actions (vazio quando roda no PC)';
comment on column public.controle_cargas.atraso_max_horas is 'Sem execucao fechada ha mais que isso, a vw_saude_robos marca ATRASADO';

-- Historico: uma linha por execucao fechada. A controle_cargas guarda so a ultima.
create table if not exists public.historico_cargas (
  id           bigint generated always as identity primary key,
  id_carga     integer not null references public.controle_cargas (id_carga),
  status       text not null check (status in ('SUCCESS', 'ERROR')),
  dta_ini      timestamptz not null,
  dta_fim      timestamptz not null,
  ambiente     text,
  qtd_itens    integer,
  mensagem     text,
  url_execucao text,
  dta_add      timestamptz not null default now()
);

comment on table public.historico_cargas is 'Uma linha por execucao fechada dos robos. qtd_itens = trabalho feito (commits no 001, pings no 002); 0 = execucao que nao precisou fazer nada';

create index if not exists ix_historico_cargas_carga_ini on public.historico_cargas (id_carga, dta_ini desc);

-- Mesmo regime da controle_cargas: RLS ligada e sem policy. So a service_role escreve.
alter table public.historico_cargas enable row level security;

-- Robo 001 passa a existir no Supabase.
insert into public.controle_cargas (id_carga, nome_carga, descricao, tempo_min, dias_semana, flg_ativo, origem, script, atraso_max_horas)
values (1, '001 - Check GitHub', 'Commits diarios no repo daily-log (calendario de contribuicoes)', 10, '{1,2,3,4,5,6,7}', true, 'Python/API', '001_check_github.py', 26)
on conflict (id_carga) do nothing;

update public.controle_cargas set atraso_max_horas = 26 where id_carga = 2;

-- Saude de cada robo, calculada na hora da leitura. E o que o hub mostra.
create or replace view public.vw_saude_robos
with (security_invoker = true) as
select
  c.id_carga,
  c.nome_carga,
  c.status,
  c.ambiente,
  c.dta_ini,
  c.dta_fim,
  c.mensagem,
  c.url_execucao,
  c.atraso_max_horas,
  round(extract(epoch from (now() - coalesce(c.dta_fim, c.dta_ini))) / 3600.0, 1) as horas_desde,
  case
    when c.dta_ini is null then 'NUNCA_RODOU'
    when c.status = 'RUNNING' and c.dta_ini < now() - make_interval(mins => c.tempo_min) then 'TRAVADO'
    when c.status = 'RUNNING' then 'RODANDO'
    when c.status = 'ERROR' then 'ERRO'
    when c.dta_fim < now() - make_interval(hours => c.atraso_max_horas) then 'ATRASADO'
    else 'OK'
  end as saude
from public.controle_cargas c
where c.flg_ativo;

comment on view public.vw_saude_robos is 'OK / ERRO / ATRASADO / TRAVADO / RODANDO / NUNCA_RODOU por robo. ATRASADO pega o robo que simplesmente nao rodou.';
