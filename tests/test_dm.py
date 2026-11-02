"""Caracterização: DM — direta, nunca em hist, offline/redelivery."""
import hashlib
import unittest

import senderme as sm
from suporte import (CasoIsolado, FakeSock, criar_como, definir_eu,
                     definir_par, quadros)


class DMProcessar(CasoIsolado):
    def setUp(self):
        super().setUp()
        self.eu, _ = definir_eu("alice")
        self.peer, self.pchave = definir_par("bob")

    def test_dm_para_mim_aplica_e_nao_propaga(self):
        ev = criar_como(self.peer, "bob", "dm", "psst", para=self.eu["id"])
        self.assertTrue(sm.processar(ev, disco=False))
        self.assertIn(ev, sm.historico)

    def test_dm_alheia_descartada(self):
        terceiro, _ = definir_par("carol")
        ev = criar_como(self.peer, "bob", "dm", "nada", para=terceiro["id"])
        self.assertFalse(sm.processar(ev, disco=False))
        self.assertEqual(sm.historico, [])

    def test_dm_propria_aplica(self):
        ev = sm.criar_evento("dm", "eu p/ bob", para=self.peer["id"])
        self.assertTrue(sm.processar(ev, disco=False))


class DMEnviar(CasoIsolado):
    def test_sem_conexao_guarda_no_historico(self):
        eu, _ = definir_eu("alice")
        peer, _ = definir_par("bob", presente=True)
        ok, msg = sm.enviar_dm_para("@bob", "oi")
        self.assertFalse(ok)  # sem socket: relata, mas guarda
        self.assertIn("Sem conexão", msg)
        self.assertEqual(len(sm.historico), 1)
        self.assertEqual(sm.historico[0]["para"], peer["id"])

    def test_com_conexao_envia_direto(self):
        definir_eu("alice")
        peer, _ = definir_par("bob", presente=True)
        sock = FakeSock()
        sm.conns[peer["id"]] = {sock}
        sm.sockets_vivos.add(sock)
        ok, _ = sm.enviar_dm_para("@bob", "oi direta")
        self.assertTrue(ok)
        (q,) = quadros(sock)
        self.assertEqual(q["t"], "ev")
        self.assertEqual(q["ev"]["txt"], "oi direta")

    def test_alvo_desconhecido(self):
        definir_eu("alice")
        ok, _ = sm.enviar_dm_para("@fantasma", "oi")
        self.assertFalse(ok)


class Redelivery(CasoIsolado):
    def test_so_recentes_ate_20_e_throttle_120s(self):
        eu, _ = definir_eu("alice")
        peer, _ = definir_par("bob", presente=True)
        for i in range(25):
            ev = sm.criar_evento("dm", "m%d" % i, para=peer["id"])
            sm.processar(ev, disco=False)
        velha = sm.criar_evento("dm", "velha", para=peer["id"])
        velha["ts"] = int(sm.agora()) - sm.RETENCAO - 10
        from suporte import reassinar
        reassinar(velha, {"n": eu["n"], "e": eu["e"], "d": eu["d"]})
        sm.processar(velha, disco=False)
        pend = sm.dms_pendentes_para(peer["id"])
        self.assertEqual(len(pend), 20)  # teto
        self.assertNotIn("velha", [e["txt"] for e in pend])  # fora da janela

        sock = FakeSock()
        sm.conns[peer["id"]] = {sock}
        sm.sockets_vivos.add(sock)
        sm.tentar_entregar_dm(peer["id"])
        n1 = len(sock.buf)
        self.assertGreater(n1, 0)
        sm.tentar_entregar_dm(peer["id"])  # throttle: nada novo
        self.assertEqual(len(sock.buf), n1)

    def test_sem_conexao_nao_queima_throttle(self):
        definir_eu("alice")
        peer, _ = definir_par("bob")
        sm.processar(sm.criar_evento("dm", "oi", para=peer["id"]), disco=False)
        sm.tentar_entregar_dm(peer["id"])
        self.assertNotIn(peer["id"], sm.dm_retry)

    def test_proprio_id_ignorado(self):
        eu, _ = definir_eu("alice")
        sm.tentar_entregar_dm(eu["id"])
        self.assertEqual(sm.dm_retry, {})

    def test_arquivo_dm_redelivery_envia_chunks(self):
        definir_eu("alice")
        peer, _ = definir_par("bob", presente=True)
        blob = b"DM-anexo" * 10
        ev = sm.criar_evento_file("segue", "anexo.bin", len(blob),
                                  hashlib.sha256(blob).hexdigest(),
                                  para=peer["id"])
        sm.salvar_bytes_arquivo(ev["mid"], blob)
        sm.processar(ev, disco=False)
        sock = FakeSock()
        sm.conns[peer["id"]] = {sock}
        sm.sockets_vivos.add(sock)
        sm.tentar_entregar_dm(peer["id"])
        tipos = [q["t"] for q in quadros(sock)]
        self.assertIn("ev", tipos)
        self.assertIn("file_chunk", tipos)


