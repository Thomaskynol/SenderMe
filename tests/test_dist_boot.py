"""Launcher/build com execução real (não só assertIn): cópia do runtime,
propagação de exit, loop 42, conteúdo da dist sem segredos.

Lento (~segundos): usa subprocessos delimitados com killpg de limpeza.
"""
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "tests"))


def runtime_esperado():
    import senderme_app.meta as meta
    que = sorted(f for f in meta.ARQUIVOS_UPDATE
                 if f.endswith(".py") or f.endswith(".css"))
    if os.path.isfile(os.path.join(RAIZ, "bootstrap.min.css")):
        que = sorted(set(que) | {"bootstrap.min.css"})
    return que


def nova_instalacao(stub_senderme=None):
    """Copia os runtime files reais para tmp; opcionalmente troca senderme.py
    por um stub de sonda. Retorna o dir da instalação."""
    inst = tempfile.mkdtemp(prefix="sm-inst-")
    for f in runtime_esperado():
        src = os.path.join(RAIZ, f)
        dst = os.path.join(inst, f)
        os.makedirs(os.path.dirname(dst) or inst, exist_ok=True)
        shutil.copy2(src, dst)
    shutil.copy2(os.path.join(RAIZ, "start.sh"), os.path.join(inst, "start.sh"))
    if stub_senderme is not None:
        with open(os.path.join(inst, "senderme.py"), "w",
                  encoding="utf-8") as fh:
            fh.write(stub_senderme)
    return inst


