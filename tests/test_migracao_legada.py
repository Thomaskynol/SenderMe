"""Migração legada: launcher antigo (24176fa, real via git) NÃO restarta o
código modular — demonstração com processo real; migração manual (rodar o
novo start.sh) comprovada na mesma cópia. Fixture sintética, nunca release
histórica autêntica: só o start.sh veio do git, a versão é a atual do código."""
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "tests"))
from test_dist_boot import nova_instalacao, identidade_rapida, porta_livre


def start_antigo():
    r = subprocess.run(["git", "-C", RAIZ, "show", "24176fa:start.sh"],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        return None
    return r.stdout


class MigracaoLegada(unittest.TestCase):
    def test_launcher_antigo_falha_e_mascara_exit_migracao_manual_ok(self):
        antigo = start_antigo()
        if antigo is None:
            self.skipTest("sem git/24176fa disponível")
        self.assertIn('cp "$APP_DIR/senderme.py" "$RUN_DIR/senderme.py"',
                      antigo)  # é o launcher que só copia senderme.py+css
        inst = nova_instalacao()
        self.addCleanup(shutil.rmtree, inst, True)
        identidade_rapida(os.path.join(inst, "dados"))
        with open(os.path.join(inst, "start.sh"), "w",
                  encoding="utf-8") as f:
            f.write(antigo)
        tcp, udp, http = porta_livre(), porta_livre(), porta_livre()
        env = dict(os.environ, SENDERME_PORTA=str(tcp),
                   SENDERME_UDP_PORTA=str(udp), SENDERME_HTTP=str(http))
        # 1) launcher antigo tenta rodar o código modular atual
        r = subprocess.run(["bash", "start.sh"], cwd=inst, env=env,
                           capture_output=True, text=True, timeout=60)
        self.assertIn("ModuleNotFoundError", r.stdout + r.stderr)
        # bug documentado: apesar da falha do Python, o launcher sai 0
        self.assertEqual(r.returncode, 0)
        # 2) migração manual: rodar o start.sh NOVO (já atualizado no disco
        # pelo update) preservando dados/ — a mesma cópia dá boot
        shutil.copy2(os.path.join(RAIZ, "start.sh"),
                     os.path.join(inst, "start.sh"))
        proc = subprocess.Popen(
            ["bash", "start.sh"], cwd=inst, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
        try:
            base = "http://127.0.0.1:%d" % http
            ok = None
            for _ in range(120):
                try:
                    with urllib.request.urlopen(base + "/api/eu",
                                                timeout=3) as rr:
                        ok = json.loads(rr.read().decode())
                        break
                except Exception:
                    if proc.poll() is not None:
                        self.fail("novo start.sh morreu: %s" % proc.returncode)
                    time.sleep(0.25)
            self.assertIsNotNone(ok)
            self.assertTrue(ok["logado"])
            self.assertEqual(ok["nick"], "bot-teste")
        finally:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                proc.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
