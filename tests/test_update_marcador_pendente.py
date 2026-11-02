"""Guarda de marcador pendente: symlink (válido ou quebrado) nunca boota mistura.

Escopo honesto: alteração LOCAL em tmp com identidades sintéticas (nunca
dados/ real, nunca dono/privada.json). O symlink é pré-existente local;
não demonstra criação remota, forja de assinatura nem execução de mistura.
Exigido: preboot.main e app.main usam lexists (não exists, que retorna
False para link quebrado), bloqueiam com mensagem acionável e preservam
marcador+backup para intervenção manual. 5 casos: ausente, válido regular,
inválido, symlink-válido, symlink-quebrado — no preboot direto E no
launcher completo (start.sh real + preboot real + stub de sonda).

Escrito ANTES da correção (TDD red→green): symlink-quebrado hoje retorna
exit 0 no preboot e o launcher inicia.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "tests"))
sys.path.insert(0, RAIZ)

import suporte  # noqa: E402
import senderme as sm  # noqa: E402
import senderme_app.preboot as preboot_mod  # noqa: E402
from suporte import CasoIsolado  # noqa: E402
from test_dist_boot import nova_instalacao  # noqa: E402

_bin = tempfile.TemporaryDirectory(prefix="sm-marcador-bin-")
_xdg = os.path.join(_bin.name, "xdg-open")
with open(_xdg, "w") as f:
    f.write("#!/bin/sh\nexit 0\n")
os.chmod(_xdg, 0o700)
_PATH_CORRETO = _bin.name + os.pathsep + os.environ.get("PATH", "")


def gravar(pasta, nome, blob):
    p = os.path.join(pasta, nome)
    os.makedirs(os.path.dirname(p) or pasta, exist_ok=True)
    with open(p, "wb") as f:
        f.write(blob)


def marcador_valido(base, arquivos=("x.txt",)):
    gravar(base, "x.txt", b"novo-parcial")
    gravar(base, ".upd-backup/x.txt", b"antigo-bom")
    with open(os.path.join(base, ".upd-pendente.json"), "w",
              encoding="utf-8") as f:
        json.dump({"v": "99.0", "arquivos": list(arquivos), "novos": [],
                   "tinha_manifesto": False}, f)


class PrebootCincoCasos(CasoIsolado):
    def test_ausente_exit_0(self):
        self.assertFalse(os.path.lexists(
            os.path.join(self._tmp.name, ".upd-pendente.json")))
        self.assertEqual(preboot_mod.main(["preboot.py", self._tmp.name]), 0)

    def test_valido_recupera_e_exit_0(self):
        marcador_valido(self._tmp.name)
        self.assertEqual(preboot_mod.main(["preboot.py", self._tmp.name]), 0)
        with open(os.path.join(self._tmp.name, "x.txt"), "rb") as f:
            self.assertEqual(f.read(), b"antigo-bom")
        self.assertFalse(os.path.lexists(
            os.path.join(self._tmp.name, ".upd-pendente.json")))

    def test_invalido_exit_1_e_preserva(self):
        with open(os.path.join(self._tmp.name, ".upd-pendente.json"), "w",
                  encoding="utf-8") as f:
            f.write("{json quebrado")
        gravar(self._tmp.name, ".upd-backup/x.txt", b"antigo-bom")
        self.assertEqual(preboot_mod.main(["preboot.py", self._tmp.name]), 1)
        self.assertTrue(os.path.lexists(
            os.path.join(self._tmp.name, ".upd-pendente.json")))
        self.assertTrue(os.path.isdir(
            os.path.join(self._tmp.name, ".upd-backup")))

    def test_symlink_valido_exit_1_e_preserva(self):
        fora = tempfile.mkdtemp(prefix="sm-marcador-alvo-")
        self.addCleanup(shutil.rmtree, fora, True)
        alvo = os.path.join(fora, "marcador.json")
        with open(alvo, "w", encoding="utf-8") as f:
            json.dump({"v": "99.0", "arquivos": [], "novos": []}, f)
        os.symlink(alvo, os.path.join(self._tmp.name, ".upd-pendente.json"))
        gravar(self._tmp.name, ".upd-backup/x.txt", b"antigo-bom")
        self.assertEqual(preboot_mod.main(["preboot.py", self._tmp.name]), 1)
        # preserva o link (não segue para fora) e o backup p/ intervenção
        self.assertTrue(os.path.islink(
            os.path.join(self._tmp.name, ".upd-pendente.json")))
        self.assertTrue(os.path.isdir(
            os.path.join(self._tmp.name, ".upd-backup")))

    def test_symlink_quebrado_exit_1_e_preserva(self):
        fora = tempfile.mkdtemp(prefix="sm-marcador-alvo-")
        self.addCleanup(shutil.rmtree, fora, True)
        os.symlink(os.path.join(fora, "sumiu.json"),
                   os.path.join(self._tmp.name, ".upd-pendente.json"))
        self.assertFalse(os.path.exists(
            os.path.join(self._tmp.name, ".upd-pendente.json")))
        self.assertTrue(os.path.lexists(
            os.path.join(self._tmp.name, ".upd-pendente.json")))
        gravar(self._tmp.name, ".upd-backup/x.txt", b"antigo-bom")
        self.assertEqual(preboot_mod.main(["preboot.py", self._tmp.name]), 1)
        self.assertTrue(os.path.islink(
            os.path.join(self._tmp.name, ".upd-pendente.json")))
        self.assertTrue(os.path.isdir(
            os.path.join(self._tmp.name, ".upd-backup")))


STUB_SONDA = ("import os, sys\n"
              "open(os.path.join(os.environ['SENDERME_HOME'], 'probe.out'),"
              " 'w').write('chegou')\n"
              "sys.exit(3)\n")


def instalar_stub():
    inst = nova_instalacao(STUB_SONDA)
    return inst


def armar_caso_launcher(inst, caso):
    """Prepara o marcador do caso dentro da instalação isolada."""
    marc = os.path.join(inst, ".upd-pendente.json")
    if caso == "ausente":
        return
    if caso == "valido":
        marcador_valido(inst)
        return
    if caso == "invalido":
        with open(marc, "w", encoding="utf-8") as f:
            f.write("{json quebrado")
        gravar(inst, ".upd-backup/x.txt", b"antigo-bom")
        return
    fora = tempfile.mkdtemp(prefix="sm-launcher-alvo-")
    if caso == "symlink-valido":
        alvo = os.path.join(fora, "marcador.json")
        with open(alvo, "w", encoding="utf-8") as f:
            json.dump({"v": "99.0", "arquivos": [], "novos": []}, f)
        os.symlink(alvo, marc)
    elif caso == "symlink-quebrado":
        os.symlink(os.path.join(fora, "sumiu.json"), marc)
    else:  # pragma: no cover
        raise AssertionError(caso)
    gravar(inst, ".upd-backup/x.txt", b"antigo-bom")
    # o dir externo precisa sobreviver ao teste (link quebrado aponta p/ lá)
    return fora


class LauncherCincoCasos(unittest.TestCase):
    def rodar(self, caso):
        inst = instalar_stub()
        self.addCleanup(shutil.rmtree, inst, True)
        fora = armar_caso_launcher(inst, caso)
        if fora:
            self.addCleanup(shutil.rmtree, fora, True)
        env = dict(os.environ, PATH=_PATH_CORRETO,
                   PYTHONDONTWRITEBYTECODE="1",
                   SENDERME_NO_BROADCAST="1")
        r = subprocess.run(["bash", "start.sh"], cwd=inst, env=env,
                           capture_output=True, text=True, timeout=90)
        return inst, r

    def test_launcher_ausente_roda_stub(self):
        inst, r = self.rodar("ausente")
        self.assertEqual(r.returncode, 3, r.stderr[-2000:])
        with open(os.path.join(inst, "probe.out"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "chegou")

    def test_launcher_valido_recupera_e_roda_stub(self):
        inst, r = self.rodar("valido")
        self.assertEqual(r.returncode, 3, r.stderr[-2000:])
        with open(os.path.join(inst, "probe.out"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "chegou")
        self.assertFalse(os.path.lexists(
            os.path.join(inst, ".upd-pendente.json")))

    def test_launcher_invalido_bloqueia_sem_rodar(self):
        inst, r = self.rodar("invalido")
        self.assertNotEqual(r.returncode, 0, r.stderr[-2000:])
        self.assertFalse(os.path.exists(os.path.join(inst, "probe.out")),
                         "stub rodou sobre marcador inválido")
        self.assertTrue(os.path.lexists(
            os.path.join(inst, ".upd-pendente.json")))
        self.assertTrue(os.path.isdir(os.path.join(inst, ".upd-backup")))

    def test_launcher_symlink_valido_bloqueia_sem_rodar(self):
        inst, r = self.rodar("symlink-valido")
        self.assertNotEqual(r.returncode, 0, r.stderr[-2000:])
        self.assertFalse(os.path.exists(os.path.join(inst, "probe.out")),
                         "stub rodou sobre marcador symlink")
        self.assertTrue(os.path.islink(
            os.path.join(inst, ".upd-pendente.json")))
        self.assertTrue(os.path.isdir(os.path.join(inst, ".upd-backup")))

    def test_launcher_symlink_quebrado_bloqueia_sem_rodar(self):
        inst, r = self.rodar("symlink-quebrado")
        self.assertNotEqual(r.returncode, 0, r.stderr[-2000:])
        self.assertFalse(os.path.exists(os.path.join(inst, "probe.out")),
                         "stub rodou sobre marcador symlink quebrado")
        self.assertTrue(os.path.islink(
            os.path.join(inst, ".upd-pendente.json")))
        self.assertTrue(os.path.isdir(os.path.join(inst, ".upd-backup")))


class Serviria(Exception):
    pass


def _sonda_servidor(chamou):
    def sonda():
        chamou.append(1)
        raise Serviria("app tentou abrir servidor sobre marcador pendente")
    return sonda


class GuardaApp(CasoIsolado):
    def test_app_nao_serve_com_symlink_quebrado(self):
        from unittest import mock
        from senderme_app import app as app_mod
        os.symlink(os.path.join(self._tmp.name, "sumiu.json"),
                   os.path.join(self._tmp.name, ".upd-pendente.json"))
        gravar(self._tmp.name, ".upd-backup/x.txt", b"antigo-bom")
        chamou = []
        with mock.patch.object(app_mod, "abrir_servidor",
                               _sonda_servidor(chamou)):
            with self.assertRaises(SystemExit) as ctx:
                app_mod.main()
        self.assertEqual(chamou, [])
        self.assertEqual(ctx.exception.code, 1)
        self.assertTrue(os.path.islink(
            os.path.join(self._tmp.name, ".upd-pendente.json")))
        self.assertTrue(os.path.isdir(
            os.path.join(self._tmp.name, ".upd-backup")))

    def test_app_nao_serve_com_marcador_invalido(self):
        from unittest import mock
        from senderme_app import app as app_mod
        with open(os.path.join(self._tmp.name, ".upd-pendente.json"), "w",
                  encoding="utf-8") as f:
            f.write("{json quebrado")
        chamou = []
        with mock.patch.object(app_mod, "abrir_servidor",
                               _sonda_servidor(chamou)):
            with self.assertRaises(SystemExit) as ctx:
                app_mod.main()
        self.assertEqual(chamou, [])
        self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