class LauncherCopiaEExit(unittest.TestCase):
    def test_copia_runtime_completo_e_propaga_falha(self):
        # stub: despeja o que o launcher copiou e sai 3
        stub = ("import os, sys\n"
                "home = os.environ['SENDERME_HOME']\n"
                "eu = os.path.dirname(os.path.abspath(__file__))\n"
                "achados = []\n"
                "for base, _, arqs in os.walk(eu):\n"
                "    for a in arqs:\n"
                "        achados.append(os.path.relpath(os.path.join(base, a), eu))\n"
                "open(os.path.join(home, 'probe.out'), 'w').write('\\n'.join(sorted(achados)))\n"
                "sys.exit(3)\n")
        inst = nova_instalacao(stub)
        self.addCleanup(shutil.rmtree, inst, True)
        r = subprocess.run(["bash", "start.sh"], cwd=inst, capture_output=True,
                           text=True, timeout=60)
        self.assertEqual(r.returncode, 3)  # falha propagada, não virou 0
        with open(os.path.join(inst, "probe.out"), encoding="utf-8") as f:
            copiados = f.read().split()
        self.assertEqual(sorted(copiados), runtime_esperado())

    def test_subdir_novo_no_disco_sobe_para_tmp(self):
        # R1b: modulo em subdiretorio novo (fora do RUNTIME) eh copiado.
        stub = ("import os, sys\n"
                "eu = os.path.dirname(os.path.abspath(__file__))\n"
                "achados = []\n"
                "for base, _, arqs in os.walk(eu):\n"
                "    for a in arqs:\n"
                "        achados.append(os.path.relpath(os.path.join(base, a), eu))\n"
                "open(os.path.join(os.environ['SENDERME_HOME'], 'probe.out'), 'w').write('\\n'.join(sorted(achados)))\n"
                "sys.exit(3)\n")
        inst = nova_instalacao(stub)
        self.addCleanup(shutil.rmtree, inst, True)
        os.makedirs(os.path.join(inst, "senderme_app", "extra"))
        for nome in ("__init__.py", "modulo.py"):
            with open(os.path.join(inst, "senderme_app", "extra", nome), "w",
                      encoding="utf-8") as f:
                f.write("# sonda\n")
        r = subprocess.run(["bash", "start.sh"], cwd=inst, capture_output=True,
                           text=True, timeout=60)
        self.assertEqual(r.returncode, 3)
        with open(os.path.join(inst, "probe.out"), encoding="utf-8") as f:
            copiados = f.read().split()
        self.assertIn("senderme_app/extra/__init__.py", copiados)
        self.assertIn("senderme_app/extra/modulo.py", copiados)

    def test_42_reexecuta_e_0_termina(self):
        stub = ("import os, sys\n"
                "home = os.environ['SENDERME_HOME']\n"
                "cont = os.path.join(home, 'cont.txt')\n"
                "n = int(open(cont).read()) if os.path.isfile(cont) else 0\n"
                "open(cont, 'w').write(str(n + 1))\n"
                "sys.exit(42 if n < 2 else 0)\n")
        inst = nova_instalacao(stub)
        self.addCleanup(shutil.rmtree, inst, True)
        r = subprocess.run(["bash", "start.sh"], cwd=inst, capture_output=True,
                           text=True, timeout=90)
        self.assertEqual(r.returncode, 0)
        with open(os.path.join(inst, "cont.txt"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "3")


def porta_livre():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def identidade_rapida(dados):
    sys.path.insert(0, os.path.join(RAIZ, "tests"))
    import suporte
    chave = suporte.chave_teste()
    idt = suporte.identidade_de(chave)
    os.makedirs(dados, exist_ok=True)
    with open(os.path.join(dados, "identidade.json"), "w",
              encoding="utf-8") as f:
        json.dump({"n": format(chave["n"], "x"), "e": chave["e"],
                   "d": format(chave["d"], "x"), "id": idt["id"]}, f)
    os.chmod(os.path.join(dados, "identidade.json"), 0o600)
    with open(os.path.join(dados, "apelido.txt"), "w",
              encoding="utf-8") as f:
        f.write("bot-teste")


def _reassinar_copia_coerente(src):
    """Versão+chave SINTÉTICAS e manifesto re-assinado na cópia (tmp).

    Nunca toca na árvore real nem em dono/privada.json: só torna a cópia
    coerente para exercitar o gate de release. Ver test_build_manifesto.py
    (mesmo padrão de fixture) e test_update_e2e_abc.py.
    """
    import hashlib
    import re
    sys.path.insert(0, os.path.join(RAIZ, "tests"))
    import suporte
    from crypto import assinar as crypto_assinar
    import senderme_app.update as upd
    chave = suporte.chave_teste()
    p = os.path.join(src, "senderme_app", "meta.py")
    with open(p, encoding="utf-8") as f:
        txt = f.read()
    txt, n = re.subn(r'os\.environ\.get\("SENDERME_VERSAO",\s*"[^"]+"\)',
                     'os.environ.get("SENDERME_VERSAO", "9.7")', txt, count=1)
    assert n == 1
    txt, n2 = re.subn(r'CHAVE_DONO_N\s*=\s*\(.*?\)',
                      'CHAVE_DONO_N = "%s"' % format(chave["n"], "x"),
                      txt, count=1, flags=re.S)
    assert n2 == 1
    with open(p, "w", encoding="utf-8") as f:
        f.write(txt)
    import importlib.util
    spec = importlib.util.spec_from_file_location("meta_copia_boot", p)
    mc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mc)
    manifest = {"v": "9.7", "arquivos": []}
    for nome in mc.ARQUIVOS_UPDATE:
        with open(os.path.join(src, nome), "rb") as f:
            blob = f.read()
        manifest["arquivos"].append({"nome": nome, "tamanho": len(blob),
                                     "sha256": hashlib.sha256(blob).hexdigest()})
    sig = crypto_assinar(upd.manifest_canonico(manifest), chave).hex()
    with open(os.path.join(src, "update-manifest.json"), "w",
              encoding="utf-8") as f:
        json.dump({"manifest": manifest, "sig": sig}, f, ensure_ascii=False)


