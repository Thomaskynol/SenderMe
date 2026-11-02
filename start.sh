#!/usr/bin/env bash
# SenderMe v2 — launcher (navegador).
#
# Pendrives vêm em FAT32/NTFS e montados com noexec: rode com `bash start.sh`.
# Copia o app para /tmp e executa de lá; os dados continuam no pendrive
# (SENDERME_HOME aponta para a pasta original). Terminal fica como servidor
# (Ctrl+C = sair e avisa a rede); o uso é no navegador.
#
# Contrato de saída: 42 = update aplicado (re-executa o start.sh DO DISCO e
# roda de novo, para o launcher novo — com lista nova — assumir); qualquer
# outro código do Python é propagado (falha nunca vira exit 0).
# A lista RUNTIME abaixo deve cobrir todo .py/.css de ARQUIVOS_UPDATE em
# senderme_app/meta.py (há teste comportamental que confere). Além dela, o
# launcher copia qualquer .py novo no disco (inclusive em subdiretório de
# senderme_app/, R1b) além do RUNTIME (R1: um
# RUNTIME antigo nunca impede um módulo novo de subir após o re-exec).
set -e

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HTTP_PORTA="${SENDERME_HTTP:-13336}"
RUNTIME="senderme.py config.py crypto.py pagina.py
    senderme_app/__init__.py senderme_app/meta.py senderme_app/estado.py
    senderme_app/persist.py senderme_app/presenca.py senderme_app/eventos.py
    senderme_app/arquivos.py senderme_app/transporte.py senderme_app/tcp.py
    senderme_app/udp.py senderme_app/manut.py senderme_app/update.py
    senderme_app/update_store.py senderme_app/update_proto.py senderme_app/comandos.py senderme_app/http.py senderme_app/app.py
    senderme_app/preboot.py senderme_app/diario.py"

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

RUN_DIR=""
limpar() {
    if [ -n "$RUN_DIR" ]; then
        rm -rf "$RUN_DIR"
        RUN_DIR=""
    fi
}
trap limpar EXIT HUP INT TERM

copiar_runtime() {
    local dest="$1"
    # shellcheck disable=SC2086
    for f in $RUNTIME; do
        if [ ! -f "$APP_DIR/$f" ]; then
            echo "SenderMe: faltando $f em $APP_DIR (instalação incompleta)" >&2
            return 1
        fi
        mkdir -p "$dest/$(dirname "$f")"
        cp "$APP_DIR/$f" "$dest/$f"
    done
    # R1: módulos novos que um RUNTIME antigo não lista sobem mesmo assim,
    # inclusive em subdiretório novo (ex. senderme_app/extra/*.py).
    if [ -d "$APP_DIR/senderme_app" ]; then
        while IFS= read -r f; do
            [ -n "$f" ] || continue
            if [ ! -f "$dest/$f" ]; then
                mkdir -p "$dest/$(dirname "$f")"
                cp "$APP_DIR/$f" "$dest/$f"
            fi
        done <<EOF
$(cd "$APP_DIR" && find senderme_app -name '*.py' -not -path '*/__pycache__/*')
EOF
    fi
    for f in "$APP_DIR"/*.py; do
        [ -e "$f" ] || continue
        rel="$(basename "$f")"
        if [ ! -f "$dest/$rel" ]; then
            cp "$f" "$dest/$rel"
        fi
    done
    if [ -f "$APP_DIR/bootstrap.min.css" ]; then
        cp "$APP_DIR/bootstrap.min.css" "$dest/bootstrap.min.css"
    fi
}

# Abre o navegador sozinho (após o servidor subir).
if command -v xdg-open >/dev/null 2>&1; then
    (sleep 2; xdg-open "http://127.0.0.1:${HTTP_PORTA}" >/dev/null 2>&1 &) || true
else
    echo "Abra no navegador: http://127.0.0.1:${HTTP_PORTA}"
fi

while true; do
    # R2: pre-boot ANTES de copiar/bootar e sem importar senderme_app:
    # desfaz update interrompido no disco; parcial sai !=0 e não boota.
    if [ -f "$APP_DIR/senderme_app/preboot.py" ]; then
        if ! python3 "$APP_DIR/senderme_app/preboot.py" "$APP_DIR"; then
            echo "SenderMe: recuperação de update pendente (veja o log); não vou iniciar mistura." >&2
            exit 1
        fi
    fi
    # shellcheck disable=SC2086
    RUN_DIR="$(mktemp -d /tmp/senderme-XXXXXX)"
    if ! copiar_runtime "$RUN_DIR"; then
        exit 1
    fi
    set +e
    python3 "$RUN_DIR/senderme.py"
    code=$?
    set -e
    limpar
    # 42 = update aplicado: o start.sh em disco já é o NOVO — re-executa
    # ele em vez de reusar este shell/lista velhos (R1).
    if [ "$code" -eq 42 ]; then
        sleep 1
        if [ -f "$APP_DIR/start.sh" ]; then
            exec bash "$APP_DIR/start.sh"
        fi
        continue
    fi
    exit "$code"
done