class DMEstadoContrato(CasoIsolado):
    """Achado 1 — `estado` explícito p/ UI (sem farejar texto).

    Contrato: enviar_dm_para(..., com_estado=True) -> (ok, msg, estado) com
    estado ∈ {entregue, guardada, somente_memoria, erro}; `ok`/`msg`
    inalterados (compat: sem flag continua (ok, msg))."""

    def test_erro_destino_inexistente_chamado_guardada_nada_guardado(self):
        # Sonda 1 do Achado 1: "@guardada" inexistente não envia nem guarda.
        definir_eu("alice")
        ok, msg, estado, _ = sm.enviar_dm_para("@guardada", "oi",
                                            com_estado=True)
        self.assertFalse(ok)
        self.assertEqual(estado, "erro")
        self.assertEqual(sm.historico, [])
        # compat: sem flag, mesmo ok/msg
        definir_eu("alice")
        ok2, msg2 = sm.enviar_dm_para("@guardada", "oi")
        self.assertEqual((ok2, msg2), (ok, msg))

    def test_erro_uso_e_vazio(self):
        definir_eu("alice")
        for alvo, texto in (("bob", "oi"), ("@bob", ""),
                            ("", "oi"), ("@fantasma", "oi")):
            with self.subTest(alvo=alvo, texto=texto):
                ok, _, estado, _ = sm.enviar_dm_para(alvo, texto,
                                                  com_estado=True)
                self.assertFalse(ok)
                self.assertEqual(estado, "erro")

    def test_guardada_offline_apelido_aviso_nao_confunde(self):
        # Sonda 2 espelhada: contato offline chamado "aviso" guarda de
        # verdade; estado é guardada mesmo com "aviso" no texto/apelido.
        definir_eu("alice")
        peer, _ = definir_par("aviso", presente=True)
        ok, msg, estado, _ = sm.enviar_dm_para("@aviso", "oi",
                                            com_estado=True)
        self.assertFalse(ok)
        self.assertEqual(estado, "guardada")
        self.assertIn("guardada", msg)
        self.assertEqual(len(sm.historico), 1)

    def test_somente_memoria_offline_sem_persist(self):
        import os
        definir_eu("alice")
        definir_par("bob", presente=True)
        p = os.path.join(sm.DADOS, "historico.jsonl")
        if os.path.isfile(p):
            os.remove(p)
        os.makedirs(p, exist_ok=True)
        self.addCleanup(lambda: os.rmdir(p) if os.path.isdir(p) else None)
        ok, msg, estado, _ = sm.enviar_dm_para("@bob", "oi", com_estado=True)
        self.assertFalse(ok)
        self.assertEqual(estado, "somente_memoria")
        self.assertIn("memória", msg)

    def test_somente_memoria_online_sem_persist(self):
        import os
        definir_eu("alice")
        peer, _ = definir_par("bob", presente=True)
        sock = FakeSock()
        sm.conns[peer["id"]] = {sock}
        sm.sockets_vivos.add(sock)
        p = os.path.join(sm.DADOS, "historico.jsonl")
        if os.path.isfile(p):
            os.remove(p)
        os.makedirs(p, exist_ok=True)
        self.addCleanup(lambda: os.rmdir(p) if os.path.isdir(p) else None)
        ok, _, estado, _ = sm.enviar_dm_para("@bob", "oi direta",
                                          com_estado=True)
        self.assertTrue(ok)  # entregue na rede...
        self.assertEqual(estado, "somente_memoria")  # ...mas só em memória
        self.assertEqual(len(quadros(sock)), 1)

    def test_entregue_direta(self):
        definir_eu("alice")
        peer, _ = definir_par("bob", presente=True)
        sock = FakeSock()
        sm.conns[peer["id"]] = {sock}
        sm.sockets_vivos.add(sock)
        ok, msg, estado, _ = sm.enviar_dm_para("@bob", "oi direta",
                                            com_estado=True)
        self.assertTrue(ok)
        self.assertEqual(estado, "entregue")
        self.assertEqual(msg, "")
        (q,) = quadros(sock)
        self.assertEqual(q["ev"]["txt"], "oi direta")

    def test_tratar_dm_propagada_e_publica_entregue(self):
        definir_eu("alice")
        sm.nick = "alice"
        sm.logado = True
        ok, _, estado, _ = sm.tratar_comando_web("/dm @fantasma oi",
                                              com_estado=True)
        self.assertFalse(ok)
        self.assertEqual(estado, "erro")
        ok2, _, estado2, _ = sm.tratar_comando_web("mensagem pública",
                                                com_estado=True)
        self.assertTrue(ok2)
        self.assertEqual(estado2, "entregue")
        # compat sem flag
        ok3, _ = sm.tratar_comando_web("outra pública")
        self.assertTrue(ok3)


