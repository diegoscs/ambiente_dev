-- Kick de jogador AFK (kubejs/server_scripts/afk_kick.js): o feed ganha o tipo
-- 'afk' (desconectado por inatividade) e o status guarda quem esta parado ha
-- quanto tempo, para o hub mostrar "AFK 6 min" ao lado do nick.
alter table public.minecraft_eventos drop constraint if exists minecraft_eventos_tipo_check;
alter table public.minecraft_eventos add constraint minecraft_eventos_tipo_check
  check (tipo in ('chat', 'comando', 'entrou', 'saiu', 'conquista', 'morte', 'afk'));

alter table public.minecraft_status add column if not exists afk jsonb;

comment on column public.minecraft_status.afk is 'Jogadores parados ha 2+ min: {"nick": minutos}. O servidor kicka aos 10 min (aviso aos 8).';
