"""Build de distribuição: gate de release (item 1).

Release (`bash build_dist.sh`) REJEITA com exit != 0 quando há drift entre
código em disco, ARQUIVOS_UPDATE e update-manifest.json (assinatura,
versão, conjunto, tamanho/hash), conferindo os BYTES da dist final.
`bash build_dist.sh --dev` permite drift mas nunca anuncia release válida.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "tests"))
sys.path.insert(0, RAIZ)

import suporte  # noqa: E402
from crypto import assinar as crypto_assinar  # noqa: E402


def copiar_arvore():
    work = tempfile.mkdtemp(prefix="sm-buildgate-")
    src = os.path.join(work, "src")
    os.makedirs(src)
    for base, dirs, arqs in os.walk(RAIZ):
        dirs[:] = [d for d in dirs
                   if d not in ("dados", "dist", "__pycache__", ".git",
                                ".planning", "arquivos_e_entregas")]
        if "dono" in base.split(os.sep):
            continue
        for a in arqs:
            if a in ("privada.json",):
                continue
            full = os.path.join(base, a)
            rel = os.path.relpath(full, RAIZ)
            if ".pyc" in rel or "/.git/" in rel:
                continue
            # só o necessário p/ o build + meta (evita RELATORIO etc.)
            dst = os.path.join(src, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(full, dst)
    return work, src


def reescrever_meta(src, versao, n_hex):
    p = os.path.join(src, "senderme_app", "meta.py")
    with open(p, encoding="utf-8") as f:
        txt = f.read()
    txt, n = re.subn(r'os\.environ\.get\("SENDERME_VERSAO",\s*"[^"]+"\)',
                     'os.environ.get("SENDERME_VERSAO", "%s")' % versao,
                     txt, count=1)
    assert n == 1
    txt, n2 = re.subn(r'CHAVE_DONO_N\s*=\s*\(.*?\)',
                      'CHAVE_DONO_N = "%s"' % n_hex, txt, count=1, flags=re.S)
    assert n2 == 1
    with open(p, "w", encoding="utf-8") as f:
        f.write(txt)


def assinar_src(src, versao, chave):
    import senderme_app.update as upd
    import senderme_app.meta as meta_atual
    nomes = list(meta_atual.ARQUIVOS_UPDATE)
    # lê ARQUIVOS_UPDATE da cópia (pode ter sido adulterada de propósito)
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "meta_copia_%s" % versao.replace(".", "_") + str(os.getpid()),
        os.path.join(src, "senderme_app", "meta.py"))
    mc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mc)
    nomes = list(mc.ARQUIVOS_UPDATE)
    manifest = {"v": versao, "arquivos": []}
    for nome in nomes:
        with open(os.path.join(src, nome), "rb") as f:
            blob = f.read()
        manifest["arquivos"].append({"nome": nome, "tamanho": len(blob),
                                     "sha256": hashlib.sha256(blob).hexdigest()})
    sig = crypto_assinar(upd.manifest_canonico(manifest), chave).hex()
    with open(os.path.join(src, "update-manifest.json"), "w",
              encoding="utf-8") as f:
        json.dump({"manifest": manifest, "sig": sig}, f, ensure_ascii=False)
    return {"manifest": manifest, "sig": sig}


def montar_src_coerente():
    work, src = copiar_arvore()
    chave = suporte.chave_teste()
    n_hex = format(chave["n"], "x")
    reescrever_meta(src, "9.7", n_hex)
    assinar_src(src, "9.7", chave)
    return work, src


def rodar_build(src, *args):
    return subprocess.run(["bash", "build_dist.sh"] + list(args), cwd=src,
                          capture_output=True, text=True, timeout=60)


class BuildGateRelease(unittest.TestCase):
    def test_release_rejeita_hash_divergente(self):
        work, src = montar_src_coerente()
        self.addCleanup(shutil.rmtree, work, True)
        with open(os.path.join(src, "start.sh"), "a",
                  encoding="utf-8") as f:
            f.write("# drift sonda\n")
        r = rodar_build(src)
        self.assertNotEqual(r.returncode, 0,
                            "build release saiu 0 com hash divergente")
        self.assertNotIn("OK: copie", r.stdout + r.stderr)

    def test_release_rejeita_assinatura_invalida(self):
        work, src = montar_src_coerente()
        self.addCleanup(shutil.rmtree, work, True)
        p = os.path.join(src, "update-manifest.json")
        d = json.load(open(p, encoding="utf-8"))
        d["sig"] = ("0" if d["sig"][:1] != "0" else "1") + d["sig"][1:]
        json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False)
        r = rodar_build(src)
        self.assertNotEqual(r.returncode, 0,
                            "build release saiu 0 com assinatura inválida")
        self.assertNotIn("OK: copie", r.stdout + r.stderr)

    def test_release_rejeita_versao_divergente(self):
        work, src = montar_src_coerente()
        self.addCleanup(shutil.rmtree, work, True)
        p = os.path.join(src, "senderme_app", "meta.py")
        txt = open(p, encoding="utf-8").read()
        txt = txt.replace('"9.7"', '"9.8"', 1)
        open(p, "w", encoding="utf-8").write(txt)
        r = rodar_build(src)
        self.assertNotEqual(r.returncode, 0,
                            "build release saiu 0 com versão divergente")
        self.assertNotIn("OK: copie", r.stdout + r.stderr)

    def test_release_rejeita_conjunto_divergente(self):
        work, src = montar_src_coerente()
        self.addCleanup(shutil.rmtree, work, True)
        p = os.path.join(src, "senderme_app", "meta.py")
        txt = open(p, encoding="utf-8").read()
        self.assertIn('"senderme_app/preboot.py"', txt)
        txt = txt.replace('"senderme_app/preboot.py"',
                          '"senderme_app/preboot.py", "senderme_app/novo.py"')
        open(p, "w", encoding="utf-8").write(txt)
        r = rodar_build(src)
        self.assertNotEqual(r.returncode, 0,
                            "build release saiu 0 com conjunto divergente")
        self.assertNotIn("OK: copie", r.stdout + r.stderr)

    def test_release_rejeita_arquivo_ausente(self):
        work, src = montar_src_coerente()
        self.addCleanup(shutil.rmtree, work, True)
        os.remove(os.path.join(src, "config.py"))
        r = rodar_build(src)
        self.assertNotEqual(r.returncode, 0,
                            "build release saiu 0 com arquivo ausente")
        self.assertNotIn("OK: copie", r.stdout + r.stderr)

    def test_release_coerente_passsa_e_anuncia(self):
        work, src = montar_src_coerente()
        self.addCleanup(shutil.rmtree, work, True)
        r = rodar_build(src)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:] + r.stdout[-2000:])
        self.assertIn("OK: copie", r.stdout)
        # BYTES da dist final conferem com o manifesto
        d = json.load(open(os.path.join(src, "dist", "SenderMe",
                                        "update-manifest.json"),
                           encoding="utf-8"))
        for a in d["manifest"]["arquivos"]:
            blob = open(os.path.join(src, "dist", "SenderMe", a["nome"]),
                        "rb").read()
            self.assertEqual(len(blob), a["tamanho"], a["nome"])
            self.assertEqual(hashlib.sha256(blob).hexdigest(), a["sha256"],
                             a["nome"])

    def test_dev_permite_drift_mas_nao_anuncia_release(self):
        work, src = montar_src_coerente()
        self.addCleanup(shutil.rmtree, work, True)
        with open(os.path.join(src, "start.sh"), "a",
                  encoding="utf-8") as f:
            f.write("# drift sonda\n")
        r = rodar_build(src, "--dev")
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        combinado = r.stdout + r.stderr
        self.assertNotIn("OK: copie", combinado)
        self.assertIn("DEV", combinado)


if __name__ == "__main__":
    unittest.main()
