-- Servidor de Minecraft na VM do Google (automacoes/minecraft_gcp).
-- Quem escreve: o monitor da VM (service_role). Quem le: as funcoes do hub
-- publico do servidor (hub_minecraft/api, service_role). Nenhum acesso direto
-- de anon/authenticated nas tabelas novas.

-- ─── status: estado da VM, ultima atividade e IP ────────────────────────────
alter table public.minecraft_status
  add column if not exists estado_vm text check (estado_vm in ('ligada', 'desligando', 'desligada')),
  add column if not exists dta_ultima_atividade timestamptz,
  add column if not exists ip text;

comment on column public.minecraft_status.estado_vm is 'Gravado pelo monitor da VM. desligada = a VM se desligou de proposito (inatividade/pedido): linha velha nao e "sem sinal".';
comment on column public.minecraft_status.dta_ultima_atividade is 'Ultima vez com jogador online (ou o boot). A VM desliga 15 min depois disso.';

-- ─── sessoes da VM: uma linha por boot ──────────────────────────────────────
create table if not exists public.minecraft_sessoes (
  id                bigint generated always as identity primary key,
  boot_id           text not null unique,
  maquina           text,
  dta_ligou         timestamptz not null,
  dta_ultimo_sinal  timestamptz,
  dta_desligou      timestamptz,
  motivo            text
);

comment on table public.minecraft_sessoes is 'Cada vez que a VM ligou. Base do custo estimado do hub. dta_desligou nula com dta_ultimo_sinal velho = desligou sem avisar (fechada no boot seguinte como inesperado).';

create index if not exists ix_minecraft_sessoes_ligou on public.minecraft_sessoes (dta_ligou desc);

-- ─── backups do mundo ───────────────────────────────────────────────────────
create table if not exists public.minecraft_backups (
  id         bigint generated always as identity primary key,
  dta        timestamptz not null default now(),
  arquivo    text not null,
  bytes      bigint,
  duracao_s  numeric(8, 1),
  destino    text,
  ok         boolean not null,
  erro       text
);

comment on table public.minecraft_backups is 'Backup do mundo feito quando o servidor para (ExecStopPost do minecraft.service), enviado ao Cloud Storage.';

create index if not exists ix_minecraft_backups_dta on public.minecraft_backups (dta desc);

-- ─── pedidos: nome de quem pediu pelo hub publico ───────────────────────────
alter table public.minecraft_comandos add column if not exists nome text;

-- ─── acesso ─────────────────────────────────────────────────────────────────
alter table public.minecraft_sessoes enable row level security;
alter table public.minecraft_backups enable row level security;
revoke all on public.minecraft_sessoes, public.minecraft_backups from anon, authenticated;
-- Sem policy: so a service_role (que ignora RLS) le e escreve.
