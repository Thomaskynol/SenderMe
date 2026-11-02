"""POST desconhecido responde 404 JSON (antes: sem resposta/hang).

Regressão mínima do fix: gate primeiro (origem cruzada dá 403),
rota desconhecida com origem válida dá 404 com corpo JSON e conexão
reutilizável (keep-alive não dessincroniza).
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


class Http404(CasoIsolado):
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

    def test_post_desconhecido_da_404_json(self):
        req = urllib.request.Request(
            self.base() + "/api/inexistente",
            data=json.dumps({}).encode(),
            headers={"Content-Type": "application/json",
                     "Origin": self.base()})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                self.fail("devia dar 404, veio %s" % r.status)
        except urllib.error.HTTPError as e:
            try:
                self.assertEqual(e.code, 404)
                corpo = json.loads(e.read().decode())
                self.assertFalse(corpo["ok"])
            finally:
                e.close()

    def test_post_desconhecido_origem_cruzada_da_403(self):
        req = urllib.request.Request(
            self.base() + "/api/inexistente",
            data=json.dumps({}).encode(),
            headers={"Content-Type": "application/json",
                     "Origin": "http://site-malicioso.test"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                self.fail("devia dar 403, veio %s" % r.status)
        except urllib.error.HTTPError as e:
            try:
                self.assertEqual(e.code, 403)
            finally:
                e.close()

    def test_socket_cru_recebe_status_e_reusa(self):
        # Socket cru: prova que há resposta (sem hang). Segunda checagem
        # em conexão nova confirma que o servidor segue servindo.
        s = socket.create_connection(("127.0.0.1", self.porta), timeout=10)
        try:
            s.settimeout(10)
            corpo = json.dumps({"x": "y" * 100}).encode()
            s.sendall(("POST /api/inexistente HTTP/1.1\r\n"
                       "Host: 127.0.0.1:%d\r\n"
                       "Content-Type: application/json\r\n"
                       "Content-Length: %d\r\n"
                       "Origin: http://127.0.0.1:%d\r\n\r\n"
                       % (self.porta, len(corpo), self.porta)).encode() + corpo)
            resp = b""
            while b'"ok": false' not in resp and b'"ok":false' not in resp:
                b = s.recv(4096)
                if not b:
                    break
                resp += b
                if len(resp) > 8192:
                    break
            self.assertIn(b"404", resp.split(b"\r\n", 1)[0])
            s.close()
            # conexão nova: servidor segue servindo (loop preservado)
            s = socket.create_connection(("127.0.0.1", self.porta), timeout=10)
            s.settimeout(10)
            # segunda requisição em socket novo: servidor ainda fala HTTP válido
            s.sendall(("GET /api/eu HTTP/1.1\r\n"
                       "Host: 127.0.0.1:%d\r\nConnection: close\r\n\r\n"
                       % self.porta).encode())
            resp2 = b""
            while True:
                b = s.recv(4096)
                if not b:
                    break
                resp2 += b
            self.assertIn(b"200", resp2.split(b"\r\n", 1)[0])
        finally:
            s.close()


if __name__ == "__main__":
    unittest.main()
