"""Caracterização: RSA própria, fingerprint, assinar/conferir."""
import unittest

import senderme as sm
from suporte import CasoIsolado, chave_teste, identidade_de


class Fingerprint(CasoIsolado):
    def test_formato_40_hex(self):
        idt = identidade_de(chave_teste())
        self.assertRegex(idt["id"], r"^[0-9a-f]{40}$")

    def test_estavel_e_sensivel_a_chave(self):
        c1, c2 = chave_teste(), chave_teste()
        self.assertEqual(sm.fingerprint(c1["n"], c1["e"]),
                         sm.fingerprint(c1["n"], c1["e"]))
        self.assertNotEqual(sm.fingerprint(c1["n"], c1["e"]),
                            sm.fingerprint(c2["n"], c2["e"]))


class AssinarConferir(CasoIsolado):
    def test_roundtrip(self):
        c = chave_teste()
        dados = "campo|de|teste".encode("utf-8")
        sig = sm.assinar(dados, c)
        self.assertTrue(sm.conferir(dados, sig, c["n"], c["e"]))

    def test_dado_adulterado_falha(self):
        c = chave_teste()
        sig = sm.assinar(b"original", c)
        self.assertFalse(sm.conferir(b"adulterado", sig, c["n"], c["e"]))

    def test_assinatura_adulterada_falha(self):
        c = chave_teste()
        sig = bytearray(sm.assinar(b"dado", c))
        sig[-1] ^= 0x01
        self.assertFalse(sm.conferir(b"dado", bytes(sig), c["n"], c["e"]))

    def test_chave_errada_falha(self):
        c1, c2 = chave_teste(), chave_teste()
        sig = sm.assinar(b"dado", c1)
        self.assertFalse(sm.conferir(b"dado", sig, c2["n"], c2["e"]))

    def test_tamanho_errado_falha(self):
        c = chave_teste()
        self.assertFalse(sm.conferir(b"dado", b"curta", c["n"], c["e"]))


if __name__ == "__main__":
    unittest.main()
