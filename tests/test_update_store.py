"""update_store: folha fd-pinned pura + re-exports (split 1.12, Desenho A).

Só tmp + stdlib; nunca dados/ nem dono/privada.json. O alvo SIGKILL do
teste de kill real (swap staged->destino em update.py) é âncora: se o
trecho sair de update.py, o teste de interrupção perde a janela.
"""
import os
import sys
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

FUNCOES = ["_fd_seguro_suportado", "_partes", "_abrir_base", "_abrir_pai",
           "_escrever_tudo", "_ler_rel", "_escrever_rel", "_substituir",
           "_remover_rel", "_podar_pais_vazios_fd"]

ALVO_SIGKILL = (b'            for nome in blobs:\n'
                b'                dest = os.path.join(S.PASTA, nome)\n'
                b'                _substituir(root_fd, ".upd-staging/" + nome,'
                b' nome)\n')


class FolhaPura(unittest.TestCase):
    def test_sem_import_de_estado_nem_pacote(self):
        src = open(os.path.join(RAIZ, "senderme_app", "update_store.py"),
                   encoding="utf-8").read()
        for linha in src.splitlines():
            s = linha.strip()
            if s.startswith("import ") or s.startswith("from "):
                self.assertNotIn("senderme", s, linha)
                self.assertNotIn("estado", s, linha)
                self.assertFalse(s.startswith("from ."), linha)

    def test_reexports_identicos_em_update(self):
        import senderme_app.update as upd
        import senderme_app.update_store as store
        for nome in FUNCOES:
            self.assertTrue(hasattr(upd, nome), nome)
            self.assertIs(getattr(upd, nome), getattr(store, nome), nome)

    def test_preboot_continua_autonomo(self):
        src = open(os.path.join(RAIZ, "senderme_app", "preboot.py"),
                   encoding="utf-8").read()
        self.assertNotIn("update_store", src)
        for linha in src.splitlines():
            s = linha.strip()
            if s.startswith("import ") or s.startswith("from "):
                self.assertNotIn("senderme", s, linha)
                self.assertFalse(s.startswith("from ."), linha)

    def test_alvo_sigkill_preservado_em_update(self):
        blob = open(os.path.join(RAIZ, "senderme_app", "update.py"),
                    "rb").read()
        self.assertIn(ALVO_SIGKILL, blob)

    def test_roundtrip_fd_em_tmp(self):
        import tempfile
        import senderme_app.update_store as store
        base = tempfile.mkdtemp(prefix="sm-store-")
        self.addCleanup(__import__("shutil").rmtree, base, True)
        root = store._abrir_base(base)
        try:
            store._escrever_rel(root, "sub/a.txt", b"ola")
            self.assertEqual(store._ler_rel(root, "sub/a.txt"), b"ola")
            store._escrever_rel(root, ".upd-staging/sub/a.txt", b"novo")
            store._substituir(root, ".upd-staging/sub/a.txt", "sub/a.txt")
            self.assertEqual(store._ler_rel(root, "sub/a.txt"), b"novo")
            store._remover_rel(root, "sub/a.txt")
            store._podar_pais_vazios_fd(root, "sub/a.txt")
            self.assertFalse(os.path.exists(os.path.join(base, "sub")))
        finally:
            try:
                os.close(root)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
