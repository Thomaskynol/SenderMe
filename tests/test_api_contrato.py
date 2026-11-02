"""Caracterização: API local — shapes puros + HTTP real em porta efêmera."""
import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import senderme as sm
from suporte import CasoIsolado, definir_eu, definir_par

RAIZ = __import__("os").path.dirname(
    __import__("os").path.dirname(__import__("os").path.abspath(__file__)))


class ShapesPuros(CasoIsolado):
    def test_hora_de_formato(self):
        import re
        self.assertRegex(sm.hora_de(1700000000), r"^\d{2}/\d{2} \d{2}:\d{2}$")
        self.assertEqual(sm.hora_de("lixo"), "--/-- --:--")

    def test_evento_para_api_tipos(self):
        eu, _ = definir_eu("alice")
        sm.nick = "alice"
        m = sm.evento_para_api(sm.criar_evento("msg", "oi"))
        self.assertEqual((m["tipo"], m["dm"], m["proprio"]), ("msg", False, True))
        self.assertEqual(m["nick"], "alice")
        peer, _ = definir_par("bob")
        d = sm.evento_para_api(criar_dm(peer))
        self.assertTrue(d["dm"])
        j = sm.evento_para_api(sm.criar_evento("join", ""))
        self.assertIn("entrou", j["txt"])
        lv = sm.evento_para_api(sm.criar_evento("leave", peer["id"]))
        self.assertIn("saiu", lv["txt"])
        nk = sm.evento_para_api(sm.criar_evento("nick", "beto"))
        self.assertIn("agora é", nk["txt"])
        self.assertIsNone(sm.evento_para_api({"tipo": "fax", "mid": "x"}))

    def test_evento_file_pronto(self):
        definir_eu("alice")
        import hashlib as _h
        blob = b"dados"
        ev = sm.criar_evento_file("leg", "f.txt", len(blob),
                                  _h.sha256(blob).hexdigest())
        d = sm.evento_para_api(ev)
        self.assertFalse(d["arq"]["pronto"])
        sm.salvar_bytes_arquivo(ev["mid"], blob)
        self.assertTrue(sm.evento_para_api(ev)["arq"]["pronto"])

    def test_mensagens_para_api_janela_e_calados(self):
        definir_eu("alice")
        for i in range(60):
            sm.processar(sm.criar_evento("msg", "m%d" % i), disco=False)
        evs, pres = sm.mensagens_para_api("")
        self.assertEqual(len(evs), 50)  # janela inicial
        self.assertTrue(any(p["eu"] for p in pres))
        evs2, _ = sm.mensagens_para_api(sm.historico[9]["mid"])
        self.assertEqual(evs2[0]["mid"], sm.historico[10]["mid"])
        self.assertLessEqual(len(evs2), 200)
        evs3, _ = sm.mensagens_para_api("mid-inexistente")
        self.assertEqual(len(evs3), 50)  # depois desconhecido: últimos 50
        peer, _ = definir_par("calado")
        sm.calados.add(peer["id"])
        from suporte import criar_como
        evp = criar_como(peer, "calado", "msg", "oculta")
        sm.processar(evp, disco=False)
        evs4, _ = sm.mensagens_para_api("")
        self.assertNotIn(evp["mid"], [e["mid"] for e in evs4])

    def test_parse_multipart(self):
        bnd = "LIMITE"
        corpo = (b"--LIMITE\r\nContent-Disposition: form-data; name=\"texto\"\r\n\r\n"
                 b"oi\r\n--LIMITE\r\nContent-Disposition: form-data; "
                 b"name=\"file\"; filename=\"a.txt\"\r\n\r\nbinario\r\n--LIMITE--\r\n")
        campos, arqs = sm._parse_multipart(corpo, "multipart/form-data; boundary=LIMITE")
        self.assertEqual(campos["texto"], "oi")
        self.assertEqual(arqs["file"], ("a.txt", b"binario"))
        self.assertEqual(sm._parse_multipart(b"x", "text/plain"), ({}, {}))


