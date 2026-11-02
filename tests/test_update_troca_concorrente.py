"""TOCTOU na troca staged->destino: thread local concorrente troca um
diretório por symlink no instante exato da promoção (adaptado da sonda
`teste_update_troca_symlink.py` da revisão 1.8; o gancho casa por basename
para não depender do formato da chamada a `os.replace`).

Escopo honesto: alteração LOCAL concorrente com chave SINTÉTICA em tmp
(nunca dono/privada.json, nunca dados/ real). Exige capacidade de alterar
os diretórios da instalação durante o update + suporte a symlink. Não
demonstra ataque remoto, forja de assinatura nem ganho de privilégio.
Exigido DEPOIS da correção: arquivo externo intacto, erro detectado
(retorna False), journal preservado (marcador+backup p/ o boot) e mensagem
honesta (sem afirmar "revertida").
"""
import hashlib
import os
import shutil
import sys
import tempfile
import threading
import unittest
from unittest import mock

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "tests"))
sys.path.insert(0, RAIZ)

import suporte  # noqa: E402
import senderme as sm  # noqa: E402
import senderme_app.update as upd_mod  # noqa: E402
from suporte import CasoIsolado, definir_eu  # noqa: E402


def instalar_chave_sintetica(tc):
    chave = suporte.chave_teste()
    n_hex = format(chave["n"], "x")
    p = mock.patch.multiple("senderme_app.estado", CHAVE_DONO_N=n_hex,
                            CHAVE_DONO_E=65537)
    p.start()
    tc.addCleanup(p.stop)
    return chave


def assinar_release(chave, versao, arquivos):
    manifest = {"v": versao, "arquivos": [
        {"nome": n, "tamanho": len(b),
         "sha256": hashlib.sha256(b).hexdigest()}
        for n, b in sorted(arquivos.items())]}
    sig = sm.assinar(sm.manifest_canonico(manifest), chave).hex()
    return {"manifest": manifest, "sig": sig}, manifest


def gravar(pasta, nome, blob):
    p = os.path.join(pasta, nome)
    os.makedirs(os.path.dirname(p) or pasta, exist_ok=True)
    with open(p, "wb") as f:
        f.write(blob)


def ler(pasta, nome):
    with open(os.path.join(pasta, nome), "rb") as f:
        return f.read()


class TrocaConcorrenteLocal(CasoIsolado):
    def test_nao_grava_fora_apos_troca_concorrente(self):
        definir_eu("alice")
        chave = instalar_chave_sintetica(self)
        base = self._tmp.name
        fora = tempfile.mkdtemp(prefix="sm-race-fora-")
        self.addCleanup(shutil.rmtree, fora, True)
        os.makedirs(os.path.join(base, "docs"))
        gravar(base, "senderme.py", b"velho")
        gravar(base, "docs/02-arquitetura.md", b"dentro-velho")
        externo = os.path.join(fora, "02-arquitetura.md")
        with open(externo, "wb") as f:
            f.write(b"fora-original")
        with open(os.path.join(base, "update-manifest.json"), "w") as f:
            f.write('{"v": "old"}')
        conteudo = {"senderme.py": b"novo",
                    "docs/02-arquitetura.md": b"fora-modificado"}
        env, manif = assinar_release(chave, "99.0", conteudo)
        self.assertTrue(sm.conferir_manifest(
            manif, env["sig"]))
        sm.update_manifest = manif
        sm.update_envelope = env
        sm.atualizando = True
        for nome, blob in conteudo.items():
            sm.update_montando[nome] = {"total": 1, "partes": {0: blob},
                                        "ts": sm.agora()}
        pronto = threading.Event()
        terminou = threading.Event()
        erros = []

        def atacante():
            try:
                if not pronto.wait(10):
                    raise RuntimeError("ponto de troca não atingido")
                os.rename(os.path.join(base, "docs"),
                          os.path.join(base, "docs-originais"))
                os.symlink(fora, os.path.join(base, "docs"),
                           target_is_directory=True)
            except BaseException as exc:  # noqa: BLE001
                erros.append(repr(exc))
            finally:
                terminou.set()

        fio = threading.Thread(target=atacante, daemon=True)
        fio.start()
        real_replace = os.replace

        def replace_sincronizado(src, dst, *a, **k):
            alvos = (os.fspath(src), os.fspath(dst))
            if any("02-arquitetura.md" in t for t in alvos):
                pronto.set()
                if not terminou.wait(10):
                    raise RuntimeError("atacante não concluiu")
                if erros:
                    raise RuntimeError(str(erros))
            return real_replace(src, dst, *a, **k)

        logs = []
        with mock.patch("os.replace", side_effect=replace_sincronizado), \
                mock.patch.object(upd_mod, "log", lambda t: logs.append(t)):
            ok = sm.finalizar_update()
        fio.join(timeout=10)
        print("retorno_update=%r marcador=%r backup=%r"
              % (ok, os.path.exists(os.path.join(base, ".upd-pendente.json")),
                 os.path.isdir(os.path.join(base, ".upd-backup"))))
        self.assertTrue(pronto.is_set(),
                        "a promoção não chegou ao ponto instrumentado")
        self.assertFalse(erros, str(erros))
        with open(externo, "rb") as f:
            self.assertEqual(f.read(), b"fora-original",
                             "arquivo externo foi alterado; update=%r" % ok)
        # erro detectado + journal preservado p/ o boot (recuperação decide)
        self.assertFalse(ok)
        self.assertTrue(os.path.exists(
            os.path.join(base, ".upd-pendente.json")))
        self.assertTrue(os.path.isdir(os.path.join(base, ".upd-backup")))
        # rollback honesto: nada afirma reversão total de efeito externo
        texto = "\n".join(logs)
        self.assertNotIn("revertida", texto)
        self.assertIn("concorrente", texto)


if __name__ == "__main__":
    unittest.main()
