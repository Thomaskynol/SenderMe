"""Caracterização: arquivos — chunk remonta+sha, throttle, limites."""
import base64
import hashlib
import os
import unittest

import senderme as sm
from suporte import (CasoIsolado, FakeSock, criar_como, definir_eu,
                     definir_par, quadros)


class ChunkMontaConfereSha(CasoIsolado):
    def setUp(self):
        super().setUp()
        self.eu, _ = definir_eu("alice")
        self.peer, self.pchave = definir_par("bob")
        self.blob = b"0123456789abcdef" * 100  # 1600 bytes
        self.sha = hashlib.sha256(self.blob).hexdigest()
        self.ev = criar_como(self.peer, "bob", "file", "leg",
                             arq={"nome": "f.bin", "tamanho": len(self.blob),
                                  "sha256": self.sha})
        sm.processar(self.ev, disco=False)
        sm.salvar_bytes_arquivo(self.ev["mid"], self.blob)

    def test_servir_e_remontar(self):
        sock = FakeSock()
        sm.conns[self.peer["id"]] = {sock}
        sm.sockets_vivos.add(sock)
        sm.servir_arquivo(self.peer["id"], self.ev["mid"])
        frames = quadros(sock)
        self.assertTrue(all(f["t"] == "file_chunk" for f in frames))
        self.assertEqual(len(frames), 1)  # 1600 bytes < 512 KB
        os.remove(sm.caminho_bin(self.ev["mid"]))  # finge lado que não tem
        for f in frames:
            sm.receber_chunk(f)
        self.assertEqual(sm.ler_bytes_arquivo(self.ev["mid"]), self.blob)
        self.assertNotIn(self.ev["mid"], sm.montando)  # slot limpo

    def test_hash_divergente_descarta(self):
        total = 1
        q = {"t": "file_chunk", "mid": self.ev["mid"], "idx": 0, "total": total,
             "dados": base64.b64encode(b"lixo").decode()}
        os.remove(sm.caminho_bin(self.ev["mid"]))
        sm.receber_chunk(q)
        self.assertIsNone(sm.ler_bytes_arquivo(self.ev["mid"]))
        self.assertNotIn(self.ev["mid"], sm.montando)

    def test_chunk_invalido_ignorado(self):
        for q in ({"t": "file_chunk", "mid": "curto", "idx": 0, "total": 1,
                   "dados": base64.b64encode(b"x").decode()},
                  {"t": "file_chunk", "mid": self.ev["mid"], "idx": 9,
                   "total": 1, "dados": base64.b64encode(b"x").decode()},
                  {"t": "file_chunk", "mid": "z" * 64, "idx": 0, "total": 1,
                   "dados": base64.b64encode(b"x").decode()}):
            sm.receber_chunk(q)  # não levanta
        self.assertEqual(sm.montando, {})


class FileReqThrottle(CasoIsolado):
    def test_throttle_30s_e_sem_throttle_quando_ja_tem(self):
        definir_eu("alice")
        mid = "a" * 64
        sm.pedir_arquivo(mid)
        t1 = sm.pedidos_arq[mid]
        sm.pedir_arquivo(mid)
        self.assertEqual(sm.pedidos_arq[mid], t1)
        sm.pedidos_arq[mid] = t1 - 31
        sm.pedir_arquivo(mid)
        self.assertGreater(sm.pedidos_arq[mid], t1 - 31)


class LimitesUpload(CasoIsolado):
    def test_global_maior_que_20mb_rejeita(self):
        definir_eu("alice")
        ok, msg = sm.publicar_arquivo_global("c", "g.bin", b"x" * (sm.MAX_ARQUIVO + 1))
        self.assertFalse(ok)
        self.assertIn("20 MB", msg)

    def test_global_ok_salva_e_publica(self):
        definir_eu("alice")
        blob = b"conteudo"
        ok, _ = sm.publicar_arquivo_global("legenda", "f.txt", blob)
        self.assertTrue(ok)
        ev = sm.historico[-1]
        self.assertEqual(ev["tipo"], "file")
        self.assertEqual(sm.ler_bytes_arquivo(ev["mid"]), blob)

    def test_dm_arquivo_maior_que_20mb_rejeita(self):
        definir_eu("alice")
        definir_par("bob", presente=True)
        ok, msg = sm.enviar_dm_arquivo("@bob", "c", "g.bin",
                                       b"x" * (sm.MAX_ARQUIVO + 1))
        self.assertFalse(ok)
        self.assertIn("20 MB", msg)


if __name__ == "__main__":
    unittest.main()
