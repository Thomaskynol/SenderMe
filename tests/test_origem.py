"""Origem estrita na API local (Achado D): alias loopback cruzado NÃO é mesma origem.

Política (dona: `_origem_ok` em `senderme_app/http.py`):
- POST mutante exige `Host` loopback (`127.0.0.1`/`localhost`/`::1`) + porta
  efetiva do servidor;
- `Origin`/`Referer` presente deve ser `http` + MESMO host do `Host`
  (sem equivaler `::1` a `127.0.0.1`) + MESMA porta; cada um é conferido
  de forma independente (inconsistência entre eles rejeita);
- sem `Origin`/`Referer` (curl local, scripts): liberado — documentado;
- resto: 403 sem efeito.
Limite conhecido: não autentica o cliente (script local passa, clique
coagido passa). Só impede que página de outra origem use o navegador
como ponte. Não é auditoria concluída.
"""
import json
import socket
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import senderme as sm
from suporte import CasoIsolado, definir_eu
from senderme_app import http as http_mod


class FakeHandler:
    def __init__(self, porta, host=None, origin=None, referer=None):
        self.headers = {}
        if host is not None:
            self.headers["Host"] = host
        if origin is not None:
            self.headers["Origin"] = origin
        if referer is not None:
            self.headers["Referer"] = referer
        self.server = type("S", (), {"server_address": ("127.0.0.1", porta)})()


def ok(porta, host=None, origin=None, referer=None):
    return http_mod._origem_ok(FakeHandler(porta, host, origin, referer))


class OrigemUnidade(CasoIsolado):
    def test_mesma_origem_exata_passa(self):
        self.assertTrue(ok(5001, "127.0.0.1:5001", "http://127.0.0.1:5001"))
        self.assertTrue(ok(5001, "localhost:5001", "http://localhost:5001/x"))
        self.assertTrue(ok(5001, "[::1]:5001", "http://[::1]:5001"))

    def test_alias_cruzado_rejeitado_achado_d(self):
        # Sonda D: Host 127.0.0.1 + Origin [::1] mesma porta → 403.
        self.assertFalse(ok(5001, "127.0.0.1:5001", "http://[::1]:5001"))
        self.assertFalse(ok(5001, "127.0.0.1:5001", "http://localhost:5001"))
        self.assertFalse(ok(5001, "localhost:5001", "http://127.0.0.1:5001"))
        self.assertFalse(ok(5001, "[::1]:5001", "http://127.0.0.1:5001"))

    def test_esquema_diferente_rejeitado(self):
        # Servidor só serve http: https nunca é a mesma origem.
        self.assertFalse(ok(5001, "127.0.0.1:5001", "https://127.0.0.1:5001"))
        self.assertFalse(ok(5001, "localhost:5001", "https://localhost:5001/x"))

    def test_porta_diferente_rejeitada(self):
        self.assertFalse(ok(5001, "127.0.0.1:5001", "http://127.0.0.1:9999"))
        self.assertFalse(ok(5001, "127.0.0.1:5001", "http://127.0.0.1/sem-porta"))

    def test_externo_null_invalido_rejeitados(self):
        for origem in ("http://site-malicioso.test/",
                       "http://site-malicioso.test:5001/",
                       "null", "notaurl", "gopher://127.0.0.1:5001/x",
                       "http://evil.com@127.0.0.1:5001/",
                       "http://127.0.0.1:99999/x", "http://[::1"):
            with self.subTest(origem=origem):
                self.assertFalse(ok(5001, "127.0.0.1:5001", origem))

    def test_sem_origin_curl_liberado_host_valido(self):
        self.assertTrue(ok(5001, "127.0.0.1:5001"))
        self.assertTrue(ok(5001, None))  # HTTP/1.0 sem Host: cliente local

    def test_host_invalido_rejeita_mesmo_sem_origin(self):
        self.assertFalse(ok(5001, "site-malicioso.test:5001"))
        self.assertFalse(ok(5001, "127.0.0.1:9999"))
        self.assertFalse(ok(5001, "evil.com@127.0.0.1:5001"))
        self.assertFalse(ok(5001, "site-malicioso.test:5001",
                            "http://127.0.0.1:5001"))

    def test_referer_sozinho_vale_mesma_regra(self):
        self.assertTrue(ok(5001, "127.0.0.1:5001", None,
                           "http://127.0.0.1:5001/index.html"))
        self.assertFalse(ok(5001, "127.0.0.1:5001", None,
                            "http://site-malicioso.test/x"))
        self.assertFalse(ok(5001, "127.0.0.1:5001", None,
                            "http://[::1]:5001/x"))

    def test_origin_e_referer_inconsistentes_rejeitados(self):
        self.assertFalse(ok(5001, "127.0.0.1:5001",
                            "http://127.0.0.1:5001",
                            "http://site-malicioso.test/x"))
        self.assertFalse(ok(5001, "127.0.0.1:5001",
                            "http://site-malicioso.test/",
                            "http://127.0.0.1:5001/x"))


