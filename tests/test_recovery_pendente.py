"""B: com recuperação pendente, nova tentativa não apaga journal (TDD red→green).

Estratégia documentada (bloquear, não recuperar-por-cima): enquanto
.upd-pendente.json existir, `receber_update_meta` recusa nova oferta e
`finalizar_update` aborta sem tocar em staging/backup/marcador/arquivos.
O próximo boot (preboot + app.main, que recusa servir mistura) recupera o
estado velho coerente; só depois nova oferta é aceita. Falhas repetidas
preservam marcador+backup para nova recuperação.

Tudo em tmp com chave SINTÉTICA (nunca dono/privada.json, nunca dados/
real); falhas de I/O injetadas via mock; rede real coberta em
test_update_e2e_abc.py.
"""
import hashlib
import json
import os
import unittest
from unittest import mock

import senderme as sm
from suporte import CasoIsolado, definir_eu, chave_teste


def instalar_chave_sintetica(tc):
    chave = chave_teste()
    n_hex = format(chave["n"], "x")
    p = mock.patch.multiple("senderme_app.estado", CHAVE_DONO_N=n_hex,
                            CHAVE_DONO_E=65537)
    p.start()
    tc.addCleanup(p.stop)
    return chave


def envelope(conteudo, versao, chave):
    manifest = {"v": versao, "arquivos": [
        {"nome": n, "tamanho": len(b),
         "sha256": hashlib.sha256(b).hexdigest()}
        for n, b in sorted(conteudo.items())]}
    sig = sm.assinar(sm.manifest_canonico(manifest), chave).hex()
    return {"manifest": manifest, "sig": sig}


def gravar(pasta, nome, blob):
    p = os.path.join(pasta, nome)
    os.makedirs(os.path.dirname(p) or pasta, exist_ok=True)
    with open(p, "wb") as f:
        f.write(blob)


def ler(pasta, nome):
    with open(os.path.join(pasta, nome), "rb") as f:
        return f.read()


def armar_pendente(tmp, velhos, novos):
    """Simula update interrompido: disco misto + marcador + backup velho."""
    for nome, blob in velhos.items():
        gravar(tmp, nome, blob)
    gravar(tmp, "a.py", novos["a.py"])  # parte nova já promovida
    bkp = os.path.join(tmp, ".upd-backup")
    for nome, blob in velhos.items():
        p = os.path.join(bkp, nome)
        os.makedirs(os.path.dirname(p) or bkp, exist_ok=True)
        with open(p, "wb") as f:
            f.write(blob)
    with open(os.path.join(tmp, ".upd-pendente.json"), "w",
              encoding="utf-8") as f:
        json.dump({"v": "99.0", "arquivos": sorted(velhos),
                   "novos": [], "tinha_manifesto": False}, f)


