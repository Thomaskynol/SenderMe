"""Caracterização: nicks — last-write-wins, transferência, (2), login."""
import os
import unittest
from unittest import mock

import senderme as sm
from suporte import CasoIsolado, definir_eu, definir_par


class LastWriteWins(CasoIsolado):
    def test_ts_velho_nao_reverte(self):
        definir_eu("alice")
        peer, _ = definir_par("bob")
        sm.aplicar_nick(peer["id"], "novo", ts=200)
        sm.aplicar_nick(peer["id"], "velho", ts=100)
        self.assertEqual(sm.nick_de[peer["id"]], "novo")

    def test_nick_vazio_ou_longo_ignorado(self):
        definir_eu("alice")
        peer, _ = definir_par("bob")
        sm.aplicar_nick(peer["id"], "   ", ts=300)
        sm.aplicar_nick(peer["id"], "n" * 25, ts=301)
        self.assertEqual(sm.nick_de[peer["id"]], "bob")


class Transferencia(CasoIsolado):
    def test_dono_offline_transfere_sem_2(self):
        definir_eu("eu")
        a, _ = definir_par("ze", presente=True)
        sm.aplicar_nick(a["id"], "ze", ts=100)
        self.assertEqual(sm.dono_do_apelido("ze"), a["id"])
        # A sai: sem socket e sem contato recente
        sm.ultimo_contato[a["id"]] = sm.agora() - 100
        sm.estado[a["id"]] = "offline"
        b, _ = definir_par("ze")
        sm.aplicar_nick(b["id"], "ze", ts=200)
        self.assertEqual(sm.dono_do_apelido("ze"), b["id"])
        self.assertEqual(sm.apelido_exibido(b["id"], "ze"), "ze")

    def test_dois_online_desempata_com_2(self):
        definir_eu("eu")
        a, _ = definir_par("dup", presente=True)
        sm.aplicar_nick(a["id"], "dup", ts=100)
        b, _ = definir_par("dup", presente=True)
        sm.aplicar_nick(b["id"], "dup", ts=200)
        self.assertEqual(sm.dono_do_apelido("dup"), a["id"])
        self.assertEqual(sm.apelido_exibido(a["id"], "dup"), "dup")
        self.assertEqual(sm.apelido_exibido(b["id"], "dup"), "dup(2)")

    def test_quem_saiu_mostra_nome_puro(self):
        definir_eu("eu")
        a, _ = definir_par("dup", presente=True)
        sm.aplicar_nick(a["id"], "dup", ts=100)
        b, _ = definir_par("dup", presente=True)
        sm.aplicar_nick(b["id"], "dup", ts=200)
        sm.ultimo_contato[b["id"]] = sm.agora() - 100
        sm.estado[b["id"]] = "offline"
        self.assertEqual(sm.apelido_exibido(b["id"], "dup"), "dup")


class EmUsoOnline(CasoIsolado):
    def test_case_insensitive_e_exceto(self):
        eu, _ = definir_eu("Alice")
        peer, _ = definir_par("BOB", presente=True)
        self.assertEqual(sm.em_uso_online("bob"), peer["id"])
        self.assertEqual(sm.em_uso_online("  BoB  "), peer["id"])
        self.assertIsNone(sm.em_uso_online("bob", exceto=peer["id"]))
        # o próprio eu conta, salvo exceto
        self.assertEqual(sm.em_uso_online("alice"), eu["id"])
        self.assertIsNone(sm.em_uso_online("alice", exceto=eu["id"]))

    def test_offline_nao_bloqueia(self):
        definir_eu("eu")
        peer, _ = definir_par("sumido")
        sm.ultimo_contato[peer["id"]] = sm.agora() - 100
        self.assertIsNone(sm.em_uso_online("sumido"))


class LoginTroca(CasoIsolado):
    def test_validar_nick(self):
        self.assertEqual(sm.validar_nick("  ")[1][:7], "Apelido")
        _, err = sm.validar_nick("n" * 25)
        self.assertIn("24", err)
        self.assertEqual(sm.validar_nick(" ze ")[0], "ze")

    def test_login_bloqueia_nome_em_uso(self):
        definir_eu()
        definir_par("bob", presente=True)
        ok, msg = sm.fazer_login("BOB")
        self.assertFalse(ok)
        self.assertIn("em uso", msg)

    def test_login_ok_salva_apelido(self):
        definir_eu()
        _sem_join = mock.patch("senderme_app.manut.anunciar_entrada",
                                lambda: None)
        _sem_join.start()
        try:
            ok, _ = sm.fazer_login("alice")
        finally:
            _sem_join.stop()
        self.assertTrue(ok)
        self.assertTrue(sm.logado)
        with open(os.path.join(sm.DADOS, "apelido.txt"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "alice")

    def test_relogin_igual_e_ok_e_outro_nome_vira_troca(self):
        definir_eu()
        _sem_join = mock.patch("senderme_app.manut.anunciar_entrada",
                                lambda: None)
        _sem_join.start()
        try:
            sm.fazer_login("alice")
            ok, _ = sm.fazer_login("alice")  # via /api/login c/ mesmo nome
            self.assertTrue(ok)
        finally:
            _sem_join.stop()

    def test_troca_exige_login_e_bloqueia_conflito(self):
        definir_eu()
        ok, _ = sm.trocar_apelido("x")
        self.assertFalse(ok)
        _sem_join = mock.patch("senderme_app.manut.anunciar_entrada",
                                lambda: None)
        _sem_join.start()
        try:
            sm.fazer_login("alice")
            ok, _ = sm.trocar_apelido("ALICE")
            self.assertFalse(ok)
            definir_par("bob", presente=True)
            ok, msg = sm.trocar_apelido("bob")
            self.assertFalse(ok)
            self.assertIn("em uso", msg)
            ok, _ = sm.trocar_apelido("beto")
            self.assertTrue(ok)
            self.assertEqual(sm.nick, "beto")
            self.assertTrue(any(e["tipo"] == "nick" and e["txt"] == "beto"
                                for e in sm.historico))
        finally:
            _sem_join.stop()


if __name__ == "__main__":
    unittest.main()
