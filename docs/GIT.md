# Git e GitHub neste repositório

Como as mudanças chegam na `main`. A `main` é o que está valendo: o `pg_cron`
do Supabase dispara os robôs a partir dela e o hub é publicado dela.

## Fluxo

```powershell
git switch main; git pull                  # 1. parte da main atualizada
git switch -c feat/robo-005-nome           # 2. uma branch por mudança
# ... commits pequenos; o sync do VS Code envia a branch, não a main
gh pr create --fill                        # 3. PR: revisão do diff e verificações
gh pr merge --squash --delete-branch       # 4. junta como um commit só
git switch main; git pull                  # 5. volta para a main
```

- **Branch curta**: horas ou dias. Antes de juntar, se a `main` andou:
  `git pull --rebase origin main` (o conflito se resolve na branch).
- **Squash merge**: a `main` fica com uma linha por mudança, com a mensagem do PR.
- **Sem `push --force` e sem `reset --hard` na `main`.** Para desfazer algo que
  já está nela: `git revert <commit>`.

## Nomes

Branch e commit usam o mesmo prefixo ([Conventional Commits](https://www.conventionalcommits.org/pt-br/)):

| Prefixo | Quando |
|---|---|
| `feat` | algo novo (robô, tela, função) |
| `fix` | correção |
| `chore` | manutenção, configuração, limpeza |
| `docs` | só documentação |
| `refactor` | reorganiza código sem mudar o comportamento |

Branch: `feat/robo-005-nome`, `fix/hub-login`. Commit: `feat(hub): ...`, com
o escopo entre parênteses quando ajuda.

## Testar um robô antes do merge

O `pg_cron` dispara o workflow pela `main`, então uma mudança só vale depois
do merge. Para rodar a versão da branch no Actions:

```powershell
gh workflow run robo_001_check_github.yml --ref feat/minha-branch
```

Sem `--dry-run` no robô, a execução grava no Supabase de verdade.

## Versões

A `lib_dscs` tem tag por versão (`lib_dscs-v2.1.0`), no commit que mudou o
`__version__` em `lib_dscs/__init__.py`:

```powershell
git tag -a lib_dscs-v2.2.0 -m "lib_dscs 2.2.0: o que mudou"
git push origin lib_dscs-v2.2.0
```

## Arquivos de controle

| Arquivo | Para quê |
|---|---|
| `.gitignore` | o que nunca entra: `.env`, saídas dos robôs e as pastas `projetos/`, `clientes/` e `arquivo/` (cada projeto ali tem o seu repositório) |
| `.gitattributes` | quebra de linha LF em tudo, CRLF nos `.bat` |
| `.git/info/exclude` | igual ao `.gitignore`, mas só no PC e sem commit |

## Configuração do PC (uma vez, vale para todos os repositórios)

```powershell
git config --global init.defaultBranch main
git config --global pull.rebase true          # pull sem commit de merge
git config --global rebase.autoStash true     # pull com alteração local aberta
git config --global fetch.prune true          # some branch apagada no GitHub
git config --global push.autoSetupRemote true # primeiro push de branch nova
```

Identidade: `diegoscs <diegoscs@users.noreply.github.com>`, sem e-mail pessoal
nos commits.
