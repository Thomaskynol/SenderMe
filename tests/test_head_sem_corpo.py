"""Achado 3 — HEAD nunca leva corpo (socket real).

Contrato: HEAD responde status+headers, sem bytes de corpo, com
Content-Length igual ao que o GET correspondente retornaria.
GET/POST preservados (com corpo). Só stdlib, 127.0.0.1 efêmero, sintéticos.
"""
import socket
import threading
import unittest
from http.server import ThreadingHTTPServer

import senderme as sm
from suporte import CasoIsolado, definir_eu


class HeadSemCorpo(CasoIsolado):
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
        sm.historico.append(sm.criar_evento("msg", "mensagem-sintetica"))

    def cru(self, metodo, rota, host=None, origin=None, versao="HTTP/1.1",
            omitir_host=False):
        s = socket.create_connection(("127.0.0.1", self.porta), timeout=10)
        try:
            s.settimeout(10)
            linhas = ["%s %s %s" % (metodo, rota, versao)]
            if not omitir_host:
                linhas.append("Host: %s" % host)
            if origin is not None:
                linhas.append("Origin: %s" % origin)
            linhas.append("Connection: close")
            linhas.append("")
            linhas.append("")
            s.sendall(("\r\n".join(linhas)).encode())
            resp = b""
            while True:
                b = s.recv(4096)
                if not b:
                    break
                resp += b
        finally:
            s.close()
        cab, _, corpo = resp.partition(b"\r\n\r\n")
        status = int(resp.split(b" ", 2)[1])
        cabs = {}
        for lin in cab.decode("iso-8859-1").split("\r\n")[1:]:
            if ":" in lin:
                k, _, v = lin.partition(":")
                cabs[k.strip().lower()] = v.strip()
        return status, cabs, corpo, resp

    def base_host(self):
        return "127.0.0.1:%d" % self.porta

    def test_head_externo_403_sem_corpo_content_length_correto(self):
        # Sonda do Achado 3: HEAD / com origem externa era 403 + 55 bytes.
        st, cabs, corpo, _ = self.cru(
            "HEAD", "/", self.base_host(), "http://site-malicioso.test/")
        self.assertEqual(st, 403)
        self.assertEqual(corpo, b"",
                         "HEAD não deve enviar corpo (Achado 3)")
        # Content-Length deve dizer o que o GET retornaria (55 do JSON 403).
        _, _, corpo_get, _ = self.cru(
            "GET", "/", self.base_host(), "http://site-malicioso.test/")
        self.assertGreater(len(corpo_get), 0, "GET 403 deve ter corpo p/ comparar")
        self.assertEqual(cabs.get("content-length"), str(len(corpo_get)))
        self.assertEqual(len(corpo_get), 55)

    def test_head_api_externo_403_sem_corpo(self):
        st, cabs, corpo, _ = self.cru(
            "HEAD", "/api/mensagens",
            "externo.example:%d" % self.porta,
            "http://externo.example:%d" % self.porta)
        self.assertEqual(st, 403)
        self.assertEqual(corpo, b"")
        self.assertIn("content-length", cabs)
        _, _, corpo_get, _ = self.cru(
            "GET", "/api/mensagens",
            "externo.example:%d" % self.porta,
            "http://externo.example:%d" % self.porta)
        self.assertEqual(cabs.get("content-length"), str(len(corpo_get)))

    def test_head_legitimo_501_sem_corpo(self):
        # HEAD não é usado pela interface; preserva 501 sem vazar corpo.
        # stdlib já omite corpo p/ HEAD; _json também omite (403 acima).
        st, cabs, corpo, _ = self.cru("HEAD", "/", self.base_host(), None)
        self.assertEqual(st, 501)
        self.assertEqual(corpo, b"")
        self.assertIn("content-length", cabs)
        self.assertGreater(int(cabs["content-length"]), 0)
        st2, _, corpo2, _ = self.cru(
            "HEAD", "/api/mensagens", self.base_host(), None)
        self.assertIn(st2, (501,))
        self.assertEqual(corpo2, b"")

    def test_get_post_preservados_com_corpo(self):
        # GET legítimo continua com corpo.
        st, _, corpo, _ = self.cru("GET", "/api/mensagens",
                                   self.base_host(), None)
        self.assertEqual(st, 200)
        self.assertIn(b"mensagem-sintetica", corpo)
        # GET 403 continua com corpo (só HEAD tira).
        _, _, corpo403, _ = self.cru(
            "GET", "/api/mensagens",
            "site-malicioso.test:%d" % self.porta, None)
        self.assertGreater(len(corpo403), 0)
        # POST legítimo e POST 403 continuam com corpo JSON.
        import json
        import urllib.request
        import urllib.error
        base = "http://127.0.0.1:%d" % self.porta

        def post_json(rota, obj, origin=None):
            h = {"Content-Type": "application/json"}
            if origin is not None:
                h["Origin"] = origin
            req = urllib.request.Request(base + rota,
                                         data=json.dumps(obj).encode(),
                                         headers=h)
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    return r.status, r.read()
            except urllib.error.HTTPError as e:
                return e.code, e.read()
        cod, corpo_ok = post_json("/api/nick", {"nick": "alice-post"})
        self.assertEqual(cod, 200)
        self.assertGreater(len(corpo_ok), 0)
        cod2, corpo_403 = post_json("/api/nick", {"nick": "x"},
                                    "http://site-malicioso.test/")
        self.assertEqual(cod2, 403)
        self.assertGreater(len(corpo_403), 0)


if __name__ == "__main__":
    unittest.main()
