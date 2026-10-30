#!/usr/bin/env bash
# SenderMe v2 — launcher (navegador).
#
# Pendrives vêm em FAT32/NTFS e montados com noexec: rode com `bash start.sh`.
# Copia o app para /tmp e executa de lá; os dados continuam no pendrive
# (SENDERME_HOME aponta para a pasta original). Terminal fica como servidor
# (Ctrl+C = sair e avisa a rede); o uso é no navegador.
set -e

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HTTP_PORTA="${SENDERME_HTTP:-13336}"

if ! command -v python3 >/dev/null 2>&1; then
    echo "SenderMe: python3 não encontrado neste PC." >&2
    echo "Instale com:  sudo apt install python3" >&2
    exit 1
fi

if [ ! -f "$APP_DIR/senderme.py" ]; then
    echo "SenderMe: não achei senderme.py em $APP_DIR" >&2
    exit 1
fi

export SENDERME_HOME="$APP_DIR"

# Abre o navegador sozinho (após o servidor subir).
if command -v xdg-open >/dev/null 2>&1; then
    (sleep 2; xdg-open "http://127.0.0.1:${HTTP_PORTA}" >/dev/null 2>&1 &) || true
else
    echo "Abra no navegador: http://127.0.0.1:${HTTP_PORTA}"
fi

while true; do
    RUN_DIR="$(mktemp -d /tmp/senderme-XXXXXX)"
    cp "$APP_DIR/senderme.py" "$RUN_DIR/senderme.py"
    if [ -f "$APP_DIR/bootstrap.min.css" ]; then
        cp "$APP_DIR/bootstrap.min.css" "$RUN_DIR/bootstrap.min.css"
    fi
    set +e
    python3 "$RUN_DIR/senderme.py"
    code=$?
    set -e
    rm -rf "$RUN_DIR"
    # 42 = update aplicado: recopia tudo (já atualizado no pendrive) e roda de novo
    if [ "$code" -eq 42 ]; then
        sleep 1
        continue
    fi
    break
done
