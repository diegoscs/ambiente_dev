-- Notificacoes que aparecem no hub. Quem escreve: o vigia (service_role).
-- Quem le e marca como lida: o leitor do hub.
create table if not exists public.notificacoes_hub (
  id        bigint generated always as identity primary key,
  dta_add   timestamptz not null default now(),
  origem    text not null default 'vigia',
  nivel     text not null check (nivel in ('info', 'atencao', 'resolvido')),
  titulo    text not null,
  detalhe   text,
  lida      boolean not null default false
);

comment on table public.notificacoes_hub is 'Feed de notificacoes do hub. O vigia grava uma por verificacao: info (tudo em dia), atencao (algum robo com problema), resolvido (voltou ao normal).';

create index if not exists ix_notificacoes_hub_dta on public.notificacoes_hub (dta_add desc);

alter table public.notificacoes_hub enable row level security;

grant select on public.notificacoes_hub to authenticated;
-- O leitor so pode mexer na coluna lida.
grant update (lida) on public.notificacoes_hub to authenticated;

create policy hub_leitura on public.notificacoes_hub
  for select to authenticated using ((select private.eh_leitor_hub()));

create policy hub_marcar_lida on public.notificacoes_hub
  for update to authenticated
  using ((select private.eh_leitor_hub()))
  with check ((select private.eh_leitor_hub()));
