"""Caracterização: criação e validação de eventos (processar/conferir_evento)."""
import hashlib
import unittest

import senderme as sm
from suporte import (CasoIsolado, criar_como, definir_eu, definir_par,
                     reassinar)


def arq_ok(nome="a.txt", tamanho=3):
    return {"nome": nome, "tamanho": tamanho, "sha256": "ab" * 32}


class CriarEvento(CasoIsolado):
    def test_mid_e_sha256_do_campo_e_assina(self):
        eu, chave = definir_eu("alice")
        ev = sm.criar_evento("msg", "oi")
        campo = sm.campo_assinatura(ev).encode("utf-8")
        self.assertEqual(ev["mid"], hashlib.sha256(campo).hexdigest())
        self.assertTrue(sm.conferir_evento(ev))

    def test_texto_2000_no_envio_e_rejeita_8000_no_recebimento(self):
        # envio trunca em tratar_comando_web; aqui só o limite de validação:
        eu, chave = definir_eu("alice")
        ev = sm.criar_evento("msg", "x" * 2000)
        self.assertTrue(sm.processar(ev, disco=False))
        ev2 = sm.criar_evento("msg", "x" * 2000)
        ev2["txt"] = "y" * (sm.MAX_TEXTO * 4 + 1)
        reassinar(ev2, chave)  # re-assina p/ isolar a causa: só o tamanho barra
        self.assertFalse(sm.processar(ev2, disco=False))

    def test_file_mid_inclui_arq(self):
        definir_eu("alice")
        ev = sm.criar_evento_file("leg", "a.txt", 3, "ab" * 32)
        self.assertEqual(ev["arq"]["sha256"], "ab" * 32)
        self.assertTrue(sm.conferir_evento(ev))


class ConferirEvento(CasoIsolado):
    def test_sig_invalida_rejeita(self):
        definir_eu("alice")
        ev = sm.criar_evento("msg", "oi")
        ev["txt"] = "adulterado"
        self.assertFalse(sm.conferir_evento(ev))

    def test_mid_errado_rejeita(self):
        definir_eu("alice")
        ev = sm.criar_evento("msg", "oi")
        ev["mid"] = "00" * 32
        self.assertFalse(sm.conferir_evento(ev))

    def test_autor_desconhecido_retorna_none(self):
        definir_eu("alice")
        outro_idt, _ = definir_par_sem_registro()
        outro = criar_como(outro_idt, "mallory", "msg", "oi")
        self.assertIsNone(sm.conferir_evento(outro))

    def test_propria_chave_dispensa_conhecidos(self):
        definir_eu("alice")
        self.assertEqual(sm.conhecidos, {})
        self.assertTrue(sm.conferir_evento(sm.criar_evento("msg", "oi")))


def definir_par_sem_registro():
    from suporte import chave_teste, identidade_de
    chave = chave_teste()
    return identidade_de(chave), chave


class ProcessarValidacao(CasoIsolado):
    def setUp(self):
        super().setUp()
        self.eu, self.chave = definir_eu("alice")

    def test_tipo_desconhecido(self):
        ev = sm.criar_evento("msg", "oi")
        ev["tipo"] = "fax"
        reassinar(ev, self.chave)
        self.assertFalse(sm.processar(ev, disco=False))

    def test_campo_obrigatorio_ausente(self):
        ev = sm.criar_evento("msg", "oi")
        del ev["nonce"]
        self.assertFalse(sm.processar(ev, disco=False))

    def test_dm_sem_para_rejeita(self):
        ev = sm.criar_evento("msg", "oi")
        ev["tipo"] = "dm"
        reassinar(ev, self.chave)
        self.assertFalse(sm.processar(ev, disco=False))

    def test_file_sem_arq_rejeita(self):
        ev = sm.criar_evento("msg", "oi")
        ev["tipo"] = "file"
        reassinar(ev, self.chave)
        self.assertFalse(sm.processar(ev, disco=False))

    def test_file_tamanho_zero_e_maior_que_20mb(self):
        for tam in (0, sm.MAX_ARQUIVO + 1):
            ev = sm.criar_evento_file("c", "a.txt", 3, "ab" * 32)
            ev["arq"]["tamanho"] = tam
            reassinar(ev, self.chave)
            self.assertFalse(sm.processar(ev, disco=False), tam)

    def test_file_nome_com_barra_ou_invertida_ou_crlf_ou_longo(self):
        for nome in ("a/b.txt", "a\\b.txt", "a\nb.txt", "a\rb.txt", "n" * 121, ""):
            ev = sm.criar_evento_file("c", "ok.txt", 3, "ab" * 32)
            ev["arq"]["nome"] = nome  # sem re-sanitizar: retrata dado de peer
            reassinar(ev, self.chave)
            self.assertFalse(sm.processar(ev, disco=False), repr(nome))

    def test_file_sha_nao_hex_ou_tamanho_errado(self):
        for sha in ("zz" * 32, "abc"):
            ev = sm.criar_evento_file("c", "a.txt", 3, "ab" * 32)
            ev["arq"]["sha256"] = sha
            reassinar(ev, self.chave)
            self.assertFalse(sm.processar(ev, disco=False), repr(sha))

    def test_msg_valida_grava_uma_vez_e_deduplica(self):
        ev = sm.criar_evento("msg", "oi")
        self.assertTrue(sm.processar(ev, disco=False))
        self.assertIn(ev["mid"], sm.vistos)
        self.assertFalse(sm.processar(ev, disco=False))
        self.assertEqual(len(sm.historico), 1)

    def test_evento_velho_24h_descartado(self):
        ev = sm.criar_evento("msg", "oi")
        ev["ts"] = int(sm.agora()) - sm.RETENCAO - 10
        reassinar(ev, self.chave)
        self.assertFalse(sm.processar(ev, disco=False))
        self.assertIn(ev["mid"], sm.vistos)  # marca p/ não pedir de novo
        self.assertEqual(sm.historico, [])


if __name__ == "__main__":
    unittest.main()
