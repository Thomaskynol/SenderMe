#!/usr/bin/env bash
# SenderMe — gera dist/SenderMe (build limpa p/ copiar ao pendrive).
#
# Inclui: código + manifest de update (só runtime).
# README/docs/roteiro ficam no repo, fora da dist e fora do conjunto
# assinado (instalação antiga mantém seus docs; o update nunca os apaga).
# NUNCA inclui: dados/ (identidade!), dono/ (chave!), __pycache__, dist/,
# .git/ (a build copia por allowlist: só os arquivos listados abaixo).
# A lista abaixo deve ser idêntica a ARQUIVOS_UPDATE em senderme_app/meta.py
# mais update-manifest.json (há teste que confere arquivo a arquivo).
#
# Gate de release (bloqueio item 1): sem --dev, a build VERIFICA e REJEITA
# (erro claro em stderr + exit != 0, sem anunciar release) quando:
# assinatura inválida, versão do código != manifesto, conjunto de arquivos
# != ARQUIVOS_UPDATE/manifesto/allowlist, arquivo ausente ou tamanho/hash
# divergente — conferindo os BYTES da dist final (não só a origem).
# Com --dev, o drift vira aviso e a saída sai marcada como DEV, nunca "OK".
set -e
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST="$APP_DIR/dist/SenderMe"

DEV=0
for arg in "$@"; do
    case "$arg" in
        --dev) DEV=1 ;;
        -h|--help)
            echo "Uso: bash build_dist.sh [--dev]"
            echo "  sem args: build de release (qualquer drift reprova, exit != 0)"
            echo "  --dev:    build de desenvolvimento (drift vira aviso; nunca é release)"
            exit 0
            ;;
        *)
            echo "ERRO release: opção desconhecida: $arg (use --dev)" >&2
            exit 2
            ;;
    esac
done

if [ ! -f "$APP_DIR/update-manifest.json" ]; then
    echo "Falta update-manifest.json: rode  python3 dono/assinar_update.py" >&2
    exit 1
fi

# Allowlist = ARQUIVOS_UPDATE + update-manifest.json (teste confere arquivo
# a arquivo). Variável (não só loop inline) para o gate comparar de verdade.
ALLOWLIST="senderme.py config.py crypto.py pagina.py bootstrap.min.css TERCEIROS.md start.sh update-manifest.json senderme_app/__init__.py senderme_app/meta.py senderme_app/estado.py senderme_app/persist.py senderme_app/presenca.py senderme_app/eventos.py senderme_app/arquivos.py senderme_app/transporte.py senderme_app/tcp.py senderme_app/udp.py senderme_app/manut.py senderme_app/update.py senderme_app/update_store.py senderme_app/update_proto.py senderme_app/comandos.py senderme_app/http.py senderme_app/app.py senderme_app/preboot.py senderme_app/diario.py"

# Ausente: nem release nem dev conseguem copiar o que não existe.
# shellcheck disable=SC2086
for f in $ALLOWLIST; do
    if [ ! -f "$APP_DIR/$f" ]; then
        if [ "$DEV" -eq 1 ]; then
            echo "AVISO DEV: arquivo ausente na origem: $f" >&2
        else
            echo "ERRO release: arquivo ausente na origem: $f" >&2
        fi
        exit 1
    fi
done

rm -rf "$DIST"
mkdir -p "$DIST/senderme_app"
# Loop com mkdir -p preserva subdiretório futuro (ex.
# senderme_app/extra/*.py); cp flat perderia o prefixo. Sem find livre:
# extra fora da lista não entra na dist.
# shellcheck disable=SC2086
for f in $ALLOWLIST; do
    mkdir -p "$DIST/$(dirname "$f")"
    cp "$APP_DIR/$f" "$DIST/$f"
done

# Gate: assinatura + versão + conjunto + tamanho/hash dos BYTES da dist
# final (stdlib apenas; dono/privada.json nunca lida aqui).
ALLOWLIST="$ALLOWLIST" DEV="$DEV" APP_DIR="$APP_DIR" DIST="$DIST" python3 - <<'PYEOF'
import hashlib
import importlib.util
import json
import os
import re
import sys

app = os.environ["APP_DIR"]
dist = os.environ["DIST"]
dev = os.environ.get("DEV") == "1"
allow = os.environ["ALLOWLIST"].split()

erros = []
avisos = []


def relatar(msg):
    (avisos if dev else erros).append(msg)


spec = importlib.util.spec_from_file_location(
    "meta_fonte", os.path.join(app, "senderme_app", "meta.py"))