class BootReal(unittest.TestCase):
    def test_boot_via_start_sh_responde_http(self):
        inst = nova_instalacao()
        self.addCleanup(shutil.rmtree, inst, True)
        identidade_rapida(os.path.join(inst, "dados"))
        tcp, udp, http = porta_livre(), porta_livre(), porta_livre()
        env = dict(os.environ, SENDERME_PORTA=str(tcp),
                   SENDERME_UDP_PORTA=str(udp), SENDERME_HTTP=str(http),
                   SENDERME_NO_BROADCAST="1")
        proc = subprocess.Popen(
            ["bash", "start.sh"], cwd=inst, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
        try:
            base = "http://127.0.0.1:%d" % http
            ok = None
            for _ in range(120):
                try:
                    with urllib.request.urlopen(base + "/api/eu",
                                                timeout=3) as r:
                        ok = json.loads(r.read().decode())
                        break
                except Exception:
                    if proc.poll() is not None:
                        self.fail("start.sh morreu com %s" % proc.returncode)
                    time.sleep(0.25)
            self.assertIsNotNone(ok, "HTTP não subiu")
            self.assertTrue(ok["logado"])
            self.assertEqual(ok["nick"], "bot-teste")
            import senderme_app.meta as meta
            self.assertEqual(ok["versao"], meta.VERSAO)
        finally:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                proc.wait(timeout=10)


class BuildDist(unittest.TestCase):
    def test_build_tem_allowlist_sem_segredos_e_hashes_batem(self):
        work = tempfile.mkdtemp(prefix="sm-build-")
        self.addCleanup(shutil.rmtree, work, True)
        for base, dirs, arqs in os.walk(RAIZ):
            dirs[:] = [d for d in dirs
                       if d not in ("dados", "dist", "__pycache__", ".git",
                                    ".planning")]
            if "dono" in base.split(os.sep):
                continue
            for a in arqs:
                if a in ("privada.json",):
                    continue
                src = os.path.join(base, a)
                rel = os.path.relpath(src, RAIZ)
                if ".pyc" in rel or "/.git/" in rel:
                    continue
                dst = os.path.join(work, "src", rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
        src = os.path.join(work, "src")
        # A árvore real pode estar com drift pós-assinatura (release real
        # pendente de nova versão+assinatura oficial): a cópia recebe
        # versão+chave SINTÉTICAS e manifesto re-assinado, para que este
        # teste exercite o gate sobre fixture coerente sem tocar na release
        # real nem na chave do dono. O drift real continua coberto por
        # test_update_dist (que lê a árvore de verdade).
        _reassinar_copia_coerente(src)
        r = subprocess.run(["bash", "build_dist.sh"], cwd=src,
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        dist = os.path.join(src, "dist", "SenderMe")
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "meta_copia", os.path.join(src, "senderme_app", "meta.py"))
        meta_src = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(meta_src)
        esperados = sorted(meta_src.ARQUIVOS_UPDATE + ["update-manifest.json"])
        achados = []
        for base, _, arqs in os.walk(dist):
            for a in arqs:
                achados.append(os.path.relpath(os.path.join(base, a), dist))
        self.assertEqual(sorted(achados), esperados)
        texto = "\n".join(achados)
        for proibido in ("dados", "dono", "privada", "__pycache__", ".git"):
            self.assertNotIn(proibido, texto)
        d = json.load(open(os.path.join(dist, "update-manifest.json"),
                           encoding="utf-8"))
        import hashlib
        for a in d["manifest"]["arquivos"]:
            blob = open(os.path.join(dist, a["nome"]), "rb").read()
            self.assertEqual(hashlib.sha256(blob).hexdigest(), a["sha256"],
                             a["nome"])


class DistSemDocs(unittest.TestCase):
    """Dist p/ pendrive sem docs: ARQUIVOS_UPDATE/allowlist/RUNTIME só runtime.

    README + docs/01-03 ficam no repo (não assinados, fora da dist);
    ROTEIRO-ESCOLA.md segue na raiz, fora da dist. Exceção única: o
    aviso de terceiros TERCEIROS.md (MIT integral do Bootstrap, cujos
    campos conferem byte a byte com o header de bootstrap.min.css)
    viaja na dist e no update assinado, sem pasta docs/ nem roteiro.
    """

    FORA = ("README.md", "docs/01-produto.md", "docs/02-arquitetura.md",
            "docs/03-progresso.md", "ROTEIRO-ESCOLA.md")

    AVISO = "TERCEIROS.md"

    def test_arquivos_update_so_runtime_mais_aviso(self):
        import senderme_app.meta as meta
        for f in self.FORA:
            self.assertNotIn(f, meta.ARQUIVOS_UPDATE, f)
        for f in meta.ARQUIVOS_UPDATE:
            self.assertTrue(f.endswith((".py", ".css")) or f == "start.sh"
                            or f == self.AVISO, f)
        self.assertIn(self.AVISO, meta.ARQUIVOS_UPDATE)

    def test_allowlist_igual_arquivos_update_mais_manifesto(self):
        import re
        import senderme_app.meta as meta
        with open(os.path.join(RAIZ, "build_dist.sh"),
                  encoding="utf-8") as f:
            src = f.read()
        m = re.search(r'^ALLOWLIST="(.*?)"', src, re.M | re.S)
        self.assertIsNotNone(m)
        allow = m.group(1).split()
        self.assertEqual(sorted(allow),
                         sorted(list(meta.ARQUIVOS_UPDATE)
                                + ["update-manifest.json"]))
        for f in self.FORA:
            self.assertNotIn(f, allow, f)

    def test_runtime_cobre_todo_py_css_do_conjunto(self):
        import re
        import senderme_app.meta as meta
        with open(os.path.join(RAIZ, "start.sh"), encoding="utf-8") as f:
            src = f.read()
        m = re.search(r'^RUNTIME="(.*?)"', src, re.M | re.S)
        self.assertIsNotNone(m)
        runtime = set(m.group(1).split())
        for f in meta.ARQUIVOS_UPDATE:
            if f.endswith(".py"):
                self.assertIn(f, runtime, f)
        # css chega ao /tmp (RUNTIME ou cp dedicado do launcher)
        self.assertIn("bootstrap.min.css", src)
        self.assertNotIn("docs/", m.group(1))
        self.assertNotIn("README", m.group(1))

    def test_bootstrap_carrega_aviso_mit(self):
        with open(os.path.join(RAIZ, "bootstrap.min.css"),
                  encoding="utf-8") as f:
            head = f.read(2000)
        self.assertIn("Licensed under MIT", head)


class TerceirosMit(unittest.TestCase):
    """TERCEIROS.md: MIT integral do Bootstrap na raiz, dist e update.

    Campos de atribuição conferem byte a byte com o header de
    bootstrap.min.css; nada sobre licença do SenderMe no arquivo.
    """

    AVISO = "TERCEIROS.md"
    CAMPOS_DO_HEADER = ("Bootstrap  v5.3.3",
                        "Copyright 2011-2024 The Bootstrap Authors",
                        "Licensed under MIT")

    def test_campos_batem_byte_a_byte_com_header_do_css(self):
        with open(os.path.join(RAIZ, "bootstrap.min.css"), "rb") as f:
            head = f.read(2000)
        with open(os.path.join(RAIZ, self.AVISO), "rb") as f:
            aviso = f.read()
        for campo in self.CAMPOS_DO_HEADER:
            b = campo.encode("utf-8")
            self.assertIn(b, head, "header do css perdeu: %r" % campo)
            self.assertIn(b, aviso, "aviso sem campo do header: %r" % campo)

    def test_texto_mit_integral(self):
        with open(os.path.join(RAIZ, self.AVISO), encoding="utf-8") as f:
            txt = f.read()
        for trecho in ("Permission is hereby granted, free of charge",
                       "The above copyright notice and this permission notice",
                       'THE SOFTWARE IS PROVIDED "AS IS"',
                       "WITHOUT WARRANTY OF ANY KIND"):
            self.assertIn(trecho, txt, "MIT incompleta, falta: %r" % trecho)

    def test_so_terceiros_sem_licenca_senderme(self):
        with open(os.path.join(RAIZ, self.AVISO), encoding="utf-8") as f:
            txt = f.read()
        self.assertNotIn("SenderMe", txt)


if __name__ == "__main__":
    unittest.main()