def criar_dm(peer):
    from suporte import criar_como
    return criar_como(peer, "bob", "dm", "psst", para=sm.ident["id"])


class HTTPReal(CasoIsolado):
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
        sm.logado = True

    def base(self):
        return "http://127.0.0.1:%d" % self.porta

    def get(self, rota):
        try:
            with urllib.request.urlopen(self.base() + rota, timeout=10) as r:
                return r.status, r.read(), r.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers

    def post_json(self, rota, obj):
        req = urllib.request.Request(self.base() + rota,
                                     data=json.dumps(obj).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    def test_eu_shape(self):
        cod, corpo, _ = self.get("/api/eu")
        self.assertEqual(cod, 200)
        d = json.loads(corpo.decode())
        for k in ("id", "nick", "logado", "precisa_login"):
            self.assertIn(k, d)
        self.assertEqual(d["id"], self.eu["id"])
        self.assertTrue(d["logado"])
        self.assertFalse(d["precisa_login"])

    def test_mensagens_e_auxiliares(self):
        sm.processar(sm.criar_evento("msg", "oi"), disco=False)
        cod, corpo, _ = self.get("/api/mensagens?depois=")
        d = json.loads(corpo.decode())
        self.assertIn("eventos", d)
        self.assertIn("presentes", d)
        for rota in ("/api/rede", "/api/ajuda", "/api/calados"):
            cod, _, _ = self.get(rota)
            self.assertEqual(cod, 200, rota)

    def test_arquivo_rotas(self):
        cod, _, _ = self.get("/api/arquivo/nao-hex!")
        self.assertEqual(cod, 400)
        cod, _, _ = self.get("/api/arquivo/" + "0" * 64)
        self.assertEqual(cod, 404)
        import hashlib as _h
        blob = b"baixar-teste"
        ok, _ = sm.publicar_arquivo_global("", "down.bin", blob)
        self.assertTrue(ok)
        mid = sm.historico[-1]["mid"]
        cod, corpo, h = self.get("/api/arquivo/" + mid)
        self.assertEqual(cod, 200)
        self.assertEqual(corpo, blob)
        self.assertIn("attachment", h.get("Content-Disposition", ""))

    def test_upload_sem_arquivo_e_vazio_400(self):
        import urllib.error
        bnd = "B"
        corpo = (b"--B\r\nContent-Disposition: form-data; name=\"texto\"\r\n\r\n"
                 + "só texto".encode("utf-8") + b"\r\n--B--\r\n")
        req = urllib.request.Request(self.base() + "/api/upload", data=corpo,
                                     headers={"Content-Type":
                                              "multipart/form-data; boundary=B"})
        try:
            urllib.request.urlopen(req, timeout=10)
            self.fail("esperava 400")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)
        corpo2 = (b"--B\r\nContent-Disposition: form-data; name=\"file\"; "
                  b"filename=\"v.txt\"\r\n\r\n\r\n--B--\r\n")
        req2 = urllib.request.Request(self.base() + "/api/upload", data=corpo2,
                                      headers={"Content-Type":
                                               "multipart/form-data; boundary=B"})
        try:
            urllib.request.urlopen(req2, timeout=10)
            self.fail("esperava 400 vazio")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)

    def test_upload_maior_que_20mb_413(self):
        import urllib.error
        bnd = "B"
        grande = b"x" * (sm.MAX_ARQUIVO + 1)
        corpo = (b"--B\r\nContent-Disposition: form-data; name=\"file\"; "
                 b"filename=\"g.bin\"\r\n\r\n" + grande + b"\r\n--B--\r\n")
        req = urllib.request.Request(self.base() + "/api/upload", data=corpo,
                                     headers={"Content-Type":
                                              "multipart/form-data; boundary=B"})
        try:
            urllib.request.urlopen(req, timeout=10)
            self.fail("esperava 413")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 413)