meta = importlib.util.module_from_spec(spec)
spec.loader.exec_module(meta)
arqs_esperados = list(meta.ARQUIVOS_UPDATE)

src_meta = open(os.path.join(app, "senderme_app", "meta.py"),
                encoding="utf-8").read()
m = re.search(r'^VERSAO\s*=\s*os\.environ\.get\("SENDERME_VERSAO",\s*"([^"]+)"\)',
              src_meta, re.M)
ver_default = m.group(1) if m else None

try:
    with open(os.path.join(dist, "update-manifest.json"),
              encoding="utf-8") as f:
        env = json.load(f)
    manifest = env["manifest"]
    sig_hex = env["sig"]
except Exception as e:
    relatar("manifesto da dist ilegível: %r" % (e,))
    manifest, sig_hex = None, None

if manifest is not None:
    if ver_default is None:
        relatar("VERSAO não encontrada em senderme_app/meta.py")
    elif manifest.get("v") != ver_default:
        relatar("versão do código (%s) != manifesto (%s)"
                % (ver_default, manifest.get("v")))
    if manifest.get("v") != getattr(meta, "VERSAO", None):
        relatar("versão efetiva (%s) != manifesto (%s)"
                % (getattr(meta, "VERSAO", None), manifest.get("v")))
    nomes_man = ([a.get("nome") for a in manifest.get("arquivos", [])]
                 if isinstance(manifest.get("arquivos"), list) else None)
    if nomes_man != arqs_esperados:
        relatar("conjunto de arquivos do manifesto != ARQUIVOS_UPDATE "
                "(só no manifesto: %s; só em ARQUIVOS_UPDATE: %s)"
                % (sorted(set(nomes_man or []) - set(arqs_esperados)),
                   sorted(set(arqs_esperados) - set(nomes_man or []))))
    if sorted(allow) != sorted(arqs_esperados + ["update-manifest.json"]):
        relatar("allowlist do build_dist.sh != ARQUIVOS_UPDATE+manifesto "
                "(só na allowlist: %s; faltando: %s)"
                % (sorted(set(allow) - set(arqs_esperados + ["update-manifest.json"])),
                   sorted(set(arqs_esperados + ["update-manifest.json"]) - set(allow))))
    try:
        sys.path.insert(0, app)
        from crypto import conferir
        campo = json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
        ok = conferir(campo, bytes.fromhex(sig_hex),
                      int(meta.CHAVE_DONO_N, 16), meta.CHAVE_DONO_E)
        if not ok:
            relatar("assinatura do manifesto inválida")
    except Exception as e:
        relatar("assinatura do manifesto inválida (%r)" % (e,))
    if isinstance(manifest.get("arquivos"), list):
        for a in manifest["arquivos"]:
            try:
                nome = a["nome"]
                p = os.path.join(dist, nome)
                if not os.path.isfile(p):
                    relatar("arquivo ausente na dist: %s" % nome)
                    continue
                with open(p, "rb") as f:
                    blob = f.read()
                if len(blob) != a["tamanho"]:
                    relatar("tamanho diverge na dist: %s "
                            "(dist %d != manifesto %d)"
                            % (nome, len(blob), a["tamanho"]))
                if hashlib.sha256(blob).hexdigest() != a["sha256"]:
                    relatar("hash diverge na dist: %s" % nome)
            except Exception as e:
                relatar("não conferi %s (%r)" % (a, e))
    else:
        relatar("manifesto sem lista de arquivos")
    achados = []
    for base, _, arqs in os.walk(dist):
        for x in arqs:
            achados.append(os.path.relpath(os.path.join(base, x), dist))
    if sorted(achados) != sorted(allow):
        relatar("arquivos da dist != allowlist (extra/faltando: %s)"
                % (sorted(set(achados) ^ set(allow)),))

if dev:
    for w in avisos:
        print("AVISO DEV: %s" % w)
else:
    if erros:
        for e in erros:
            print("ERRO release: %s" % e, file=sys.stderr)
        sys.exit(1)
PYEOF

if [ "$DEV" -eq 1 ]; then
    echo "== dist/SenderMe (DEV) =="
    find "$DIST" -type f | sort
    echo "== tamanho =="
    du -sh "$DIST"
    echo "DEV: distribuição de desenvolvimento em dist/SenderMe (NÃO é release válida; não distribua como update)."
else
    echo "== dist/SenderMe =="
    find "$DIST" -type f | sort
    echo "== tamanho =="
    du -sh "$DIST"
    echo "OK: copie a pasta dist/SenderMe para o pendrive."
fi
