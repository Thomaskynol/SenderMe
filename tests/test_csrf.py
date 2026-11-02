"""CSRF na API local: Origin externo deve ser rejeitado; frontend local e
curl (sem Origin) continuam funcionando. Escrito ANTES da correção."""
import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import senderme as sm
from suporte import CasoIsolado, definir_eu


class CSRF(CasoIsolado):
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

    def post_nick(self, novo, origin=None, referer=None):
        headers = {"Content-Type": "application/json"}
        if origin is not None:
            headers["Origin"] = origin
        if referer is not None:
            headers["Referer"] = referer
        req = urllib.request.Request(
            self.base() + "/api/nick", data=json.dumps({"nick": novo}).encode(),
            headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode())
            finally:
                e.close()

    def test_origin_externo_rejeitado_sem_efeito(self):
        cod, _ = self.post_nick("invadido", origin="http://site-malicioso.test")
        self.assertEqual(cod, 403)
        self.assertEqual(sm.nick, "alice")

    def test_origin_local_autorizado(self):
        cod, corpo = self.post_nick(
            "alice2", origin=self.base())
        self.assertEqual(cod, 200)
        self.assertTrue(corpo["ok"])
        self.assertEqual(sm.nick, "alice2")

    def test_sem_origin_autorizado_curl_local(self):
        cod, corpo = self.post_nick("alice3")
        self.assertEqual(cod, 200)
        self.assertTrue(corpo["ok"])
        self.assertEqual(sm.nick, "alice3")

    def test_outra_porta_localhost_rejeitada_sem_efeito(self):
        # R6: outra porta localhost é outra origem no navegador — 403.
        # (Antes registrado como limite aceito com 200; a política
        # host+porta exige a correção, não é enfraquecimento.)
        for origem in ("http://localhost:9999/outra-app",
                       "http://127.0.0.1:9999/outra-app",
                       "http://[::1]:9999/outra-app"):
            with self.subTest(origem=origem):
                cod, _ = self.post_nick("invadido", origin=origem)
                self.assertEqual(cod, 403)
                self.assertEqual(sm.nick, "alice")

    def test_referer_outra_porta_rejeitado_sem_efeito(self):
        cod, _ = self.post_nick(
            "invadido", referer="http://127.0.0.1:9999/outra-app")
        self.assertEqual(cod, 403)
        self.assertEqual(sm.nick, "alice")

    def test_alias_cruzado_mesma_porta_rejeitado_achado_d(self):
        # Achado D: no navegador, esquema+host+porta definem a origem —
        # aliases loopback NÃO são intercambiáveis. urllib manda
        # Host: 127.0.0.1:<porta> (URL base); Origin com outro alias ou
        # outro esquema, mesmo na mesma porta, é outra origem → 403.
        # (Antes registrado como 200; a política exata exige a correção.
        # Uso consistente do alias — Host localhost + Origin localhost —
        # continua passando; ver tests/test_origem.py.)
        for origem in ("http://localhost:%d" % self.porta,
                       "http://[::1]:%d" % self.porta,
                       "https://localhost:%d/x" % self.porta,
                       "https://127.0.0.1:%d/x" % self.porta):
            with self.subTest(origem=origem):
                cod, _ = self.post_nick("invadido", origin=origem)
                self.assertEqual(cod, 403)
                self.assertEqual(sm.nick, "alice")

    def test_externo_mesma_porta_rejeitado(self):
        # Porta igual não basta: host externo continua 403.
        cod, _ = self.post_nick(
            "invadido",
            origin="http://site-malicioso.test:%d" % self.porta)
        self.assertEqual(cod, 403)
        self.assertEqual(sm.nick, "alice")

    def test_porta_implicita_e_invalida_rejeitadas(self):
        # Sem porta explícita vale 80/443 (nunca a do servidor); porta
        # inválida/fora de faixa também é 403.
        casos = [
            "http://127.0.0.1/sem-porta",
            "http://localhost/sem-porta",
            "https://127.0.0.1/sem-porta",
            "http://127.0.0.1:99999/x",
            "http://127.0.0.1:abc/x",
        ]
        for origem in casos:
            with self.subTest(origem=origem):
                cod, _ = self.post_nick("invadido", origin=origem)
                self.assertEqual(cod, 403)
                self.assertEqual(sm.nick, "alice")

    def test_referer_externo_isolado_rejeitado_sem_efeito(self):
        cod, _ = self.post_nick("invadido", referer="http://site-malicioso.test/x")
        self.assertEqual(cod, 403)
        self.assertEqual(sm.nick, "alice")

    def test_referer_local_autorizado(self):
        cod, corpo = self.post_nick(
            "alice5", referer=self.base() + "/index.html")
        self.assertEqual(cod, 200)
        self.assertTrue(corpo["ok"])
        self.assertEqual(sm.nick, "alice5")

    def test_origin_null_rejeitado_sem_efeito(self):
        # file://, iframe sandbox e alguns modos de privacidade enviam
        # literalmente "null" — nunca é o nosso frontend, sempre rejeita.
        cod, _ = self.post_nick("invadido", origin="null")
        self.assertEqual(cod, 403)
        self.assertEqual(sm.nick, "alice")

    def test_origens_invalidas_rejeitadas_sem_efeito(self):
        casos = [
            "http://[::1",              # URL malformada
            "notaurl",                   # sem esquema nem host
            "gopher://127.0.0.1:1/x",   # esquema que navegador nunca envia
            "http://evil.com@127.0.0.1/",  # userinfo: host real é evil.com
        ]
        for origem in casos:
            with self.subTest(origem=origem):
                cod, _ = self.post_nick("invadido", origin=origem)
                self.assertEqual(cod, 403)
                self.assertEqual(sm.nick, "alice")

    def test_fluxo_frontend_login_envio_upload(self):
        # Simula o frontend real: mesma origem do servidor em tudo.
        origem = self.base()
        base = self.base()

        def post_json(path, obj):
            req = urllib.request.Request(
                base + path, data=json.dumps(obj).encode(),
                headers={"Content-Type": "application/json",
                         "Origin": origem})
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode())

        with urllib.request.urlopen(base + "/", timeout=10) as r:
            self.assertEqual(r.status, 200)
            self.assertIn(b"/api/", r.read())

        sm.logado, sm.nick = False, ""
        cod, corpo = post_json("/api/login", {"nick": "alice"})
        self.assertEqual(cod, 200)
        self.assertTrue(corpo["ok"])
        self.assertTrue(sm.logado)

        cod, corpo = post_json("/api/enviar", {"texto": "ola-front"})
        self.assertEqual(cod, 200)
        self.assertTrue(corpo["ok"])

        blob = b"anexo-do-front" * 100
        bnd = "FRONT"
        corpo_up = (b"--FRONT\r\nContent-Disposition: form-data; "
                    b"name=\"texto\"\r\n\r\nsegue anexo\r\n--FRONT\r\n"
                    b"Content-Disposition: form-data; name=\"file\"; "
                    b"filename=\"doc.bin\"\r\n\r\n" + blob +
                    b"\r\n--FRONT--\r\n")
        req = urllib.request.Request(
            base + "/api/upload", data=corpo_up,
            headers={"Content-Type": "multipart/form-data; boundary=FRONT",
                     "Origin": origem})
        with urllib.request.urlopen(req, timeout=10) as r:
            self.assertTrue(json.loads(r.read().decode())["ok"])

        with urllib.request.urlopen(
                base + "/api/mensagens", timeout=10) as r:
            d = json.loads(r.read().decode())
        textos = [(m.get("txt") or "") for m in d["eventos"]]
        self.assertTrue(any("ola-front" in t for t in textos))
        self.assertTrue(any("segue anexo" in t for t in textos))


if __name__ == "__main__":
    unittest.main()
