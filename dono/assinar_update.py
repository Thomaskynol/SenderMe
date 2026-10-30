#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Assina uma release do SenderMe (uso do DONO apenas).

Lê dono/privada.json (NUNCA distribuída), calcula sha256 dos arquivos do
pacote e escreve update-manifest.json {manifest, sig} na raiz do projeto.
O manifest entra na dist/ e é servido via P2P; a privada nunca sai daqui.
"""
import hashlib
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

ARQUIVOS = ["senderme.py", "bootstrap.min.css", "start.sh", "README.md",
            "docs/01-produto.md", "docs/02-arquitetura.md", "docs/03-progresso.md"]


def versao_do_codigo():
    import re
    src = open(os.path.join(RAIZ, "senderme.py"), encoding="utf-8").read()
    m = re.search(r'^VERSAO\s*=\s*os\.environ\.get\("SENDERME_VERSAO",\s*"([^"]+)"\)',
                  src, re.M)
    if not m:
        raise SystemExit("VERSAO não encontrada em senderme.py")
    return m.group(1)


def main():
    priv_path = os.path.join(RAIZ, "dono", "privada.json")
    try:
        priv = json.load(open(priv_path, encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit("dono/privada.json não encontrada (só o dono assina).")
    import senderme as sm
    chave = {"n": int(priv["n"], 16), "e": int(priv["e"]), "d": int(priv["d"], 16)}
    manifest = {"v": versao_do_codigo(), "arquivos": []}
    for nome in ARQUIVOS:
        p = os.path.join(RAIZ, nome)
        if not os.path.isfile(p):
            raise SystemExit("faltando no pacote: %s" % nome)
        with open(p, "rb") as f:
            blob = f.read()
        manifest["arquivos"].append({"nome": nome, "tamanho": len(blob),
                                     "sha256": hashlib.sha256(blob).hexdigest()})
    campo = sm.manifest_canonico(manifest)
    sig = sm.assinar(campo, chave).hex()
    # confere com a pública embutida antes de gravar
    n_pub = int(sm.CHAVE_DONO_N, 16)
    assert sm.conferir(campo, bytes.fromhex(sig), n_pub, sm.CHAVE_DONO_E), \
        "assinatura não confere com CHAVE_DONO embutida!"
    with open(os.path.join(RAIZ, "update-manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"manifest": manifest, "sig": sig}, f, ensure_ascii=False)
    print("update-manifest.json v%s assinado (%d arquivos)." % (manifest["v"], len(ARQUIVOS)))


if __name__ == "__main__":
    main()
