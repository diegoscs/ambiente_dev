# -*- coding: utf-8 -*-
# =============================================
# AUTOR          : Diego Candido
# DATA CRIACAO   : 05/09/2026
# DESCRICAO      : Biblioteca compartilhada dos robos do ambiente_dev.
#                  Mesmo papel da marche_lib no trabalho: credenciais, log,
#                  HTTP e controle de cargas (Supabase) em um lugar so.
#
# USO NO ROBO    : sys.path.insert(0, str(Path(__file__).parent.parent.parent))
#                  import lib_dscs as dl
#
#                  dl.registrar_carga_supabase(IDCARGA, dl.STATUS_INICIO, ...)
#                  ...
#                  dl.registrar_carga_supabase(IDCARGA, dl.STATUS_SUCESSO, ...)
#                  Esqueleto completo em automacoes\_modelo.
# =============================================
from __future__ import annotations

from .api import chamar_api_json
from .config import (
    ENV_FILE,
    RAIZ,
    ler_env,
    obter_variavel,
)
from .log import (
    configurar_logger,
    linhas_do_log,
    log,
    log_erro,
    logar_contexto,
    logar_traceback,
    salvar_log_erro,
)
from .notificacao import (
    alertar_erro_robo,
    alertar_telegram,
    telegram_configurado,
)
from .retry import executar_com_retry
from .supabase import (
    MODO_CLOUD,
    MODO_LOCAL,
    STATUS_ERRO,
    STATUS_INICIO,
    STATUS_SUCESSO,
    TABELA_CONTROLE_SUPABASE,
    SAUDE_BOA,
    TABELA_HISTORICO_SUPABASE,
    comandos_minecraft_abertos,
    fechar_comando_minecraft,
    gravar_eventos_minecraft,
    gravar_status_minecraft,
    ler_saude_robos,
    modo_execucao,
    notificar_hub,
    ultima_notificacao,
    ultimo_evento_minecraft,
    registrar_carga_supabase,
    supabase_apagar,
    supabase_atualizar,
    supabase_configurado,
    supabase_inserir,
    supabase_ler,
    trabalho_feito_no_dia,
    url_execucao_actions,
)

# 2.0.0 (27/10/2026): sai o modo LOCAL (Postgres dm, dbo.controle_cargas e a
# trava em temp\estado.json). Os STATUS_* passam a morar no supabase.py.
__version__ = "2.0.0"

__all__ = [
    # config
    "RAIZ",
    "ENV_FILE",
    "ler_env",
    "obter_variavel",
    # log
    "configurar_logger",
    "log",
    "log_erro",
    "logar_contexto",
    "logar_traceback",
    "salvar_log_erro",
    "linhas_do_log",
    # notificacao
    "alertar_telegram",
    "alertar_erro_robo",
    "telegram_configurado",
    # retry
    "executar_com_retry",
    # api
    "chamar_api_json",
    # supabase (controle de cargas)
    "MODO_LOCAL",
    "MODO_CLOUD",
    "STATUS_INICIO",
    "STATUS_SUCESSO",
    "STATUS_ERRO",
    "TABELA_CONTROLE_SUPABASE",
    "TABELA_HISTORICO_SUPABASE",
    "modo_execucao",
    "supabase_configurado",
    "url_execucao_actions",
    "registrar_carga_supabase",
    "trabalho_feito_no_dia",
    "SAUDE_BOA",
    "ler_saude_robos",
    "notificar_hub",
    "ultima_notificacao",
    "gravar_status_minecraft",
    "gravar_eventos_minecraft",
    "ultimo_evento_minecraft",
    "comandos_minecraft_abertos",
    "fechar_comando_minecraft",
    "supabase_ler",
    "supabase_inserir",
    "supabase_atualizar",
    "supabase_apagar",
]
