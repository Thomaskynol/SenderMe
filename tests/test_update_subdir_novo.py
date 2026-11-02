"""C: release assinada que adiciona SUBDIRETÓRIO novo (TDD red→green).

Cobre o caso que o teste de módulo-novo não cobre: arquivo dentro de pasta
antes inexistente (`senderme_app/extra/...`). Exige: promoção cria pais no
destino, rollback remove arquivo novo E poda dirs vazios, recovery no boot
faz o mesmo, e o caminho P2P real entre instalações temporárias aplica e
boota a versão nova (pacote Python novo importável). Chave SINTÉTICA em tmp;
nunca dono/privada.json, nunca dados/ real.
"""
import hashlib
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "tests"))
sys.path.insert(0, RAIZ)

import suporte  # noqa: E402
import senderme as sm  # noqa: E402
from suporte import CasoIsolado, definir_eu  # noqa: E402

_bin = tempfile.TemporaryDirectory(prefix="sm-subdir-bin-")
_xdg = os.path.join(_bin.name, "xdg-open")
with open(_xdg, "w") as f:
    f.write("#!/bin/sh\nexit 0\n")
os.chmod(_xdg, 0o700)
os.environ["PATH"] = _bin.name + os.pathsep + os.environ["PATH"]
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"


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


def _via_fd(dir_fd, nome):
    """Caminho aproximado p/ filtros de mock (somente Linux): resolve o
    fd do diretório via /proc; sem dir_fd, devolve o nome como veio."""
    try:
        base = os.readlink("/proc/self/fd/%d" % (dir_fd,))
    except (OSError, TypeError):
        return os.fspath(nome)
    return base + "/" + os.fspath(nome)


NOVOS_SUBDIR = {"senderme.py": b"novo-1",
                "senderme_app/extra/__init__.py": b"# extra\n",
                "senderme_app/extra/modulo.py": b"SINTETICO = True\n"}


class PromocaoComSubdir(CasoIsolado):
    def test_aplica_arquivos_em_pasta_nova(self):
        definir_eu("alice")
        chave = instalar_chave_sintetica(self)
        gravar(self._tmp.name, "senderme.py", b"velho-1")
        env, manif = assinar_release(chave, "99.0", NOVOS_SUBDIR)
        sm.update_manifest = manif
        sm.update_envelope = env
        sm.atualizando = True
        for nome, blob in NOVOS_SUBDIR.items():
            sm.update_montando[nome] = {"total": 1, "partes": {0: blob},
                                        "ts": sm.agora()}
        self.assertTrue(sm.finalizar_update())
        for nome, blob in NOVOS_SUBDIR.items():
            self.assertEqual(ler(self._tmp.name, nome), blob, nome)
        self.assertFalse(os.path.exists(
            os.path.join(self._tmp.name, ".upd-pendente.json")))
        self.assertFalse(os.path.exists(
            os.path.join(self._tmp.name, ".upd-backup")))

    def test_falha_reverte_arquivo_novo_e_poda_pasta_vazia(self):
        definir_eu("alice")
        chave = instalar_chave_sintetica(self)
        gravar(self._tmp.name, "senderme.py", b"velho-1")
        env, manif = assinar_release(chave, "99.0", NOVOS_SUBDIR)
        sm.update_manifest = manif
        sm.update_envelope = env
        sm.atualizando = True
        for nome, blob in NOVOS_SUBDIR.items():
            sm.update_montando[nome] = {"total": 1, "partes": {0: blob},
                                        "ts": sm.agora()}
        real_replace = os.replace
        n = {"i": 0}

        def falhar_ultimo(src, dst, *a, **k):
            # conta só a troca staged->destino (tmp+replace termina em
            # .tmp); falha na última promoção p/ reverter arquivo novo.
            if isinstance(src, str) and not src.endswith(".tmp"):
                n["i"] += 1
                if n["i"] == len(NOVOS_SUBDIR):
                    raise OSError("disco cheio (simulado)")
            return real_replace(src, dst, *a, **k)

        with mock.patch("os.replace", side_effect=falhar_ultimo):
            self.assertFalse(sm.finalizar_update())
        self.assertFalse(sm.atualizando)
        self.assertEqual(ler(self._tmp.name, "senderme.py"), b"velho-1")
        self.assertFalse(os.path.exists(os.path.join(
            self._tmp.name, "senderme_app", "extra", "modulo.py")))
        self.assertFalse(os.path.exists(os.path.join(
            self._tmp.name, "senderme_app", "extra")))

    def test_recovery_remove_arquivo_novo_em_subdir(self):
        definir_eu("alice")
        chave = instalar_chave_sintetica(self)
        gravar(self._tmp.name, "senderme.py", b"velho-1")
        env, manif = assinar_release(chave, "99.0", NOVOS_SUBDIR)
        sm.update_manifest = manif
        sm.update_envelope = env
        sm.atualizando = True
        for nome, blob in NOVOS_SUBDIR.items():
            sm.update_montando[nome] = {"total": 1, "partes": {0: blob},
                                        "ts": sm.agora()}
        real_replace = os.replace

        def morrer_no_meio(src, dst, *a, **k):
            out = real_replace(src, dst, *a, **k)
            if os.fspath(dst).endswith("modulo.py") and "extra" in _via_fd(
                    k.get("dst_dir_fd"), dst):
                raise KeyboardInterrupt("kill simulado após pasta nova")
            return out

        with mock.patch("os.replace", side_effect=morrer_no_meio):
            with self.assertRaises(KeyboardInterrupt):
                sm.finalizar_update()
        sm.atualizando = False
        sm.update_manifest = None
        sm.update_envelope = None
        sm.update_montando.clear()
        self.assertTrue(sm.recuperar_update())
        self.assertEqual(ler(self._tmp.name, "senderme.py"), b"velho-1")
        self.assertFalse(os.path.exists(os.path.join(
            self._tmp.name, "senderme_app", "extra", "modulo.py")))
        self.assertFalse(os.path.exists(
            os.path.join(self._tmp.name, ".upd-pendente.json")))


