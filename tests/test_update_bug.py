"""Defeitos do updater: flag presa + pacote parcial. Escritos ANTES da
correção (TDD red→green); só cobrem caminhos sem os._exit(42)."""
import hashlib
import os
import unittest
from unittest import mock

import senderme as sm
from suporte import CasoIsolado, definir_eu


def _manifest_2arq():
    b1, b2 = b"conteudo-novo-1", b"conteudo-novo-2"
    return ({"v": "99.0", "arquivos": [
        {"nome": "senderme.py", "tamanho": len(b1),
         "sha256": hashlib.sha256(b1).hexdigest()},
        {"nome": "config.py", "tamanho": len(b2),
         "sha256": hashlib.sha256(b2).hexdigest()}]}, b1, b2)


class FlagPresa(CasoIsolado):
    def test_finalizar_incompleto_libera_atualizando(self):
        definir_eu("alice")
        manif, _, _ = _manifest_2arq()
        sm.update_manifest = manif
        sm.atualizando = True
        sm.update_montando.clear()
        sm.finalizar_update()
        self.assertFalse(sm.atualizando)

    def test_erro_de_gravacao_libera_atualizando_e_reverte(self):
        definir_eu("alice")
        manif, b1, b2 = _manifest_2arq()
        for nome, blob in (("senderme.py", b"velho-1"), ("config.py", b"velho-2")):
            with open(os.path.join(self._tmp.name, nome), "wb") as f:
                f.write(blob)
        sm.update_manifest = manif
        sm.update_envelope = {"manifest": manif, "sig": "x"}
        sm.atualizando = True
        sm.update_montando["senderme.py"] = {"total": 1, "partes": {0: b1},
                                             "ts": sm.agora()}
        sm.update_montando["config.py"] = {"total": 1, "partes": {0: b2},
                                           "ts": sm.agora()}
        real_replace = os.replace

        def falhar_2a(src, dst, *a, **k):
            falhar_2a.n += 1
            if falhar_2a.n == 2:
                raise OSError("disco cheio (simulado)")
            return real_replace(src, dst, *a, **k)
        falhar_2a.n = 0
        with mock.patch("os.replace", side_effect=falhar_2a):
            sm.finalizar_update()
        self.assertFalse(sm.atualizando)
        with open(os.path.join(self._tmp.name, "senderme.py"), "rb") as f:
            self.assertEqual(f.read(), b"velho-1")
        with open(os.path.join(self._tmp.name, "config.py"), "rb") as f:
            self.assertEqual(f.read(), b"velho-2")


if __name__ == "__main__":
    unittest.main()
