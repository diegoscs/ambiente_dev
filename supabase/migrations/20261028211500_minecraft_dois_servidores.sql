-- Segundo servidor de Minecraft: Pixelmon, numa VM propria ("pixelmon"), com
-- o mesmo monitor e o mesmo hub do Create. Cada tabela minecraft_* ganha a
-- coluna servidor; o que ja existe e do Create ('create', o padrao).
-- Quem escreve: o monitor de cada VM (service_role), com o servidor do .env.
-- Quem le: as funcoes do hub_minecraft (service_role) e o hub dos robos
-- (authenticated, que so olha o Create).

alter table public.minecraft_status     add column if not exists servidor text not null default 'create';
alter table public.minecraft_eventos    add column if not exists servidor text not null default 'create';
alter table public.minecraft_comandos   add column if not exists servidor text not null default 'create';
alter table public.minecraft_sessoes    add column if not exists servidor text not null default 'create';
alter table public.minecraft_backups    add column if not exists servidor text not null default 'create';
alter table public.minecraft_desempenho add column if not exists servidor text not null default 'create';
alter table public.minecraft_jogadores  add column if not exists servidor text not null default 'create';

alter table public.minecraft_status     add constraint minecraft_status_servidor_check     check (servidor in ('create', 'pixelmon'));
alter table public.minecraft_eventos    add constraint minecraft_eventos_servidor_check    check (servidor in ('create', 'pixelmon'));
alter table public.minecraft_comandos   add constraint minecraft_comandos_servidor_check   check (servidor in ('create', 'pixelmon'));
alter table public.minecraft_sessoes    add constraint minecraft_sessoes_servidor_check    check (servidor in ('create', 'pixelmon'));
alter table public.minecraft_backups    add constraint minecraft_backups_servidor_check    check (servidor in ('create', 'pixelmon'));
alter table public.minecraft_desempenho add constraint minecraft_desempenho_servidor_check check (servidor in ('create', 'pixelmon'));
alter table public.minecraft_jogadores  add constraint minecraft_jogadores_servidor_check  check (servidor in ('create', 'pixelmon'));

comment on column public.minecraft_status.servidor is 'create = Create Chronicles (VM minecraft), pixelmon = Pixelmon (VM pixelmon).';

-- ─── status: uma linha por servidor (era a linha unica id = 1) ──────────────
-- A coluna id fica (sempre 1, sem uso): a chave passa a ser o servidor.
alter table public.minecraft_status drop constraint minecraft_status_pkey;
alter table public.minecraft_status add primary key (servidor);
comment on column public.minecraft_status.id is 'Sem uso desde 28/10/2026 (era a linha unica). A chave e servidor.';

-- ─── eventos: o mesmo nick pode entrar nos dois servidores no mesmo instante ─
alter table public.minecraft_eventos drop constraint uq_minecraft_eventos;
alter table public.minecraft_eventos add constraint uq_minecraft_eventos
  unique (servidor, dta_evento, tipo, jogador, texto);
drop index if exists public.ix_minecraft_eventos_dta;
create index ix_minecraft_eventos_dta on public.minecraft_eventos (servidor, dta_evento desc);

-- ─── pedidos: um aberto por vez em cada servidor ────────────────────────────
drop index if exists public.uq_minecraft_comandos_um_aberto;
create unique index uq_minecraft_comandos_um_aberto
  on public.minecraft_comandos (servidor) where status in ('pendente', 'executando');

-- ─── ranking: o mesmo jogador tem uma linha em cada servidor ────────────────
alter table public.minecraft_jogadores drop constraint minecraft_jogadores_pkey;
alter table public.minecraft_jogadores add primary key (servidor, jogador);

-- ─── indices de leitura do hub ──────────────────────────────────────────────
drop index if exists public.ix_minecraft_sessoes_ligou;
create index ix_minecraft_sessoes_ligou on public.minecraft_sessoes (servidor, dta_ligou desc);
drop index if exists public.ix_minecraft_backups_dta;
create index ix_minecraft_backups_dta on public.minecraft_backups (servidor, dta desc);
drop index if exists public.ix_minecraft_desempenho_dta;
create index ix_minecraft_desempenho_dta on public.minecraft_desempenho (servidor, dta desc);
drop index if exists public.ix_minecraft_comandos_dta;
create index ix_minecraft_comandos_dta on public.minecraft_comandos (servidor, dta_pedido desc);

-- Acesso nao muda: RLS ja ligada em todas; o hub dos robos continua pedindo
-- so a acao (servidor fica no padrao 'create') e lendo o que ja lia.
revoke all on public.minecraft_status, public.minecraft_eventos, public.minecraft_comandos,
  public.minecraft_sessoes, public.minecraft_backups, public.minecraft_desempenho,
  public.minecraft_jogadores from anon;