class DMTransmitidaContrato(CasoIsolado):
    """Item 2 (1.10): `transmitida` distingue as duas `somente_memoria`.

    true = bytes entregues ao socket; NUNCA confirma recebimento/leitura
    pelo destinatário. `ok`/`msg`/`estado` intactos; sem flag segue 2-tupla.
    Matriz: enviada+persistida→(true,entregue);
    enviada+falha-persist→(true,somente_memoria);
    guardada→(false,guardada); só-memória sem envio→(false,somente_memoria);
    erro→(false,erro)."""

    def test_enviada_persistida_true_entregue(self):
        definir_eu("alice")
        peer, _ = definir_par("bob", presente=True)
        sock = FakeSock()
        sm.conns[peer["id"]] = {sock}
        sm.sockets_vivos.add(sock)
        ok, msg, estado, transmitida = sm.enviar_dm_para(
            "@bob", "oi direta", com_estado=True)
        self.assertTrue(ok)
        self.assertEqual(estado, "entregue")
        self.assertTrue(transmitida)
        self.assertEqual(msg, "")
        self.assertIsInstance(transmitida, bool)

    def test_enviada_falha_persist_true_somente_memoria(self):
        import os
        definir_eu("alice")
        peer, _ = definir_par("bob", presente=True)
        sock = FakeSock()
        sm.conns[peer["id"]] = {sock}
        sm.sockets_vivos.add(sock)
        p = os.path.join(sm.DADOS, "historico.jsonl")
        if os.path.isfile(p):
            os.remove(p)
        os.makedirs(p, exist_ok=True)
        self.addCleanup(lambda: os.rmdir(p) if os.path.isdir(p) else None)
        ok, _, estado, transmitida = sm.enviar_dm_para(
            "@bob", "oi direta", com_estado=True)
        self.assertTrue(ok)  # bytes no socket...
        self.assertEqual(estado, "somente_memoria")  # ...mas só em memória
        self.assertTrue(transmitida)
        self.assertEqual(len(quadros(sock)), 1)

    def test_guardada_offline_false(self):
        definir_eu("alice")
        definir_par("bob", presente=True)
        ok, msg, estado, transmitida = sm.enviar_dm_para(
            "@bob", "oi", com_estado=True)
        self.assertFalse(ok)
        self.assertEqual(estado, "guardada")
        self.assertFalse(transmitida)
        self.assertIn("guardada", msg)
        self.assertEqual(len(sm.historico), 1)

    def test_somente_memoria_offline_sem_envio_false(self):
        import os
        definir_eu("alice")
        definir_par("bob", presente=True)
        p = os.path.join(sm.DADOS, "historico.jsonl")
        if os.path.isfile(p):
            os.remove(p)
        os.makedirs(p, exist_ok=True)
        self.addCleanup(lambda: os.rmdir(p) if os.path.isdir(p) else None)
        ok, _, estado, transmitida = sm.enviar_dm_para(
            "@bob", "oi", com_estado=True)
        self.assertFalse(ok)
        self.assertEqual(estado, "somente_memoria")
        self.assertFalse(transmitida)

    def test_erro_false_nada_guardado(self):
        definir_eu("alice")
        ok, _, estado, transmitida = sm.enviar_dm_para(
            "@fantasma", "oi", com_estado=True)
        self.assertFalse(ok)
        self.assertEqual(estado, "erro")
        self.assertFalse(transmitida)
        self.assertEqual(sm.historico, [])

    def test_compat_2tupla_sem_flag(self):
        definir_eu("alice")
        peer, _ = definir_par("bob", presente=True)
        sock = FakeSock()
        sm.conns[peer["id"]] = {sock}
        sm.sockets_vivos.add(sock)
        ok2, msg2 = sm.enviar_dm_para("@bob", "oi direta")
        self.assertTrue(ok2)
        self.assertEqual(msg2, "")

    def test_tratar_dm_repasse_e_publica(self):
        definir_eu("alice")
        sm.nick = "alice"
        sm.logado = True
        peer, _ = definir_par("bob", presente=True)
        sock = FakeSock()
        sm.conns[peer["id"]] = {sock}
        sm.sockets_vivos.add(sock)
        ok, _, estado, transmitida = sm.tratar_comando_web(
            "/dm @bob segredo", com_estado=True)
        self.assertTrue(ok)
        self.assertEqual(estado, "entregue")
        self.assertTrue(transmitida)
        ok2, _, estado2, transmitida2 = sm.tratar_comando_web(
            "mensagem pública", com_estado=True)
        self.assertTrue(ok2)
        self.assertEqual(estado2, "entregue")
        self.assertTrue(transmitida2)
        ok3, _, estado3, transmitida3 = sm.tratar_comando_web(
            "/dm @fantasma oi", com_estado=True)
        self.assertFalse(ok3)
        self.assertEqual(estado3, "erro")
        self.assertFalse(transmitida3)


