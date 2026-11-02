"""Host em GET/HEAD e demais métodos (item 4): mesma política do POST.

Preserva curl sem Origin + interface normal; bloqueia Host externo/inválido
e Origin cruzado inclusive em leitura. Não reescreve política D (`_origem_ok`
intacta) — só estende o gate a `do_GET`/`do_HEAD`/métodos desconhecidos.
Limite: sem repro em navegador; endurecimento comprovado no servidor.
"""
import socket
import threading
import unittest
from http.server import ThreadingHTTPServer

import senderme as sm
from suporte import CasoIsolado, definir_eu


class HostGet(CasoIsolado):
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

    def cru(self, metodo, rota, host=None, origin=None, referer=None,
            versao="HTTP/1.1", omitir_host=False):
        s = socket.create_connection(("127.0.0.1", self.porta), timeout=10)
        try:
            s.settimeout(10)
            linhas = ["%s %s %s" % (metodo, rota, versao)]
            if not omitir_host:
                linhas.append("Host: %s" % host)
            if origin is not None:
                linhas.append("Origin: %s" % origin)
            if referer is not None:
                linhas.append("Referer: %s" % referer)
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
        status = int(resp.split(b" ", 2)[1])
        return status, resp

    def base_host(self):
        return "127.0.0.1:%d" % self.porta

    def base_origem(self):
        return "http://127.0.0.1:%d" % self.porta

    def test_sonda_item4_host_origin_externos_bloqueados(self):
        cod, corpo = self.cru("GET", "/api/mensagens",
                              "externo.example:%d" % self.porta,
                              "http://externo.example:%d" % self.porta)
        self.assertEqual(cod, 403)
        self.assertNotIn(b"mensagem-sintetica", corpo)

    def test_get_host_externo_sem_origin_bloqueado(self):
        cod, corpo = self.cru("GET", "/api/mensagens",
                              "site-malicioso.test:%d" % self.porta, None)
        self.assertEqual(cod, 403)
        self.assertNotIn(b"mensagem-sintetica", corpo)

    def test_get_host_valido_origin_externo_bloqueado(self):
        cod, _ = self.cru("GET", "/api/mensagens", self.base_host(),
                          "http://site-malicioso.test/")
        self.assertEqual(cod, 403)

    def test_get_alias_cruzado_bloqueado_achado_d(self):
        cod, _ = self.cru("GET", "/api/mensagens", self.base_host(),
                          "http://localhost:%d" % self.porta)
        self.assertEqual(cod, 403)
        cod, _ = self.cru("GET", "/api/mensagens",
                          "localhost:%d" % self.porta, self.base_origem())
        self.assertEqual(cod, 403)

    def test_get_curl_sem_origin_preservado(self):
        cod, corpo = self.cru("GET", "/api/mensagens", self.base_host(), None)
        self.assertEqual(cod, 200)
        self.assertIn(b"mensagem-sintetica", corpo)

    def test_get_mesma_origem_preservada(self):
        cod, corpo = self.cru("GET", "/api/mensagens", self.base_host(),
                              self.base_origem())
        self.assertEqual(cod, 200)
        self.assertIn(b"mensagem-sintetica", corpo)

    def test_get_localhost_consistente_preservado(self):
        h = "localhost:%d" % self.porta
        o = "http://localhost:%d" % self.porta
        cod, _ = self.cru("GET", "/api/mensagens", h, o)
        self.assertEqual(cod, 200)

    def test_get_sem_host_http10_preservado(self):
        cod, corpo = self.cru("GET", "/api/mensagens", None, None,
                              versao="HTTP/1.0", omitir_host=True)
        self.assertEqual(cod, 200)
        self.assertIn(b"mensagem-sintetica", corpo)

    def test_get_host_invalido_rejeitado(self):
        for host in ("site-malicioso.test:%d" % self.porta,
                     "127.0.0.1:9999",
                     "evil.com@127.0.0.1:%d" % self.porta,
                     "127.0.0.1:99999"):
            with self.subTest(host=host):
                cod, corpo = self.cru("GET", "/api/mensagens", host, None)
                self.assertEqual(cod, 403)
                self.assertNotIn(b"mensagem-sintetica", corpo)

    def test_get_raiz_e_eu_gate(self):
        cod, _ = self.cru("GET", "/", "externo.example:%d" % self.porta,
                          "http://externo.example:%d" % self.porta)
        self.assertEqual(cod, 403)
        cod, _ = self.cru("GET", "/", self.base_host(), None)
        self.assertEqual(cod, 200)
        cod, _ = self.cru("GET", "/api/eu",
                          "externo.example:%d" % self.porta, None)
        self.assertEqual(cod, 403)
        cod, _ = self.cru("GET", "/api/eu", self.base_host(), None)
        self.assertEqual(cod, 200)

    def test_head_externo_bloqueado_legitimo_sem_vazar(self):
        cod, corpo = self.cru("HEAD", "/api/mensagens",
                              "externo.example:%d" % self.porta,
                              "http://externo.example:%d" % self.porta)
        self.assertEqual(cod, 403)
        self.assertNotIn(b"mensagem-sintetica", corpo)
        cod, corpo = self.cru("HEAD", "/api/mensagens",
                              self.base_host(), None)
        self.assertIn(cod, (200, 501))
        self.assertNotIn(b"mensagem-sintetica", corpo)

    def test_metodo_desconhecido_externo_bloqueado(self):
        cod, _ = self.cru("PUT", "/api/mensagens",
                          "externo.example:%d" % self.porta, None)
        self.assertEqual(cod, 403)
        cod, _ = self.cru("PUT", "/api/mensagens", self.base_host(), None)
        self.assertEqual(cod, 501)


class HeadSemCorpoGate(CasoIsolado):
    """Achado 3 (gate): HEAD 403/501 nunca leva corpo; Content-Length correto.

    Aditivo ao gate existente — não reescreve a política `_origem_ok`."""

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

    def cru(self, metodo, rota, host, origin=None):
        s = socket.create_connection(("127.0.0.1", self.porta), timeout=10)
        try:
            linhas = ["%s %s HTTP/1.1" % (metodo, rota), "Host: %s" % host]
            if origin is not None:
                linhas.append("Origin: %s" % origin)
            linhas += ["Connection: close", "", ""]
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
        st = int(resp.split(b" ", 2)[1])
        cls = {}
        for lin in cab.decode("iso-8859-1").split("\r\n")[1:]:
            if ":" in lin:
                k, _, v = lin.partition(":")
                cls[k.strip().lower()] = v.strip()
        return st, cls, corpo

    def test_head_403_e_501_sem_corpo(self):
        h = "127.0.0.1:%d" % self.porta
        st, cabs, corpo = self.cru("HEAD", "/", h,
                                   "http://site-malicioso.test/")
        self.assertEqual(st, 403)
        self.assertEqual(corpo, b"")
        self.assertEqual(cabs.get("content-length"), "55")
        st2, cabs2, corpo2 = self.cru("HEAD", "/", h, None)
        self.assertEqual(st2, 501)
        self.assertEqual(corpo2, b"")
        self.assertGreater(int(cabs2.get("content-length", "0")), 0)


if __name__ == "__main__":
    unittest.main()
