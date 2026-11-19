#!/usr/bin/env bash
# Fim dos creditos do teste do Google (acabam em 18/01/2027). Chamado passo a
# passo pelo workflow minecraft_fim_creditos.yml, que o pg_cron dispara
# (migration 20261118190000_minecraft_fim_creditos.sql):
#
#   14/01/2027 06:00 SP  backup:   copia o backup mais recente de cada servidor
#                                  para fora do Google e confere as permissoes
#   16/01/2027 06:00 SP  encerrar: desliga as VMs, copia o backup final e
#                                  desvincula o projeto do faturamento
#   16/01/2027 12:00 SP  repescagem do encerrar (se ja cortou, nao faz nada)
#
# Uso: fim_creditos.sh modo | permissoes | desligar | backup | faturamento
# Credencial: conta minecraft-encerrar (chave no secret MINECRAFT_GCP_KEY).
set -euo pipefail

PROJETO=serverminecasaonly
ZONA=southamerica-east1-b
BALDE=gs://serverminecasaonly-backups
VMS=(minecraft pixelmon)
# Nome dos arquivos de backup de cada servidor (PREFIXO_BACKUP do monitor_vm.py).
PREFIXOS=(world pixelmon_world)
DIA_ENCERRAR=2027-01-16
# Release do GitHub aceita arquivo de ate 2 GB: acima disso, vai em partes.
PARTE=1900M

saida() { [[ -n ${GITHUB_OUTPUT:-} ]] && echo "$1=$2" >> "$GITHUB_OUTPUT"; echo "$1=$2"; }

faturamento_ligado() {
  [[ $(gcloud billing projects describe "$PROJETO" --format='value(billingEnabled)') == True ]]
}

# Decide o que fazer. "auto" (o pg_cron nao passa entrada) vai pela data de SP.
cmd_modo() {
  local hoje modo=${MODO:-auto}
  hoje=$(TZ=America/Sao_Paulo date +%F)
  if [[ $modo == auto ]]; then
    if [[ $hoje < $DIA_ENCERRAR ]]; then modo=backup; else modo=encerrar; fi
  fi
  [[ $modo == backup || $modo == encerrar ]] || { echo "::error::modo invalido: $modo"; exit 1; }
  saida modo "$modo"
  saida hoje "$hoje"
  if faturamento_ligado; then
    saida ja_cortado false
  elif [[ $modo == encerrar ]]; then
    echo "::notice::Faturamento ja desvinculado do projeto: nada a fazer."
    saida ja_cortado true
  else
    echo "::error::O projeto esta sem faturamento: sem acesso aos backups do Cloud Storage."
    exit 1
  fi
}