class RedeComPacoteNovo(unittest.TestCase):
    """P2P real + launcher real + boot pós-reinício com subdir novo."""

    def test_rede_pacote_novo_aplica_e_boota(self):
        from test_update_e2e_abc import (montar_conteudo, escrever_instalacao,
                                         Processo)
        import senderme_app.update as upd
        from crypto import assinar as crypto_assinar

        def envelope(conteudo, versao, chave):
            m = {"v": versao, "arquivos": [
                {"nome": n, "tamanho": len(b),
                 "sha256": hashlib.sha256(b).hexdigest()}
                for n, b in sorted(conteudo.items())]}
            return {"manifest": m,
                    "sig": crypto_assinar(upd.manifest_canonico(m),
                                          chave).hex()}

        chave = suporte.chave_teste()
        antigo = montar_conteudo("9.8", chave)
        novo = montar_conteudo("9.9", chave)
        meta_antiga = novo["senderme_app/meta.py"]
        novo["senderme_app/meta.py"] = meta_antiga.replace(
            b'"senderme_app/update_proto.py"]',
            b'"senderme_app/update_proto.py", "senderme_app/extra/__init__.py",'
            b' "senderme_app/extra/modulo.py"]')
        self.assertNotEqual(novo["senderme_app/meta.py"], meta_antiga,
                            "ajuste a âncora da fixture (meta.py)")
        sh_antigo = novo["start.sh"]
        novo["start.sh"] = sh_antigo.replace(
            b'senderme_app/preboot.py"',
            b'senderme_app/preboot.py senderme_app/extra/__init__.py'
            b' senderme_app/extra/modulo.py"')
        self.assertNotEqual(novo["start.sh"], sh_antigo,
                            "ajuste a âncora da fixture (start.sh)")
        app_antigo = novo["senderme_app/app.py"]
        novo["senderme_app/app.py"] = app_antigo.replace(
            b"from . import estado as S",
            b"from .extra import modulo\nfrom . import estado as S", 1)
        self.assertNotEqual(novo["senderme_app/app.py"], app_antigo,
                            "ajuste a âncora da fixture (app.py)")
        novo["senderme_app/extra/__init__.py"] = b"# fixture\n"
        novo["senderme_app/extra/modulo.py"] = b"SINTETICO = True\n"
        ia = escrever_instalacao(novo, envelope(novo, "9.9", chave), "peer-a")
        self.addCleanup(shutil.rmtree, ia, True)
        ib = escrever_instalacao(antigo, envelope(antigo, "9.8", chave),
                                 "peer-b")
        self.addCleanup(shutil.rmtree, ib, True)
        a = Processo(self, ia, "peer-a")
        b = Processo(self, ib, "peer-b",
                     fixos="127.0.0.1:%d" % a.tcp)
        self.assertEqual(a.esperar_eu("peer-a")["versao"], "9.9")
        self.assertEqual(b.esperar_eu("peer-b")["versao"], "9.8")
        eu = b.esperar_versao("9.9", limite=180)
        self.assertEqual(eu["versao"], "9.9")
        self.assertIsNone(b.proc.poll())
        with open(os.path.join(ib, "senderme_app", "extra", "modulo.py"),
                  "rb") as f:
            self.assertEqual(f.read(), b"SINTETICO = True\n")


if __name__ == "__main__":
    unittest.main()
