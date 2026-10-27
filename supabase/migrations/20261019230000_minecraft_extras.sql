-- Hub do servidor: mortes no feed, desempenho (TPS, CPU, RAM), hora/clima do
-- jogo e ranking da galera. Quem escreve: o monitor da VM (service_role).
-- Quem le: as funcoes do hub_minecraft (service_role). Sem acesso direto de
-- anon/authenticated nas tabelas novas.

-- ─── mortes no feed ─────────────────────────────────────────────────────────
alter table public.minecraft_eventos drop constraint if exists minecraft_eventos_tipo_check;
alter table public.minecraft_eventos add constraint minecraft_eventos_tipo_check
  check (tipo in ('chat', 'comando', 'entrou', 'saiu', 'conquista', 'morte'));

-- ─── status: desempenho e mundo ─────────────────────────────────────────────
alter table public.minecraft_status
  add column if not exists tps           numeric(5, 2),
  add column if not exists mspt          numeric(7, 2),
  add column if not exists cpu_pct       numeric(5, 1),
  add column if not exists ram_usada_mb  integer,
  add column if not exists ram_total_mb  integer,
  add column if not exists java_ram_mb   integer,
  add column if not exists mundo_dia     integer,
  add column if not exists mundo_tick    integer,
  add column if not exists chuva         boolean,
  add column if not exists trovoada      boolean;

comment on column public.minecraft_status.tps is 'Ticks por segundo (20 = sem lag), do /neoforge tps (Overall).';
comment on column public.minecraft_status.mundo_tick is 'Hora do dia no jogo, 0 a 23999 (0 = 06:00).';

-- ─── historico de desempenho: uma linha por minuto com o servidor online ────
create table if not exists public.minecraft_desempenho (
  id            bigint generated always as identity primary key,
  dta           timestamptz not null default now(),
  tps           numeric(5, 2),
  mspt          numeric(7, 2),
  cpu_pct       numeric(5, 1),
  ram_usada_mb  integer,
  java_ram_mb   integer,
  jogadores     integer
);

comment on table public.minecraft_desempenho is 'Uma linha por minuto com o servidor online. O monitor apaga o que tem mais de 7 dias.';

create index if not exists ix_minecraft_desempenho_dta on public.minecraft_desempenho (dta desc);

-- ─── ranking: estatisticas do proprio Minecraft (world/stats) ───────────────
create table if not exists public.minecraft_jogadores (
  jogador           text primary key,
  uuid              text,
  tempo_jogado_min  integer,
  mortes            integer,
  mobs_mortos       integer,
  jogadores_mortos  integer,
  distancia_km      numeric(9, 2),
  blocos_minerados  integer,
  conquistas        integer,
  dta_atualizacao   timestamptz not null default now()
);

comment on table public.minecraft_jogadores is 'Ranking do hub: lido de world/stats e world/advancements a cada 5 min pelo monitor da VM.';

-- ─── acesso ─────────────────────────────────────────────────────────────────
alter table public.minecraft_desempenho enable row level security;
alter table public.minecraft_jogadores enable row level security;
revoke all on public.minecraft_desempenho, public.minecraft_jogadores from anon, authenticated;
