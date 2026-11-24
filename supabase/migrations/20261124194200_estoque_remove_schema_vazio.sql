-- DMP: sai o schema estoque, vazio desde que o app foi para o DMC
-- (20261124160000_estoque_remove_copia_antiga). Decisao de 24/11/2026.
--
-- ANTES de aplicar: tirar "estoque" de Settings > Data API > Exposed schemas
-- no painel do DMP. Schema exposto que nao existe derruba a API inteira.
drop schema if exists estoque;
