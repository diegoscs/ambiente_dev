-- Espelho de dbo.controle_cargas do Postgres local (banco dm).
-- A tabela local e a fonte da verdade; aqui e copia, atualizada por upsert
-- em id_carga pelo robo 002 (check_supabase).
create table if not exists public.controle_cargas (
    id_carga    integer primary key,
    nome_carga  text not null unique,
    descricao   text,
    status      text,
    dta_ini     timestamptz,
    dta_fim     timestamptz,
    tempo_min   integer not null default 30,
    dias_semana smallint[] not null default '{1,2,3,4,5,6,7}',
    flg_ativo   boolean not null default true,
    origem      text,
    script      text,
    dta_add     timestamptz not null default now(),
    dta_modif   timestamptz not null default now(),
    constraint ck_status check (status = any (array['RUNNING','SUCCESS','ERROR']))
);

comment on table public.controle_cargas is
    'Espelho de dbo.controle_cargas (Postgres local dm). Fonte da verdade e o local; escrita apenas pelo robo 002 com a service_role.';

-- RLS ligada sem policy: o robo usa a service_role, que ignora RLS por
-- definicao. Sem policy, a anon key nao le nem escreve nada aqui - e o
-- comportamento desejado para uma tabela de monitoramento interno.
alter table public.controle_cargas enable row level security;
