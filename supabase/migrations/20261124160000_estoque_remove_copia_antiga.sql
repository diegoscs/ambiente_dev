-- O schema estoque mudou para o projeto DMC (oaqhgdewlfjtepjfaiml) em 24/11/2026.
-- Antes de rodar: cada linha das 13 tabelas e as 3 contas conferidas identicas
-- no DMC, e o app em producao lendo so do DMC. Backup: dm_2026-11-24_1306Z.zip.
-- O schema fica vazio ate sair de Data API > Exposed schemas; depois, drop.
drop schema estoque cascade;
create schema estoque;