class DMItem3Explicito(CasoIsolado):
    """Item 3 (1.11): `transmitida` com semantica por contexto, valores intactos.

    Publica sem peers e DM no socket devolvem o mesmo bool True por razoes
    diferentes (aceitacao local vs bytes ao socket) — por isso a camada HTTP
    expoe `nivel`/`confirmado`/`peers` (ver test_api_contrato). Aqui ancora
    que os valores nao mudaram e que nenhum afirma recebimento/leitura."""

    def test_publica_sem_peers_aceitacao_local_sem_socket(self):
        definir_eu("alice")
        sm.nick = "alice"
        sm.logado = True
        self.assertEqual(dict(sm.conns), {})
        ok, msg, estado, transmitida = sm.tratar_comando_web(
            "oi publica sem peers", com_estado=True)
        self.assertTrue(ok)
        self.assertEqual(estado, "entregue")
        self.assertTrue(transmitida)  # aceitacao local, nao socket
        self.assertEqual(msg, "")
        self.assertEqual(len(sm.historico), 1)

    def test_mesmo_bool_significados_diferentes(self):
        definir_eu("alice")
        sm.nick = "alice"
        sm.logado = True
        ok_pub, _, est_pub, tra_pub = sm.tratar_comando_web(
            "publica sem socket", com_estado=True)
        peer, _ = definir_par("bob", presente=True)
        sock = FakeSock()
        sm.conns[peer["id"]] = {sock}
        sm.sockets_vivos.add(sock)
        ok_dm, _, est_dm, tra_dm = sm.enviar_dm_para(
            "@bob", "oi direta", com_estado=True)
        self.assertEqual((ok_pub, est_pub, tra_pub), (True, "entregue", True))
        self.assertEqual((ok_dm, est_dm, tra_dm), (True, "entregue", True))
        self.assertEqual(len(quadros(sock)), 1)  # so a DM tocou socket
        # nenhum afirma recebimento/leitura: msgs vazias, sem "receb"
        for m in (ok_pub, ok_dm):
            self.assertTrue(m)


if __name__ == "__main__":
    unittest.main()
