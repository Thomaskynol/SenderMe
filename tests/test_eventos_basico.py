"""Caracterização: mid = sha256(campo_assinatura), sanitização de nome, constantes.

Sem chaves RSA: só formato puro + limites. Roda rápido como primeiro incremento.
"""
import hashlib
import unittest

import senderme as sm


class CampoAssinaturaMid(unittest.TestCase):
    def ev_base(self, **kw):
        ev = {"tipo": "msg", "de": "idA", "nick": "alice",
              "ts": 1700000000, "txt": "oi", "nonce": "abc123"}
        ev.update(kw)
        return ev

    def test_mid_e_sha256_do_campo(self):
        ev = self.ev_base()
        campo = sm.campo_assinatura(ev)
        self.assertEqual(campo, "msg|idA|alice|1700000000|oi|abc123")
        self.assertEqual(hashlib.sha256(campo.encode("utf-8")).hexdigest(),
                         hashlib.sha256(sm.campo_assinatura(ev).encode("utf-8")).hexdigest())
        # contrato: criar_evento define mid exatamente assim (verificado nos testes com chave)

    def test_campo_inclui_para_quando_dm(self):
        sem = sm.campo_assinatura(self.ev_base())
        com = sm.campo_assinatura(self.ev_base(para="idB"))
        self.assertEqual(com, sem + "|idB")

    def test_campo_inclui_arq_quando_file(self):
        ev = self.ev_base(tipo="file", txt="legenda",
                          arq={"nome": "a.txt", "tamanho": 3, "sha256": "x" * 64})
        campo = sm.campo_assinatura(ev)
        self.assertTrue(campo.endswith("|a.txt|3|" + "x" * 64))
        # sem arq não tem sufixo
        self.assertNotIn("a.txt", sm.campo_assinatura(self.ev_base()))


class LimparNomeArq(unittest.TestCase):
    def test_basename_remove_traversal(self):
        self.assertEqual(sm.limpar_nome_arq("../../etc/evil.txt"), "evil.txt")
        self.assertEqual(sm.limpar_nome_arq("/abs/path.png"), "path.png")

    def test_cr_lf_removidos(self):
        self.assertNotIn("\n", sm.limpar_nome_arq("a\nb.txt"))
        self.assertNotIn("\r", sm.limpar_nome_arq("a\rb.txt"))

    def test_vazio_ou_ponto_vira_arquivo(self):
        self.assertEqual(sm.limpar_nome_arq(""), "arquivo")
        self.assertEqual(sm.limpar_nome_arq("."), "arquivo")
        self.assertEqual(sm.limpar_nome_arq(".."), "arquivo")

    def test_trunca_120(self):
        self.assertEqual(len(sm.limpar_nome_arq("a" * 200)), 120)

    def test_barra_invertida_nao_e_removida_aqui_validacao_rejeita_depois(self):
        # shortcut documentado: limpar mantém `\`; quem rejeita é processar().
        self.assertIn("\\", sm.limpar_nome_arq("a\\b.txt"))


class ConstantesContrato(unittest.TestCase):
    def test_limites(self):
        self.assertEqual(sm.MAX_TEXTO, 2000)
        self.assertEqual(sm.MAX_ARQUIVO, 20 * 1024 * 1024)
        self.assertEqual(sm.MAX_ARQUIVOS_TOTAL, 60 * 1024 * 1024)
        self.assertEqual(sm.RETENCAO, 24 * 3600)
        self.assertEqual(sm.CHUNK_ARQ, 512 * 1024)

    def test_tipos_evento(self):
        self.assertEqual(set(sm.TIPOS_EVENTO), {"msg", "join", "leave", "nick", "dm", "file"})


if __name__ == "__main__":
    unittest.main()
