#!/usr/bin/env bash
# SenderMe — gera dist/SenderMe (build limpa p/ copiar ao pendrive).
#
# Inclui: código + manifest de update + README + docs.
# NUNCA inclui: dados/ (identidade!), dono/ (chave!), __pycache__, dist/,
# .git/ (a build copia por allowlist: só os arquivos listados abaixo).
set -e
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST="$APP_DIR/dist/SenderMe"

if [ ! -f "$APP_DIR/update-manifest.json" ]; then
    echo "Falta update-manifest.json: rode  python3 dono/assinar_update.py" >&2
    exit 1
fi

rm -rf "$DIST"
mkdir -p "$DIST/docs"
cp "$APP_DIR/senderme.py" "$APP_DIR/bootstrap.min.css" "$APP_DIR/start.sh" \
   "$APP_DIR/README.md" "$APP_DIR/update-manifest.json" "$DIST/"
cp "$APP_DIR/docs/01-produto.md" "$APP_DIR/docs/02-arquitetura.md" \
   "$APP_DIR/docs/03-progresso.md" "$DIST/docs/"

echo "== dist/SenderMe =="
find "$DIST" -type f | sort
echo "== tamanho =="
du -sh "$DIST"
echo "OK: copie a pasta dist/SenderMe para o pendrive."
