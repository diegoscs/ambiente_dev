-- Limite de inatividade em vigor, gravado pelo monitor da VM para a contagem
-- regressiva do hub: 15 min da VM ligar ate o primeiro jogador entrar (o
-- TLauncher demora para abrir o modpack), 5 min depois que alguem ja jogou.
alter table public.minecraft_status add column if not exists desliga_apos_min integer;

comment on column public.minecraft_status.desliga_apos_min is 'Minutos sem ninguem online ate a VM desligar, em vigor agora (15 antes do primeiro jogador do boot, 5 depois).';
