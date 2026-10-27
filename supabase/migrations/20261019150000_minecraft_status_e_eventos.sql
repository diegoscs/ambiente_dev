-- Servidor de Minecraft da galera no hub. Quem escreve: o monitor do PC
-- (automacoes/monitor_minecraft, service_role). Quem le: o leitor do hub.

-- ─── status: linha unica, sobrescrita a cada minuto ─────────────────────────
create table if not exists public.minecraft_status (
  id                smallint primary key default 1 check (id = 1),
  online            boolean not null,
  jogadores_online  integer not null default 0,
  jogadores_max     integer,
  jogadores         text[] not null default '{}',
  versao            text,
  motd              text,
  latencia_ms       integer,
  erro              text,
  dta_verificacao   timestamptz not null default now(),
  dta_mudanca       timestamptz not null default now()
);

comment on table public.minecraft_status is 'Ultima leitura do server de Minecraft pelo monitor do PC. dta_verificacao velha = PC desligado ou sem internet (o hub mostra SEM SINAL).';
comment on column public.minecraft_status.dta_mudanca is 'Quando online mudou pela ultima vez: "online desde" / "offline desde".';

-- Horarios carimbados pelo banco, nao pelo relogio do PC.
create or replace function private.minecraft_status_carimbo()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.dta_verificacao := now();
  if tg_op = 'UPDATE' and new.online is not distinct from old.online then
    new.dta_mudanca := old.dta_mudanca;
  else
    new.dta_mudanca := now();
  end if;
  return new;
end;
$$;

revoke all on function private.minecraft_status_carimbo() from public, anon, authenticated;

drop trigger if exists tg_minecraft_status_carimbo on public.minecraft_status;
create trigger tg_minecraft_status_carimbo
  before insert or update on public.minecraft_status
  for each row execute function private.minecraft_status_carimbo();

-- ─── eventos: chat, comandos, entradas/saidas e conquistas, lidos do log ────
create table if not exists public.minecraft_eventos (
  id          bigint generated always as identity primary key,
  dta_evento  timestamptz not null,
  tipo        text not null check (tipo in ('chat', 'comando', 'entrou', 'saiu', 'conquista')),
  jogador     text not null,
  texto       text not null default '',
  dta_add     timestamptz not null default now(),
  -- O monitor reenvia o que pode ja ter mandado (rotacao do log, retry):
  -- a chave natural deixa o insert idempotente.
  constraint uq_minecraft_eventos unique (dta_evento, tipo, jogador, texto)
);

comment on table public.minecraft_eventos is 'Eventos do server de Minecraft extraidos do latest.log (e do log do KubeJS, para comandos de qualquer jogador).';

create index if not exists ix_minecraft_eventos_dta on public.minecraft_eventos (dta_evento desc);

-- ─── acesso ─────────────────────────────────────────────────────────────────
alter table public.minecraft_status enable row level security;
alter table public.minecraft_eventos enable row level security;

-- O Supabase concede tudo por padrao: tira e devolve so a leitura.
revoke all on public.minecraft_status, public.minecraft_eventos from anon, authenticated;
grant select on public.minecraft_status, public.minecraft_eventos to authenticated;

create policy hub_leitura on public.minecraft_status
  for select to authenticated using ((select private.eh_leitor_hub()));

create policy hub_leitura on public.minecraft_eventos
  for select to authenticated using ((select private.eh_leitor_hub()));
