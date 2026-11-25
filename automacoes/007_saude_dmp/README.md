# 007 · Saúde do DMP

Irmão do [006](../006_saude_dmc/README.md), para o banco **pessoal** (DMP:
hub, robôs, Minecraft e finanças). Confere todo dia, **só lendo**, se está de pé
e seguro. Erro deixa o run vermelho e avisa em `#alertas`; aviso vai para
`#alertas` só quando muda.

| | |
|---|---|
| Quando | 03:00 de São Paulo, pelo `pg_cron` (única hora cheia livre antes do vigia) |
| `qtd_itens` | checagens que passaram |

| Checagem | Erro | Aviso |
|---|---|---|
| Sites (hub-robos, server-galera, financas-app) | não abre | mais de 5 s |
| Auth do DMP | cadastro aberto ligado | |
| RLS em `public`, `private`, `openfinance` | tabela sem RLS | |
| Papel anônimo | com escrita em tabela ou view | |
| Tamanho do banco | | acima de 400 MB |
| pg_cron | | job que falhou nas últimas 24 h |
| Vault | sem `github_dispatch_token` | |

A API e o banco respondendo já são conferidos pelo keepalive (002), e os
disparos do pg_cron recusados pelo GitHub, pelo vigia.

```powershell
& $py automacoes\007_saude_dmp\007_saude_dmp.py --dry-run
```

## Estado

- **25/11/2026**: criado. O primeiro dry-run achou dois pontos: o Auth do DMP
  aceitava cadastro de qualquer pessoa (corrigir no painel) e o papel anônimo
  tinha escrita na `vw_saude_robos` (migration `20261125020300_robos_views_sem_escrita`).
