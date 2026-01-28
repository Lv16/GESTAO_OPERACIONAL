#!/usr/bin/env bash
set -euo pipefail

# Deploy helper para GESTAO_OPERACIONAL
# Uso: ./deploy.sh [--dry-run] [--no-static] [--no-migrate] [--skip-pip]

PROJ_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$PROJ_DIR/deploy.log"
VENV_DEFAULT="$PROJ_DIR/venv_new"
HOST_HEADER="synchro.ambipar.vps-kinghost.net"

DRY_RUN=false
COLLECTSTATIC=true
MIGRATE=true
PIP_INSTALL=true
VENV="$VENV_DEFAULT"

usage(){
  cat <<EOF
Usage: $0 [--dry-run] [--no-static] [--no-migrate] [--skip-pip] [--venv PATH]
  --dry-run     : mostrar ações sem executá-las
  --no-static   : pular collectstatic
  --no-migrate  : pular migrate
  --skip-pip    : pular pip install
  --venv PATH   : ambiente virtual a usar (default: $VENV_DEFAULT)
EOF
}

log(){
  echo "$(date -u +"%Y-%m-%d %H:%M:%S UTC") - $*" | tee -a "$LOG"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=true; shift;;
    --no-static) COLLECTSTATIC=false; shift;;
    --no-migrate) MIGRATE=false; shift;;
    --skip-pip) PIP_INSTALL=false; shift;;
    --venv) VENV="$2"; shift 2;;
    --help) usage; exit 0;;
    *) echo "Unknown arg: $1"; usage; exit 2;;
  esac
done

run(){
  if [ "$DRY_RUN" = true ]; then
    # Mostra o comando exatamente como seria executado (com escaping)
    printf '+ '
    printf '%q ' "$@"
    printf '\n'
  else
    log "+ $*"
    "$@" 2>&1 | tee -a "$LOG"
  fi
}

cd "$PROJ_DIR"

log "Iniciando deploy (dry-run=$DRY_RUN)"

# Garantir branch main
BRANCH=$(git rev-parse --abbrev-ref HEAD || true)
if [ "$BRANCH" != "main" ]; then
  log "WARNING: branch atual é '$BRANCH' (esperado: main)"
fi

run git fetch origin --quiet
run git pull origin main

# Ativar virtualenv se existir
if [ -d "$VENV" ] && [ -f "$VENV/bin/activate" ]; then
  if [ "$DRY_RUN" = true ]; then
    echo "+ source $VENV/bin/activate"
  else
    # shellcheck disable=SC1090
    source "$VENV/bin/activate"
    log "Virtualenv ativado: $VENV"
  fi
else
  log "Aviso: virtualenv não encontrada em $VENV — prosseguindo sem ativar"
fi

if [ "$PIP_INSTALL" = true ] && [ -f requirements.txt ]; then
  run pip install -r requirements.txt
fi

if [ "$MIGRATE" = true ]; then
  run python manage.py migrate --noinput
fi

if [ "$COLLECTSTATIC" = true ]; then
  run python manage.py collectstatic --noinput
fi

# Reiniciar serviço e verificar status
run sudo systemctl restart gunicorn
run sudo systemctl status --no-pager -l gunicorn | sed -n '1,140p'

# Health checks simples com retries
if [ "$DRY_RUN" = true ]; then
  printf '+ echo -n "/ -> "\n'
  printf '+ curl -sS -o /dev/null -w "%%{http_code}\\n" -H "Host: %s" %s\n' "$HOST_HEADER" "http://127.0.0.1/"
  printf '+ echo -n "/rdo/ -> "\n'
  printf '+ curl -sS -o /dev/null -w "%%{http_code}\\n" -H "Host: %s" %s\n' "$HOST_HEADER" "http://127.0.0.1/rdo/"
else
  check_url() { curl -sS -o /dev/null -w "%{http_code}" -H "Host: $HOST_HEADER" "$1" || echo "000"; }

  wait_for_url() {
    local url="$1"
    local name="$2"
    local tries=0
    local max_tries=10
    local code
    printf "%s -> " "$name"
    while [ "$tries" -lt "$max_tries" ]; do
      code=$(check_url "$url")
      if [ "$code" = "200" ] || [ "$code" = "301" ]; then
        echo "$code"
        return 0
      fi
      echo -n "$code "
      tries=$((tries+1))
      sleep 1
    done
    echo
    return 1
  }

  if ! wait_for_url "http://127.0.0.1/" "/"; then
    log "ERROR: healthcheck falhou para /"
    sudo journalctl -u gunicorn -n 200 --no-pager | sed -n '1,200p' >> "$LOG" || true
    exit 1
  fi

  if ! wait_for_url "http://127.0.0.1/rdo/" "/rdo/"; then
    log "ERROR: healthcheck falhou para /rdo/"
    sudo journalctl -u gunicorn -n 200 --no-pager | sed -n '1,200p' >> "$LOG" || true
    exit 1
  fi
fi

log "Deploy finalizado"

if [ "$DRY_RUN" = true ]; then
  echo "Nota: modo dry-run — nenhuma alteração foi executada."
fi

exit 0
