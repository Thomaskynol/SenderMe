"""R1: release que adiciona módulo + muda launcher reinicia sozinha (Lane U).

Cenário preservado da sonda (vermelho na 1.6, verde após o fix): fixtures
9.8->9.9 onde a 9.9 acrescenta senderme_app/modulo_futuro.py ao manifesto,
ao start.sh e ao import do app. O launcher VELHO (já com re-exec do
start.sh do disco + cópia robusta) deve aplicar e servir 9.9 sem
intervenção; na 1.6 genuína (RUNTIME fixo + `continue`) isso morria com
ImportError — caminho manual documentado em docs/04-migracao.md.

Só instalações/chaves/identidades sintéticas em tmp; portas via bind; stub
xdg-open; nunca dados/ nem dono/privada.json; só stdlib.
"""
import hashlib
import os
import shutil
import sys
import tempfile
import time
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "tests"))
sys.path.insert(0, RAIZ)

import suporte  # noqa: E402
from test_update_e2e_abc import montar_conteudo, escrever_instalacao, Processo  # noqa: E402
import senderme_app.update as upd  # noqa: E402
from crypto import assinar as crypto_assinar  # noqa: E402

_bin = tempfile.TemporaryDirectory(prefix="sm-modulo-bin-")
_xdg = os.path.join(_bin.name, "xdg-open")
with open(_xdg, "w") as f:
    f.write("#!/bin/sh\nexit 0\n")
os.chmod(_xdg, 0o700)
os.environ["PATH"] = _bin.name + os.pathsep + os.environ["PATH"]
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"


def envelope(conteudo, versao, chave):
    manifest = {"v": versao, "arquivos": [
        {"nome": n, "tamanho": len(conteudo[n]),
         "sha256": hashlib.sha256(conteudo[n]).hexdigest()}
        for n in sorted(conteudo)]}
    sig = crypto_assinar(upd.manifest_canonico(manifest), chave).hex()
    return {"manifest": manifest, "sig": sig}


class ModuloNovoReiniciaSozinho(unittest.TestCase):
    def test_release_com_modulo_novo_aplica_e_serve_sem_intervencao(self):
        chave = suporte.chave_teste()
        velho = montar_conteudo("9.8", chave)
        novo = montar_conteudo("9.9", chave)
        # release nova plausível: módulo no manifesto, no launcher e no app.
        meta_antiga = novo["senderme_app/meta.py"]
        novo["senderme_app/meta.py"] = meta_antiga.replace(
            b'"senderme_app/update_proto.py"]',
            b'"senderme_app/update_proto.py", "senderme_app/modulo_futuro.py"]')
        assert novo["senderme_app/meta.py"] != meta_antiga
        sh_antigo = novo["start.sh"]
        novo["start.sh"] = sh_antigo.replace(
            b'senderme_app/preboot.py"',
            b'senderme_app/preboot.py senderme_app/modulo_futuro.py"')
        assert novo["start.sh"] != sh_antigo
        app_antigo = novo["senderme_app/app.py"]
        novo["senderme_app/app.py"] = app_antigo.replace(
            b"from . import estado as S",
            b"from . import modulo_futuro\nfrom . import estado as S", 1)
        assert novo["senderme_app/app.py"] != app_antigo
        novo["senderme_app/modulo_futuro.py"] = b"MARCADOR_TESTE = True\n"
        inst_a = escrever_instalacao(novo, envelope(novo, "9.9", chave),
                                     "peer-a")
        self.addCleanup(shutil.rmtree, inst_a, True)
        inst_b = escrever_instalacao(velho, envelope(velho, "9.8", chave),
                                     "peer-b")
        self.addCleanup(shutil.rmtree, inst_b, True)
        a = Processo(self, inst_a, "peer-a")
        b = Processo(self, inst_b, "peer-b",
                     fixos="127.0.0.1:%d" % a.tcp)
        self.assertEqual(a.esperar_eu("peer-a")["versao"], "9.9")
        self.assertEqual(b.esperar_eu("peer-b")["versao"], "9.8")
        eu = b.esperar_versao("9.9", limite=120)
        self.assertEqual(eu["versao"], "9.9")
        self.assertIsNone(b.proc.poll())
        self.assertIn("aplicado, reiniciando", b.cauda())
        with open(os.path.join(inst_b, "senderme_app", "modulo_futuro.py"),
                  "rb") as f:
            self.assertEqual(f.read(), b"MARCADOR_TESTE = True\n")


if __name__ == "__main__":
    unittest.main()
