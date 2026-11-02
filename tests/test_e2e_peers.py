"""2 peers reais em loopback: login, mensagem pública, DM e arquivo global.

Processos `python3 senderme.py` isolados (SENDERME_HOME + 3 portas próprias
cada, identidades sintéticas rápidas). Delimitado: timeouts + killpg.
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "tests"))
from test_dist_boot import identidade_rapida, porta_livre


class Peer:
    def __init__(self, nick, fixos=""):
        self.home = tempfile.mkdtemp(prefix="sm-peer-")
        self.tcp, self.udp, self.http = (porta_livre(), porta_livre(),
                                         porta_livre())
        identidade_rapida(os.path.join(self.home, "dados"))
        with open(os.path.join(self.home, "dados", "apelido.txt"), "w",
                  encoding="utf-8") as f:
            f.write(nick)
        env = dict(os.environ, SENDERME_HOME=self.home,
                   SENDERME_PORTA=str(self.tcp),
                   SENDERME_UDP_PORTA=str(self.udp),
                   SENDERME_HTTP=str(self.http),
                   SENDERME_FIXOS=fixos,
                   # supressão de broadcast em teste (ver udp.thread_udp:
                   # sem o patch, inócuo; com o patch, nada sai p/ a LAN).
                   SENDERME_NO_BROADCAST="1")
        self.proc = subprocess.Popen(
            [sys.executable, os.path.join(RAIZ, "senderme.py")],
            cwd=RAIZ, env=env, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True)
        self.base = "http://127.0.0.1:%d" % self.http

    def fechar(self):
        try:
            os.killpg(self.proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            self.proc.wait(timeout=10)
        shutil.rmtree(self.home, ignore_errors=True)

    def api(self, rota, obj=None, timeout=10):
        data = json.dumps(obj).encode() if obj is not None else None
        req = urllib.request.Request(
            self.base + rota, data=data,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())

    def esperar_logado(self, nick, limite=60):
        fim = time.time() + limite
        while time.time() < fim:
            if self.proc.poll() is not None:
                raise AssertionError("peer %s morreu" % nick)
            try:
                eu = self.api("/api/eu")
                if eu["logado"] and eu["nick"] == nick:
                    return eu
            except Exception:
                pass
            time.sleep(0.5)
        raise AssertionError("peer %s sem login" % nick)

    def esperar_texto(self, trecho, limite=60, dm=None):
        last, fim = "", time.time() + limite
        while time.time() < fim:
            try:
                d = self.api("/api/mensagens?depois=" +
                             urllib.request.quote(last))
                for m in d["eventos"]:
                    last = m["mid"]
                    if trecho in (m.get("txt") or "") and \
                            (dm is None or m["dm"] == dm):
                        return m
            except Exception:
                pass
            time.sleep(0.5)
        raise AssertionError("texto %r não chegou" % trecho)


class DoisPeers(unittest.TestCase):
    def test_login_mensagem_dm_e_arquivo(self):
        b = Peer("peer-b")
        self.addCleanup(b.fechar)
        a = Peer("peer-a", fixos="127.0.0.1:%d" % b.tcp)
        self.addCleanup(a.fechar)
        a.esperar_logado("peer-a")
        b.esperar_logado("peer-b")
        # B fala primeiro para A aprender o nick via P2P
        b.api("/api/enviar", {"texto": "oi-de-b"})
        a.esperar_texto("oi-de-b")
        # pública A -> B
        a.api("/api/enviar", {"texto": "ola-de-a"})
        b.esperar_texto("ola-de-a", dm=False)
        # DM A -> B (só B vê como dm)
        a.api("/api/enviar", {"texto": "segredo-a-b", "para": "@peer-b"})
        mb = b.esperar_texto("segredo-a-b", dm=True)
        self.assertTrue(mb["dm"])
        # arquivo global A -> B (conteúdo puxado via chunks P2P)
        blob = b"conteudo-arquivo-e2e" * 500
        bnd = "E2E"
        corpo = (b"--E2E\r\nContent-Disposition: form-data; name=\"texto\"\r\n\r\n"
                 b"segue anexo\r\n--E2E\r\nContent-Disposition: form-data; "
                 b"name=\"file\"; filename=\"doc.bin\"\r\n\r\n" + blob +
                 b"\r\n--E2E--\r\n")
        req = urllib.request.Request(
            a.base + "/api/upload", data=corpo,
            headers={"Content-Type": "multipart/form-data; boundary=E2E"})
        with urllib.request.urlopen(req, timeout=30) as r:
            self.assertTrue(json.loads(r.read().decode())["ok"])
        last, fim, mid = "", time.time() + 30, None
        while time.time() < fim and mid is None:
            d = b.api("/api/mensagens?depois=" + urllib.request.quote(last))
            for m in d["eventos"]:
                last = m["mid"]
                if m.get("tipo") == "file" and "segue anexo" in (m.get("txt") or ""):
                    mid = m["mid"]
            time.sleep(0.5)
        self.assertIsNotNone(mid, "evento de arquivo não chegou em B")
        # conteúdo puxado via chunks P2P: pronto quando o download responde
        fim = time.time() + 90
        blob_b = None
        while time.time() < fim:
            try:
                with urllib.request.urlopen(
                        b.base + "/api/arquivo/" + mid, timeout=30) as r:
                    blob_b = r.read()
                    break
            except urllib.error.HTTPError:
                pass
            time.sleep(1.0)
        self.assertEqual(blob_b, blob)


if __name__ == "__main__":
    unittest.main()