# A conta de servico consegue fazer o que o dia 16 precisa? (Roda no dia 14
# para dar tempo de corrigir.) testIamPermissions devolve so as que ela tem.
cmd_permissoes() {
  # Storage nao aparece no teste do projeto: confere listando o balde.
  gcloud storage ls "$BALDE" > /dev/null
  local precisa=(compute.instances.get compute.instances.stop
                 resourcemanager.projects.get resourcemanager.projects.deleteBillingAssignment)
  # Precisa da API cloudresourcemanager ativada no projeto (ativada em 18/11/2026).
  local corpo tem faltam=()
  corpo=$(printf '"%s",' "${precisa[@]}")
  if ! tem=$(curl -sS --fail-with-body -X POST -H "Authorization: Bearer $(gcloud auth print-access-token)" \
        -H "Content-Type: application/json" -d "{\"permissions\":[${corpo%,}]}" \
        "https://cloudresourcemanager.googleapis.com/v1/projects/$PROJETO:testIamPermissions"); then
    echo "::error::testIamPermissions falhou: $tem"
    exit 1
  fi
  for p in "${precisa[@]}"; do grep -q "\"$p\"" <<<"$tem" || faltam+=("$p"); done
  if (( ${#faltam[@]} )); then
    echo "::error::A conta minecraft-encerrar nao tem: ${faltam[*]}"
    exit 1
  fi
  echo "Permissoes ok: ${precisa[*]}"
}

# Parar a VM pelo Google e o mesmo caminho do botao de desligar: o
# minecraft.service salva o mundo e manda o backup antes de a maquina cair.
cmd_desligar() {
  local vm status
  for vm in "${VMS[@]}"; do
    status=$(gcloud compute instances describe "$vm" --zone "$ZONA" --format='value(status)')
    if [[ $status == TERMINATED ]]; then
      echo "$vm: ja desligada"
    else
      echo "$vm: $status -> desligando (salva o mundo e faz backup)"
      gcloud compute instances stop "$vm" --zone "$ZONA" --quiet
    fi
  done
}

# Backup mais recente de cada servidor -> confere se abre -> criptografa
# (leva as senhas do Login System e o repositorio e publico) -> release do
# GitHub com a data de SP. Rodar de novo no mesmo dia substitui os arquivos.
cmd_backup() {
  : "${BACKUP_SENHA:?secret MINECRAFT_BACKUP_SENHA ausente}"
  local pasta tag prefixo ultimo arquivo lista=""
  pasta=$(mktemp -d)
  tag="backup-minecraft-$(TZ=America/Sao_Paulo date +%F)"
  for prefixo in "${PREFIXOS[@]}"; do
    ultimo=$(gcloud storage ls "$BALDE/${prefixo}_*.tar.gz" | sort | tail -1)
    [[ -n $ultimo ]] || { echo "::error::nenhum backup ${prefixo}_* em $BALDE"; exit 1; }
    arquivo="$pasta/$(basename "$ultimo")"
    gcloud storage cp "$ultimo" "$arquivo" --no-user-output-enabled
    tar -tzf "$arquivo" > /dev/null
    gpg --batch --yes --pinentry-mode loopback --symmetric --cipher-algo AES256 \
        --passphrase-file <(printf %s "$BACKUP_SENHA") -o "$arquivo.gpg" "$arquivo"
    rm "$arquivo"
    if (( $(stat -c %s "$arquivo.gpg") > 1900 * 1024 * 1024 )); then
      split -b "$PARTE" -d "$arquivo.gpg" "$arquivo.gpg.parte"
      rm "$arquivo.gpg"
    fi
    lista+="- $(basename "$ultimo") ($(du -h "$arquivo".gpg* | awk '{print $1}' | paste -sd+))"$'\n'
  done
  ls -la "$pasta"

  local notas="Backup dos mundos do Minecraft (Create e Pixelmon), copiado do Cloud Storage antes do fim dos creditos do Google.
Criptografado (AES-256). Para baixar e abrir no PC: apps/minecraft/gcp/baixar_backup_github.ps1

$lista"
  if gh release view "$tag" > /dev/null 2>&1; then
    gh release upload "$tag" "$pasta"/* --clobber
    gh release edit "$tag" --notes "$notas"
  else
    gh release create "$tag" "$pasta"/* --prerelease --latest=false \
      --title "Backup Minecraft $(TZ=America/Sao_Paulo date +%d/%m/%Y)" --notes "$notas"
  fi
  echo "Release: $tag"
}

# Sem conta de faturamento no projeto, o Google nao tem o que cobrar. Os
# discos e o balde ficam parados (sem uso) ate o Google apagar. Volta pelo
# console: Faturamento -> Gerenciar projetos -> Alterar faturamento.
cmd_faturamento() {
  if ! faturamento_ligado; then echo "Ja estava desvinculado."; return; fi
  gcloud billing projects unlink "$PROJETO" --quiet
  if faturamento_ligado; then echo "::error::O Google ainda mostra o faturamento ligado."; exit 1; fi
  echo "::notice::Faturamento desvinculado do projeto $PROJETO: nada mais pode ser cobrado."
}

case "${1:-}" in
  modo|permissoes|desligar|backup|faturamento) "cmd_$1" ;;
  *) echo "uso: $0 modo|permissoes|desligar|backup|faturamento" >&2; exit 2 ;;
esac