class BloqueioComPendente(CasoIsolado):
    def test_receber_recusa_nova_oferta_com_recuperacao_pendente(self):
        definir_eu("alice")
        chave = instalar_chave_sintetica(self)
        tmp = self._tmp.name
        velhos = {"a.py": b"OLD-A", "b.py": b"OLD-B"}
        novos = {"a.py": b"NEW-A", "b.py": b"NEW-B"}
        armar_pendente(tmp, velhos, novos)
        env = envelope(novos, "99.0", chave)
        with mock.patch("senderme_app.update.baixar_update") as dl:
            sm.receber_update_meta(env)  # mesmo peer, mesma versão
            sm.receber_update_meta(envelope(novos, "100.0", chave))  # outro
            dl.assert_not_called()
        self.assertFalse(sm.atualizando)
        self.assertIsNone(sm.update_manifest)
        # journal intacto para o boot recuperar
        self.assertTrue(os.path.exists(
            os.path.join(tmp, ".upd-pendente.json")))
        self.assertEqual(ler(os.path.join(tmp, ".upd-backup"), "a.py"),
                         b"OLD-A")
        self.assertEqual(ler(tmp, "a.py"), b"NEW-A")
        self.assertEqual(ler(tmp, "b.py"), b"OLD-B")

    def test_finalizar_com_pendente_aborta_preservando_journal(self):
        definir_eu("alice")
        chave = instalar_chave_sintetica(self)
        tmp = self._tmp.name
        velhos = {"a.py": b"OLD-A", "b.py": b"OLD-B"}
        novos = {"a.py": b"NEW-A", "b.py": b"NEW-B"}
        armar_pendente(tmp, velhos, novos)
        env = envelope(novos, "99.0", chave)
        sm.update_manifest = env["manifest"]
        sm.update_envelope = env
        sm.atualizando = True
        for nome, blob in novos.items():
            sm.update_montando[nome] = {"total": 1, "partes": {0: blob},
                                        "ts": sm.agora()}
        self.assertFalse(sm.finalizar_update())
        self.assertTrue(os.path.exists(
            os.path.join(tmp, ".upd-pendente.json")))
        self.assertTrue(os.path.isdir(os.path.join(tmp, ".upd-backup")))
        self.assertEqual(ler(os.path.join(tmp, ".upd-backup"), "a.py"),
                         b"OLD-A")
        # mistura preservada p/ o boot desfazer (nada fingido de limpo)
        self.assertEqual(ler(tmp, "a.py"), b"NEW-A")
        self.assertEqual(ler(tmp, "b.py"), b"OLD-B")

    def test_falhas_repetidas_preservam_journal_para_novo_boot(self):
        """2ª falha (no backup) não pode apagar marcador+backup da 1ª."""
        definir_eu("alice")
        chave = instalar_chave_sintetica(self)
        tmp = self._tmp.name
        velhos = {"a.py": b"OLD-A", "b.py": b"OLD-B"}
        novos = {"a.py": b"NEW-A", "b.py": b"NEW-B"}
        armar_pendente(tmp, velhos, novos)
        env = envelope(novos, "99.0", chave)
        sm.update_manifest = env["manifest"]
        sm.update_envelope = env
        sm.atualizando = True
        for nome, blob in novos.items():
            sm.update_montando[nome] = {"total": 1, "partes": {0: blob},
                                        "ts": sm.agora()}
        real_open = open

        def falhar_backup(path, *a, **k):
            modo = a[0] if a else k.get("mode", "r")
            if isinstance(path, str) and path.endswith(
                    os.path.join(".upd-backup", "a.py")) and "w" in modo:
                raise OSError("falha no retry (simulada)")
            return real_open(path, *a, **k)

        with mock.patch("builtins.open", side_effect=falhar_backup):
            self.assertFalse(sm.finalizar_update())
        self.assertTrue(os.path.exists(
            os.path.join(tmp, ".upd-pendente.json")))
        self.assertEqual(ler(os.path.join(tmp, ".upd-backup"), "a.py"),
                         b"OLD-A")

    def test_depois_da_recuperacao_total_nova_oferta_aceita(self):
        definir_eu("alice")
        chave = instalar_chave_sintetica(self)
        tmp = self._tmp.name
        velhos = {"a.py": b"OLD-A", "b.py": b"OLD-B"}
        novos = {"a.py": b"NEW-A", "b.py": b"NEW-B"}
        armar_pendente(tmp, velhos, novos)
        self.assertTrue(sm.recuperar_update())
        self.assertFalse(os.path.exists(
            os.path.join(tmp, ".upd-pendente.json")))
        self.assertEqual(ler(tmp, "a.py"), b"OLD-A")
        env = envelope(novos, "99.0", chave)
        with mock.patch("senderme_app.update.baixar_update", lambda: None):
            sm.receber_update_meta(env)
        self.assertTrue(sm.atualizando)
        self.assertEqual(sm.update_manifest["v"], "99.0")


if __name__ == "__main__":
    unittest.main()