class EnviarEstadoHttp(CasoIsolado):
    """Achado 1 (HTTP): POST /api/enviar inclui `estado` estável.

    Valores fixos: entregue/guardada/somente_memoria/erro; `ok`/`msg`/
    `resposta` intactos (compat)."""

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

    def post_enviar(self, texto, para=""):
        import urllib.error
        req = urllib.request.Request(
            self.base() + "/api/enviar",
            data=json.dumps({"texto": texto, "para": para}).encode(),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    def test_publica_entregue_com_compat(self):
        cod, d = self.post_enviar("oi pública")
        self.assertEqual(cod, 200)
        self.assertTrue(d["ok"])
        self.assertEqual(d["estado"], "entregue")
        for k in ("ok", "msg", "resposta"):
            self.assertIn(k, d, "compat: %s ausente" % k)

    def test_erro_guardada_nome_confunde(self):
        # "@guardada" inexistente: erro, nada guardado (só o nome confunde).
        cod, d = self.post_enviar("oi", "@guardada")
        self.assertFalse(d["ok"])
        self.assertEqual(d["estado"], "erro")
        self.assertIn("msg", d)
        self.assertIn("resposta", d)
        self.assertEqual(sm.historico, [])

    def test_guardada_offline_aviso(self):
        definir_par("aviso", presente=True)
        cod, d = self.post_enviar("oi", "@aviso")
        self.assertFalse(d["ok"])
        self.assertEqual(d["estado"], "guardada")
        self.assertEqual(len(sm.historico), 1)

    def test_somente_memoria_offline_sem_persist(self):
        import os
        definir_par("bob", presente=True)
        p = __import__("os").path.join(sm.DADOS, "historico.jsonl")
        if os.path.isfile(p):
            os.remove(p)
        os.makedirs(p, exist_ok=True)
        self.addCleanup(lambda: os.rmdir(p) if os.path.isdir(p) else None)
        _, d = self.post_enviar("oi", "@bob")
        self.assertFalse(d["ok"])
        self.assertEqual(d["estado"], "somente_memoria")

    def test_entregue_dm_direta_e_via_barra(self):
        from suporte import FakeSock
        peer, _ = definir_par("bob", presente=True)
        sock = FakeSock()
        sm.conns[peer["id"]] = {sock}
        sm.sockets_vivos.add(sock)
        _, d = self.post_enviar("segredo", "@bob")
        self.assertTrue(d["ok"])
        self.assertEqual(d["estado"], "entregue")
        sm.conns[peer["id"]] = {sock}
        sm.sockets_vivos.add(sock)
        _, d2 = self.post_enviar("/dm @bob outro-segredo")
        self.assertTrue(d2["ok"])
        self.assertEqual(d2["estado"], "entregue")

    def test_erro_vazio(self):
        _, d = self.post_enviar("", "@bob")
        self.assertEqual(d["estado"], "erro")


class EnviarTransmitidaHttp(CasoIsolado):
    """Item 2 (1.10, HTTP): `transmitida` por caso, `ok`/`msg`/`resposta`/
    `estado` intactos. true = bytes entregues ao socket; nunca confirma
    recebimento/leitura pelo destinatário."""

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

    def post_enviar(self, texto, para=""):
        import urllib.error
        req = urllib.request.Request(
            self.base() + "/api/enviar",
            data=json.dumps({"texto": texto, "para": para}).encode(),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    def test_matriz_transmitida(self):
        from suporte import FakeSock
        casos = []
        # enviada+persistida -> (true, entregue)
        peer, _ = definir_par("bob", presente=True)
        sock = FakeSock()
        sm.conns[peer["id"]] = {sock}
        sm.sockets_vivos.add(sock)
        _, d = self.post_enviar("segredo", "@bob")
        casos.append(("enviada+persistida", d, True, "entregue", True))
        # guardada p/ futuro -> (false, guardada)
        definir_par("carol", presente=True)
        _, d = self.post_enviar("oi", "@carol")
        casos.append(("guardada", d, False, "guardada", False))
        # erro -> (false, erro)
        _, d = self.post_enviar("oi", "@fantasma")
        casos.append(("erro", d, False, "erro", False))
        for nome, d, ok, estado, transm in casos:
            with self.subTest(nome):
                self.assertIs(d["ok"], ok)
                self.assertEqual(d["estado"], estado)
                self.assertIs(d["transmitida"], transm)
                for k in ("ok", "msg", "resposta", "estado"):
                    self.assertIn(k, d, "compat: %s ausente" % k)
                self.assertIsInstance(d["transmitida"], bool)

    def test_transmitida_true_falha_persist(self):
        import os
        from suporte import FakeSock
        peer, _ = definir_par("dave", presente=True)
        sock = FakeSock()
        sm.conns[peer["id"]] = {sock}
        sm.sockets_vivos.add(sock)
        p = __import__("os").path.join(sm.DADOS, "historico.jsonl")
        if os.path.isfile(p):
            os.remove(p)
        os.makedirs(p, exist_ok=True)
        self.addCleanup(lambda: os.rmdir(p) if os.path.isdir(p) else None)
        _, d = self.post_enviar("oi", "@dave")
        self.assertTrue(d["ok"])
        self.assertEqual(d["estado"], "somente_memoria")
        self.assertIs(d["transmitida"], True)

    def test_transmitida_false_sem_envio_sem_persist(self):
        import os
        definir_par("erin", presente=True)
        p = __import__("os").path.join(sm.DADOS, "historico.jsonl")
        if os.path.isfile(p):
            os.remove(p)
        os.makedirs(p, exist_ok=True)
        self.addCleanup(lambda: os.rmdir(p) if os.path.isdir(p) else None)
        _, d = self.post_enviar("oi", "@erin")
        self.assertFalse(d["ok"])
        self.assertEqual(d["estado"], "somente_memoria")
        self.assertIs(d["transmitida"], False)

    def test_publica_entregue_transmitida_bool(self):
        _, d = self.post_enviar("oi pública")
        self.assertTrue(d["ok"])
        self.assertEqual(d["estado"], "entregue")
        self.assertIsInstance(d["transmitida"], bool)


class NivelConfirmadoPeersHttp(CasoIsolado):
    """Item 3 (1.11, HTTP): `nivel`/`confirmado`/`peers` explicitos, compat.

    Desenho: mantem `transmitida` bool com semantica documentada por
    contexto (DM = bytes ao socket; demais = aceitacao local) + campo de
    nivel que desambigua. `nivel` in {"local","socket"}; `confirmado`
    sempre False (hoje nunca ha confirmacao — NUNCA afirma recebimento/
    leitura); `peers` = nº de peers conectados no envio. Campos antigos
    intactos (tipos/valores); novos opcionais (ausentes = backend antigo).
    """

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

    def post_enviar(self, texto, para=""):
        import urllib.error
        req = urllib.request.Request(
            self.base() + "/api/enviar",
            data=json.dumps({"texto": texto, "para": para}).encode(),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    def test_publica_sem_peers_nivel_local(self):
        _, d = self.post_enviar("oi publica sem peers")
        self.assertTrue(d["ok"])
        self.assertEqual(d["estado"], "entregue")
        self.assertIs(d["transmitida"], True)  # compat: aceitacao local
        self.assertEqual(d["nivel"], "local")
        self.assertIs(d["confirmado"], False)
        self.assertEqual(d["peers"], 0)

    def test_publica_com_peers_conta(self):
        from suporte import FakeSock
        for nome in ("bob", "carol"):
            peer, _ = definir_par(nome, presente=True)
            sock = FakeSock()
            sm.conns[peer["id"]] = {sock}
            sm.sockets_vivos.add(sock)
        _, d = self.post_enviar("oi publica com peers")
        self.assertTrue(d["ok"])
        self.assertEqual(d["estado"], "entregue")
        self.assertIs(d["transmitida"], True)
        self.assertEqual(d["nivel"], "local")
        self.assertIs(d["confirmado"], False)
        self.assertEqual(d["peers"], 2)

    def test_dm_socket_nivel_socket(self):
        from suporte import FakeSock
        peer, _ = definir_par("bob", presente=True)
        sock = FakeSock()
        sm.conns[peer["id"]] = {sock}
        sm.sockets_vivos.add(sock)
        _, d = self.post_enviar("segredo", "@bob")
        self.assertTrue(d["ok"])
        self.assertEqual(d["estado"], "entregue")
        self.assertIs(d["transmitida"], True)
        self.assertEqual(d["nivel"], "socket")
        self.assertIs(d["confirmado"], False)

    def test_dm_barra_socket_nivel_socket(self):
        from suporte import FakeSock
        peer, _ = definir_par("bob", presente=True)
        sock = FakeSock()
        sm.conns[peer["id"]] = {sock}
        sm.sockets_vivos.add(sock)
        _, d = self.post_enviar("/dm @bob outro-segredo")
        self.assertTrue(d["ok"])
        self.assertEqual(d["estado"], "entregue")
        self.assertEqual(d["nivel"], "socket")
        self.assertIs(d["confirmado"], False)

    def test_dm_guardada_nivel_local(self):
        definir_par("carol", presente=True)
        _, d = self.post_enviar("oi", "@carol")
        self.assertFalse(d["ok"])
        self.assertEqual(d["estado"], "guardada")
        self.assertIs(d["transmitida"], False)
        self.assertEqual(d["nivel"], "local")
        self.assertIs(d["confirmado"], False)

    def test_erro_nivel_local(self):
        _, d = self.post_enviar("oi", "@fantasma")
        self.assertFalse(d["ok"])
        self.assertEqual(d["estado"], "erro")
        self.assertIs(d["transmitida"], False)
        self.assertEqual(d["nivel"], "local")
        self.assertIs(d["confirmado"], False)

    def test_somente_memoria_socket_vs_local(self):
        import os
        from suporte import FakeSock
        peer, _ = definir_par("dave", presente=True)
        sock = FakeSock()
        sm.conns[peer["id"]] = {sock}
        sm.sockets_vivos.add(sock)
        p = __import__("os").path.join(sm.DADOS, "historico.jsonl")
        if os.path.isfile(p):
            os.remove(p)
        os.makedirs(p, exist_ok=True)
        self.addCleanup(lambda: os.rmdir(p) if os.path.isdir(p) else None)
        _, d = self.post_enviar("oi", "@dave")
        self.assertEqual(d["estado"], "somente_memoria")
        self.assertIs(d["transmitida"], True)
        self.assertEqual(d["nivel"], "socket")
        self.assertIs(d["confirmado"], False)

    def test_somente_memoria_sem_envio_nivel_local(self):
        import os
        definir_par("erin", presente=True)
        p = __import__("os").path.join(sm.DADOS, "historico.jsonl")
        if os.path.isfile(p):
            os.remove(p)
        os.makedirs(p, exist_ok=True)
        self.addCleanup(lambda: os.rmdir(p) if os.path.isdir(p) else None)
        _, d = self.post_enviar("oi", "@erin")
        self.assertEqual(d["estado"], "somente_memoria")
        self.assertIs(d["transmitida"], False)
        self.assertEqual(d["nivel"], "local")
        self.assertIs(d["confirmado"], False)

    def test_compat_antigos_intactos_e_novos_tipos(self):
        _, d = self.post_enviar("oi publica")
        for k in ("ok", "msg", "resposta", "estado", "transmitida"):
            self.assertIn(k, d, "compat: %s ausente" % k)
        self.assertIsInstance(d["transmitida"], bool)
        self.assertIn(d["estado"], ("entregue", "guardada", "somente_memoria", "erro"))
        self.assertIn(d["nivel"], ("local", "socket"))
        self.assertIsInstance(d["confirmado"], bool)
        self.assertIsInstance(d["peers"], int)


if __name__ == "__main__":
    unittest.main()
