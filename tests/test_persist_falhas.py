"""R5/R7 — persistência: DM offline sem disco avisa; apelido sem disco avisa.

Só stdlib, dados sintéticos em tmp via CasoIsolado. Falhas de disco são
reais (historico.jsonl / apelido.txt como diretório -> open falha), sem
mocks de retorno."""
import os
import unittest
from unittest import mock

import senderme as sm
from suporte import CasoIsolado, FakeSock, definir_eu, definir_par, quadros


def _tornar_dir(caminho):
    if os.path.isfile(caminho):
        os.remove(caminho)
    os.makedirs(caminho, exist_ok=True)


class DMOfflinePersistencia(CasoIsolado):
    def setUp(self):
        super().setUp()
        definir_eu("alice")
        definir_par("bob", presente=True)

    def test_offline_falha_persist_nao_diz_guardada(self):
        _tornar_dir(os.path.join(sm.DADOS, "historico.jsonl"))
        ok, msg = sm.enviar_dm_para("@bob", "oi")
        self.assertFalse(ok)
        self.assertNotIn("guardada", msg)
        self.assertIn("AVISO", msg)
        self.assertIn("historico.jsonl", msg)
        self.assertEqual(len(sm.historico), 1)

    def test_offline_falha_persist_perdida_no_restart(self):
        _tornar_dir(os.path.join(sm.DADOS, "historico.jsonl"))
        sm.enviar_dm_para("@bob", "oi efemera")
        mid = sm.historico[0]["mid"]
        # restart: disco não tem o evento (só memória); remove o dir-bloqueio
        # e recarrega como o boot faria.
        os.rmdir(os.path.join(sm.DADOS, "historico.jsonl"))
        sm.historico[:] = []
        sm.vistos.clear()
        recarregados = sm.carregar_historico()
        self.assertEqual(recarregados, [])
        self.assertNotIn(mid, [e.get("mid") for e in sm.historico])

    def test_offline_sucesso_diz_guardada_e_sobrevive_restart(self):
        ok, msg = sm.enviar_dm_para("@bob", "oi salva")
        self.assertFalse(ok)
        self.assertIn("guardada", msg)
        self.assertTrue(os.path.isfile(os.path.join(sm.DADOS, "historico.jsonl")))
        mid = sm.historico[0]["mid"]
        sm.historico[:] = []
        sm.vistos.clear()
        recarregados = sm.carregar_historico()
        self.assertIn(mid, [e.get("mid") for e in recarregados])

    def test_online_falha_persist_entrega_mas_avisa(self):
        peer_id = [i for i in sm.conhecidos][0]
        sock = FakeSock()
        sm.conns[peer_id] = {sock}
        sm.sockets_vivos.add(sock)
        _tornar_dir(os.path.join(sm.DADOS, "historico.jsonl"))
        ok, msg = sm.enviar_dm_para("@bob", "oi direta")
        self.assertTrue(ok)
        self.assertIn("aviso", msg.lower())
        self.assertEqual(len(quadros(sock)), 1)  # entregue na rede
        self.assertFalse(os.path.isfile(
            os.path.join(sm.DADOS, "historico.jsonl")))


class ApelidoPersistencia(CasoIsolado):
    def test_login_falha_apelido_avisa_mas_loga(self):
        definir_eu()
        _tornar_dir(os.path.join(sm.DADOS, "apelido.txt"))
        with mock.patch("senderme_app.manut.anunciar_entrada", lambda: None):
            ok, msg = sm.fazer_login("alice")
        self.assertTrue(ok)
        self.assertIn("aviso", msg.lower())
        self.assertIn("apelido.txt", msg)
        self.assertTrue(sm.logado)
        self.assertEqual(sm.nick, "alice")

    def test_troca_apelido_falha_avisa(self):
        definir_eu()
        with mock.patch("senderme_app.manut.anunciar_entrada", lambda: None):
            sm.fazer_login("alice")
            os.remove(os.path.join(sm.DADOS, "apelido.txt"))
            _tornar_dir(os.path.join(sm.DADOS, "apelido.txt"))
            ok, msg = sm.trocar_apelido("beto")
        self.assertTrue(ok)
        self.assertIn("aviso", msg.lower())
        self.assertEqual(sm.nick, "beto")


if __name__ == "__main__":
    unittest.main()
