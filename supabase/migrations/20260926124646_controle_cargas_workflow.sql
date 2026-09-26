-- Nome do arquivo do workflow no GitHub Actions. O hub usa para o botao
-- "Rodar agora" e para o link; robo novo so precisa preencher aqui.
alter table public.controle_cargas
  add column if not exists workflow text
  constraint ck_workflow check (workflow is null or workflow ~ '^[a-z0-9_]+\.yml$');

comment on column public.controle_cargas.workflow is 'Arquivo em .github/workflows que roda o robo (ex.: robo_001_check_github.yml). Null = sem botao no hub.';

update public.controle_cargas set workflow = 'robo_001_check_github.yml' where id_carga = 1;
update public.controle_cargas set workflow = 'robo_002_check_supabase.yml' where id_carga = 2;

-- A view ganha a coluna no fim (create or replace nao deixa reordenar).
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
  end as saude,
  c.workflow
from public.controle_cargas c
where c.flg_ativo;

revoke select on public.vw_saude_robos from anon;
grant select on public.vw_saude_robos to authenticated;
