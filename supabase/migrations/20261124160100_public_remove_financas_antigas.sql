-- Financas antigas (app arquivado financas-pipeline/web): ninguem em producao
-- le estas tabelas desde 10/2026 (levantamento, secao 4). O financas-app usa so
-- o schema openfinance. Backup: dm_2026-11-24_1306Z.zip.
-- Sem cascade: se algo inesperado depender delas, a migration falha.
drop view public.vw_conferencia_cartao, public.vw_fila_revisao, public.vw_fluxo_mensal,
          public.vw_patrimonio_mensal, public.vw_reconciliacao_mensal, public.vw_ultima_execucao;
drop table public.transacoes, public.faturas, public.snapshots_saldo, public.regras_categoria,
           public.categorias, public.contas, public.ingestion_log, public.perfil, public.usuarios,
           public.ativos, public.posicoes, public.proventos, public.investimentos_historico,
           public.cotacoes, public.indices;
