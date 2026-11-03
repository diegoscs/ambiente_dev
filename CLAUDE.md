# ambiente_dev

Robôs em Python agendados no GitHub Actions, com controle de cargas no
Supabase e um hub web (Vercel) para acompanhar pelo celular. Visão geral no
[README.md](README.md).

## Robô novo ou mudança em robô

**Siga [automacoes/PADRAO_ROBOS.md](automacoes/PADRAO_ROBOS.md)** e parta de
[automacoes/_modelo/](automacoes/_modelo). Em resumo:

- Roda no GitHub Actions (`MODO_EXECUCAO=CLOUD`); o PC não é agendador.
- Infra sempre da `lib_dscs` (`import lib_dscs as dl`); nada de conexão, `.env`
  ou HTTP na mão.
- Registro obrigatório com `dl.registrar_carga_supabase` (RUNNING → SUCCESS/ERROR),
  com `mensagem` legível e `qtd_itens` = trabalho que chegou ao destino.
- Trava diária pelo histórico no Supabase (`dl.trabalho_feito_no_dia`), dia UTC.
- `--dry-run`/`--status` não registram status.
- Cadastro em `public.controle_cargas` por migration (com `workflow`,
  `tempo_min`, `atraso_max_horas`): o robô aparece sozinho no hub e no vigia.
- Schema só por migration em `supabase/migrations/`; RLS ligada e `revoke`
  explícito de escrita para `anon`/`authenticated`.
- Secret nunca começa com `GITHUB_`; prefixo novo vai em `PREFIXOS_AMBIENTE`.
- Log só em caso de erro; README do robô com decisões e estado datado.

## Comandos

```powershell
$py = "C:\Users\ferna\AppData\Local\Python\bin\python.exe"
& $py automacoes\NNN_robo\NNN_robo.py --dry-run
$env:MODO_EXECUCAO = "CLOUD"; & $py automacoes\NNN_robo\NNN_robo.py
& $py automacoes\vigia_robos.py        # saude de todos os robos
cd apps\hub; vercel deploy --prod      # hub (ainda sem deploy automatico)
```

## Cuidados

- Mudança vai por branch e PR com squash, nunca direto na `main`: fluxo,
  nomes e versões em [docs/GIT.md](docs/GIT.md).
- Workflows e arquivos podem ser editados direto no site do GitHub: comece
  sempre com `git pull` para não sobrescrever uma edição feita por lá.
- Credencial do GitHub guardada no Git Credential Manager (conta `diegoscs`,
  fixada em `credential.https://github.com.username`). Se o push voltar a pedir
  usuário e senha, confira `cmdkey /list` (duas contas do GitHub travam o GCM).
- No VS Code (`.vscode/settings.json`, fora do repositório), commit já faz
  sync (pull com rebase + push) e o autofetch traz edições feitas no GitHub.
- O `.env` nunca vai para o repositório (confira com `git ls-files`).
- Mudou `apps/hub/` ou `apps/minecraft/hub/`? O deploy na Vercel é manual até
  o repositório ser conectado lá.
- Mudou `apps/minecraft/monitor/` ou `apps/minecraft/gcp/vm/`? Só chega na VM
  com o `publicar_vm.ps1` (VM ligada).
- Supabase do projeto: `mthipdxpedlfnkzddlar` (financas-pipeline, sa-east-1).
