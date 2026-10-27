-- Ligar/desligar o server de Minecraft pelo hub. O hub grava o pedido; o
-- monitor do PC (automacoes/monitor_minecraft, service_role) executa em ate
-- 1 minuto e fecha o pedido com o resultado.
create table if not exists public.minecraft_comandos (
  id            bigint generated always as identity primary key,
  acao          text not null check (acao in ('ligar', 'desligar')),
  status        text not null default 'pendente'
                check (status in ('pendente', 'executando', 'feito', 'ignorado', 'erro')),
  mensagem      text,
  pedido_por    uuid default auth.uid(),
  dta_pedido    timestamptz not null default now(),
  dta_execucao  timestamptz
);

comment on table public.minecraft_comandos is 'Fila de ligar/desligar do server de Minecraft. Pedido com mais de 10 min sem o PC pegar vira ignorado (nao liga o server horas depois).';

create index if not exists ix_minecraft_comandos_dta on public.minecraft_comandos (dta_pedido desc);

-- Um pedido aberto por vez: clique repetido ou duas abas nao empilham ordens.
create unique index if not exists uq_minecraft_comandos_um_aberto
  on public.minecraft_comandos ((true)) where status in ('pendente', 'executando');

alter table public.minecraft_comandos enable row level security;

-- O leitor do hub le e pede; so escolhe a acao. Status, autor e horarios
-- vem dos defaults, e o resto quem escreve e o monitor.
revoke all on public.minecraft_comandos from anon, authenticated;
grant select on public.minecraft_comandos to authenticated;
grant insert (acao) on public.minecraft_comandos to authenticated;

create policy hub_leitura on public.minecraft_comandos
  for select to authenticated using ((select private.eh_leitor_hub()));

create policy hub_pedir on public.minecraft_comandos
  for insert to authenticated
  with check ((select private.eh_leitor_hub()) and status = 'pendente' and pedido_por = auth.uid());