class OrigemHttpReal(CasoIsolado):
    @classmethod
    def subir(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), sm.Handler)
        cls.porta = cls.srv.server_address[1]
        cls.fio = threading.Thread(target=cls.srv.serve_forever,
                                   kwargs={"poll_interval": 0.01}, daemon=True)
        cls.fio.start()

    @classmethod
    def descer(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        super().setUp()
        self.__class__.subir()
        self.addCleanup(self.__class__.descer)
        self.eu, _ = definir_eu("alice")
        sm.nick = "alice"
        sm.logado = True

    def base(self):
        return "http://127.0.0.1:%d" % self.porta

    def post(self, rota, origin=None, referer=None, host=None, dados=None):
        headers = {"Content-Type": "application/json"}
        if origin is not None:
            headers["Origin"] = origin
        if referer is not None:
            headers["Referer"] = referer
        if host is not None:
            headers["Host"] = host
        req = urllib.request.Request(
            self.base() + rota,
            data=(dados if dados is not None
                  else json.dumps({"nick": "x"}).encode()),
            headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            try:
                return e.code, e.read()
            finally:
                e.close()

    def test_sonda_d_bloqueada_sem_efeito(self):
        cod, _ = self.post("/api/nick", origin="http://[::1]:%d" % self.porta,
                           dados=json.dumps({"nick": "origem-distinta"}).encode())
        self.assertEqual(cod, 403)
        self.assertEqual(sm.nick, "alice")

    def test_todas_mutantes_rejeitam_origem_cruzada(self):
        for rota in ("/api/login", "/api/nick", "/api/enviar",
                     "/api/calar", "/api/upload"):
            with self.subTest(rota=rota):
                cod, _ = self.post(rota, origin="http://[::1]:%d" % self.porta)
                self.assertEqual(cod, 403)

    def test_legitimas_preservadas(self):
        cod, corpo = self.post(
            "/api/nick", origin=self.base(),
            dados=json.dumps({"nick": "alice2"}).encode())
        self.assertEqual(cod, 200)
        self.assertTrue(json.loads(corpo.decode())["ok"])
        self.assertEqual(sm.nick, "alice2")
        cod, corpo = self.post(
            "/api/nick", dados=json.dumps({"nick": "alice3"}).encode())
        self.assertEqual(cod, 200)
        self.assertEqual(sm.nick, "alice3")

    def test_host_falsificado_no_fio_rejeitado(self):
        # Host fora do loopback, sem Origin: DNS-rebinding não passa.
        cod = self.post_cru("site-malicioso.test", None, "invadido")
        self.assertEqual(cod, 403)
        self.assertEqual(sm.nick, "alice")

    def test_alias_consistente_no_fio_autorizado(self):
        # Página aberta por http://localhost:<porta>: fetch relativo manda
        # Host localhost + Origin localhost → mesma origem, passa.
        cod = self.post_cru("localhost:%d" % self.porta,
                            "http://localhost:%d" % self.porta, "alice-lh")
        self.assertEqual(cod, 200)
        self.assertEqual(sm.nick, "alice-lh")

    def post_cru(self, host_hdr, origin, nick):
        s = socket.create_connection(("127.0.0.1", self.porta), timeout=10)
        try:
            corpo = json.dumps({"nick": nick}).encode()
            linhas = ["POST /api/nick HTTP/1.1",
                       "Host: %s" % host_hdr,
                       "Content-Type: application/json",
                       "Content-Length: %d" % len(corpo),
                       "Connection: close"]
            if origin is not None:
                linhas.append("Origin: %s" % origin)
            req = ("\r\n".join(linhas) + "\r\n\r\n").encode() + corpo
            s.sendall(req)
            resp = b""
            while True:
                b = s.recv(4096)
                if not b:
                    break
                resp += b
        finally:
            s.close()
        return int(resp.split(b" ", 2)[1])


if __name__ == "__main__":
    unittest.main()
