"""Update real A→B→C entre processos+launcher (Lane U, item 2).

Caminho real de ponta a ponta: P2P TCP (ver/update_meta/update_get/
update_chunk), aplicação com staging+backup+marcador, saída 42 e restart DE
VERDADE pelo start.sh (loop do launcher), e propagação do envelope assinado
B→C com A fora do ar. Socketpair/FakeSock aparecem SÓ como complemento em
outros arquivos (test_update_fluxo cobre chunk por socket real); aqui nada é
simulado na rede.

Mecanismo de fixture da chave (NÃO é release histórica): a chave pública do
dono é embutida em senderme_app/meta.py (CHAVE_DONO_N/E) e confer_manifest a
usa via senderme_app.estado. Cada instalação de teste recebe uma CÓPIA dos
runtime files com meta.py reescrito (VERSAO de teste 9.8/9.9 + N sintético) e
um update-manifest.json assinado pela chave SINTÉTICA gerada no teste (nunca
dono/privada.json). SENDERME_VERSAO sozinha NÃO é usada: o que prova a versão
nova é código+manifesto+hashes assinados correspondentes no disco + /api/eu.

Lento (~minutos) e delimitado: 3 instalações em tmp com SENDERME_HOME próprio
(ver start.sh: ele força SENDERME_HOME=$APP_DIR), identidades sintéticas
próprias, 9 portas livres, processos com polling limitado e limpeza total
(killpg + rmtree) via addCleanup. Nunca toca dados/ reais.
"""
import hashlib
import json
import os
import re
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
sys.path.insert(0, RAIZ)

import suporte  # noqa: E402
from crypto import assinar as crypto_assinar, conferir as crypto_conferir  # noqa: E402

OLD_V = "9.8"  # fixture de teste (versão "anterior"), NÃO é release histórica
NEW_V = "9.9"  # fixture de teste (versão "nova"), NÃO é release histórica

BOOT_TIMEOUT = 90
UPDATE_TIMEOUT = 240


def porta_livre():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def arquivos_runtime():
    import senderme_app.meta as meta
    return list(meta.ARQUIVOS_UPDATE)


def reescrever_meta(src_bytes, versao, n_hex):
    """Aplica fixture de versão+chave sintética na cópia de meta.py."""
    src = src_bytes.decode("utf-8")
    src, n = re.subn(r'os\.environ\.get\("SENDERME_VERSAO",\s*"[^"]+"\)',
                     'os.environ.get("SENDERME_VERSAO", "%s")' % versao,
                     src, count=1)
    assert n == 1, "padrão VERSAO não achado em meta.py"
    src2, n2 = re.subn(r'CHAVE_DONO_N\s*=\s*\(.*?\)', 'CHAVE_DONO_N = "%s"'
                       % n_hex, src, count=1, flags=re.S)
    assert n2 == 1, "padrão CHAVE_DONO_N não achado em meta.py"
    return src2.encode("utf-8")


def montar_conteudo(versao, chave_sint):
    """{nome: bytes} da release de teste (código atual + meta de fixture)."""
    n_hex = format(chave_sint["n"], "x")
    conteudo = {}
    for nome in arquivos_runtime():
        p = os.path.join(RAIZ, nome)
        assert os.path.isfile(p), "faltando no código atual: %s" % nome
        with open(p, "rb") as f:
            blob = f.read()
        if nome == os.path.join("senderme_app", "meta.py"):
            blob = reescrever_meta(blob, versao, n_hex)
        conteudo[nome] = blob
    return conteudo


def assinar_envelope(conteudo, versao, chave_sint):
    import senderme_app.update as upd
    manifest = {"v": versao, "arquivos": [
        {"nome": n, "tamanho": len(conteudo[n]),
         "sha256": hashlib.sha256(conteudo[n]).hexdigest()}
        for n in arquivos_runtime()]}
    sig = crypto_assinar(upd.manifest_canonico(manifest),
                         chave_sint).hex()
    return {"manifest": manifest, "sig": sig}


def escrever_instalacao(conteudo, envelope, nick):
    """Cria instalação isolada: runtime + start.sh + manifesto + identidade."""
    inst = tempfile.mkdtemp(prefix="sm-abc-")
    for nome, blob in conteudo.items():
        dst = os.path.join(inst, nome)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as f:
            f.write(blob)
    for extra in ("start.sh", "bootstrap.min.css"):
        src = os.path.join(RAIZ, extra)
        if os.path.isfile(src) and not os.path.isfile(os.path.join(inst, extra)):
            shutil.copy2(src, os.path.join(inst, extra))
    with open(os.path.join(inst, "update-manifest.json"), "w",
              encoding="utf-8") as f:
        json.dump(envelope, f, ensure_ascii=False)
    dados = os.path.join(inst, "dados")
    os.makedirs(dados, exist_ok=True)
    chave = suporte.chave_teste()
    idt = suporte.identidade_de(chave)
    with open(os.path.join(dados, "identidade.json"), "w",
              encoding="utf-8") as f:
        json.dump({"n": format(chave["n"], "x"), "e": chave["e"],
                   "d": format(chave["d"], "x"), "id": idt["id"]}, f)
    os.chmod(os.path.join(dados, "identidade.json"), 0o600)
    with open(os.path.join(dados, "apelido.txt"), "w",
              encoding="utf-8") as f:
        f.write(nick)
    return inst


class Processo:
    """Um start.sh real rodando uma instalação de teste."""

    def __init__(self, tc, inst, nick, fixos=""):
        self.inst = inst
        self.tcp, self.udp, self.http = (porta_livre(), porta_livre(),
                                         porta_livre())
        self.base = "http://127.0.0.1:%d" % self.http
        self.log_path = os.path.join(inst, "launcher-teste.log")
        self.log = open(self.log_path, "ab")
        env = {k: v for k, v in os.environ.items()
               if k not in ("SENDERME_HOME", "SENDERME_VERSAO",
                            "SENDERME_FIXOS")}
        env.update({"SENDERME_PORTA": str(self.tcp),
                    "SENDERME_UDP_PORTA": str(self.udp),
                    "SENDERME_HTTP": str(self.http),
                    "SENDERME_FIXOS": fixos,
                    # supressão de broadcast em teste (ver udp.thread_udp:
                    # sem o patch, inócuo; com o patch, nada sai p/ a LAN).
                    "SENDERME_NO_BROADCAST": "1"})
        self.proc = subprocess.Popen(
            ["bash", "start.sh"], cwd=inst, env=env,
            stdout=self.log, stderr=subprocess.STDOUT,
            start_new_session=True)
        tc.addCleanup(self.fechar)

    def fechar(self):
        try:
            os.killpg(self.proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            self.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            self.proc.wait(timeout=15)
        try:
            self.log.close()
        except Exception:
            pass

    def api(self, rota, timeout=10):
        with urllib.request.urlopen(self.base + rota,
                                     timeout=timeout) as r:
            return json.loads(r.read().decode())

    def esperar_eu(self, nick, limite=BOOT_TIMEOUT):
        fim = time.time() + limite
        while time.time() < fim:
            if self.proc.poll() is not None:
                raise AssertionError(
                    "%s: launcher morreu (exit %s); log:\n%s"
                    % (nick, self.proc.returncode, self.cauda()))
            try:
                eu = self.api("/api/eu")
                if eu["logado"] and eu["nick"] == nick:
                    return eu
            except Exception:
                pass
            time.sleep(0.5)
        raise AssertionError("%s sem login em %ss; log:\n%s"
                             % (nick, limite, self.cauda()))

    def esperar_versao(self, versao, limite=UPDATE_TIMEOUT):
        """Aguarda o restart pós-update: tolera a janela sem HTTP."""
        fim = time.time() + limite
        while time.time() < fim:
            if self.proc.poll() is not None:
                raise AssertionError(
                    "launcher morreu esperando %s (exit %s); log:\n%s"
                    % (versao, self.proc.returncode, self.cauda()))
            try:
                eu = self.api("/api/eu")
                if eu["logado"] and eu.get("versao") == versao:
                    return eu
            except Exception:
                pass
            time.sleep(1.0)
        raise AssertionError("versão %s não assumiu em %ss; log:\n%s"
                             % (versao, limite, self.cauda()))

    def cauda(self, n=40):
        try:
            with open(self.log_path, "rb") as f:
                linhas = f.read().decode("utf-8", "replace").splitlines()
            return "\n".join(linhas[-n:])
        except OSError:
            return "<sem log>"


def confere_instalacao(inst, envelope, chave_sint):
    """Manifesto+assinatura+hashes correspondem aos arquivos no disco."""
    import senderme_app.update as upd
    manif = envelope["manifest"]
    assert crypto_conferir(
        upd.manifest_canonico(manif),
        bytes.fromhex(envelope["sig"]),
        chave_sint["n"], chave_sint["e"]), "assinatura não confere"
    for a in manif["arquivos"]:
        with open(os.path.join(inst, a["nome"]), "rb") as f:
            blob = f.read()
        assert len(blob) == a["tamanho"], a["nome"]
        assert hashlib.sha256(blob).hexdigest() == a["sha256"], a["nome"]


class CadeiaABC(unittest.TestCase):
    def test_b_recebe_de_a_e_c_recebe_de_b_com_restart_real(self):
        chave_sint = suporte.chave_teste()
        conteudo_novo = montar_conteudo(NEW_V, chave_sint)
        conteudo_velho = montar_conteudo(OLD_V, chave_sint)
        env_novo = assinar_envelope(conteudo_novo, NEW_V, chave_sint)
        env_velho = assinar_envelope(conteudo_velho, OLD_V, chave_sint)

        inst_a = escrever_instalacao(conteudo_novo, env_novo, "peer-a")
        self.addCleanup(shutil.rmtree, inst_a, True)
        inst_b = escrever_instalacao(conteudo_velho, env_velho, "peer-b")
        self.addCleanup(shutil.rmtree, inst_b, True)

        # --- fase 1: A (nova) serve B (velha) via P2P real ---
        a = Processo(self, inst_a, "peer-a")
        b = Processo(self, inst_b, "peer-b",
                     fixos="127.0.0.1:%d" % a.tcp)
        eu_a = a.esperar_eu("peer-a")
        self.assertEqual(eu_a["versao"], NEW_V)
        eu_b0 = b.esperar_eu("peer-b")
        self.assertEqual(eu_b0["versao"], OLD_V)
        def sha_meta(inst):
            with open(os.path.join(inst, "senderme_app", "meta.py"),
                      "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()

        hash_antes = sha_meta(inst_b)

        eu_b1 = b.esperar_versao(NEW_V)  # inclui download+apply+exit42+reboot
        self.assertEqual(eu_b1["nick"], "peer-b")
        hash_depois = sha_meta(inst_b)
        self.assertNotEqual(hash_antes, hash_depois)
        with open(os.path.join(inst_b, "update-manifest.json"),
                  encoding="utf-8") as f:
            env_b = json.load(f)
        self.assertEqual(env_b["sig"], env_novo["sig"])
        self.assertEqual(env_b["manifest"], env_novo["manifest"])
        confere_instalacao(inst_b, env_novo, chave_sint)
        # funcionamento básico após o reinício
        self.assertIn("eventos", b.api("/api/mensagens"))
        self.assertIn("aplicado, reiniciando", b.cauda())

        # --- fase 2: A morre; B serve C via P2P real ---
        a.fechar()
        inst_c = escrever_instalacao(conteudo_velho, env_velho, "peer-c")
        self.addCleanup(shutil.rmtree, inst_c, True)
        c = Processo(self, inst_c, "peer-c",
                     fixos="127.0.0.1:%d" % b.tcp)
        eu_c0 = c.esperar_eu("peer-c")
        self.assertEqual(eu_c0["versao"], OLD_V)
        eu_c1 = c.esperar_versao(NEW_V)
        self.assertEqual(eu_c1["nick"], "peer-c")
        with open(os.path.join(inst_c, "update-manifest.json"),
                  encoding="utf-8") as f:
            env_c = json.load(f)
        self.assertEqual(env_c["sig"], env_novo["sig"])
        confere_instalacao(inst_c, env_novo, chave_sint)
        self.assertIn("eventos", c.api("/api/mensagens"))
        self.assertIn("aplicado, reiniciando", c.cauda())


class ReinicioAposQueda(unittest.TestCase):
    """Reoferta real após kill no meio do download (achado 2).

    B (velha) começa a baixar de A (nova), morre com SIGKILL antes de
    aplicar e volta na MESMA instalação (mesma identidade/versão). Sem
    reoferta, A nunca reenvia a meta — a marca (peer, versão) da entrega
    morta só sai com a conexão que a fez. Exige o bypass por socket morto;
    na 1.10 este teste trava em OLD_V até o timeout.
    Só processos, instalações, chaves e identidades de teste em tmp.
    """

    def test_morto_no_download_recebe_de_novo_ao_voltar(self):
        chave_sint = suporte.chave_teste()
        conteudo_novo = montar_conteudo(NEW_V, chave_sint)
        conteudo_velho = montar_conteudo(OLD_V, chave_sint)
        env_novo = assinar_envelope(conteudo_novo, NEW_V, chave_sint)
        env_velho = assinar_envelope(conteudo_velho, OLD_V, chave_sint)
        inst_a = escrever_instalacao(conteudo_novo, env_novo, "peer-a")
        self.addCleanup(shutil.rmtree, inst_a, True)
        inst_b = escrever_instalacao(conteudo_velho, env_velho, "peer-b")
        self.addCleanup(shutil.rmtree, inst_b, True)

        a = Processo(self, inst_a, "peer-a")
        b1 = Processo(self, inst_b, "peer-b",
                      fixos="127.0.0.1:%d" % a.tcp)
        self.assertEqual(a.esperar_eu("peer-a")["versao"], NEW_V)
        self.assertEqual(b1.esperar_eu("peer-b")["versao"], OLD_V)
        # janela do kill: B já logou "baixando" mas ainda não aplicou
        fim = time.time() + 120
        while time.time() < fim:
            cauda = b1.cauda(n=200)
            if "baixando" in cauda:
                break
            if b1.proc.poll() is not None:
                self.fail("B morreu antes do download; log:\n%s" % cauda)
            time.sleep(0.2)
        else:
            self.fail("B nunca começou a baixar; log:\n%s" % b1.cauda())
        cauda = b1.cauda(n=200)
        self.assertIn("baixando", cauda)
        self.assertNotIn("aplicado, reiniciando", cauda,
                         "janela do kill perdida: B já aplicou antes do "
                         "SIGKILL (teste inconclusivo)")
        try:
            os.killpg(b1.proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        b1.proc.wait(timeout=30)
        b1.fechar()
        # volta na mesma instalação: mesma identidade, ainda na versão velha
        b2 = Processo(self, inst_b, "peer-b",
                      fixos="127.0.0.1:%d" % a.tcp)
        eu = b2.esperar_versao(NEW_V)
        self.assertEqual(eu["nick"], "peer-b")
        confere_instalacao(inst_b, env_novo, chave_sint)
        self.assertIn("aplicado, reiniciando", b2.cauda())


if __name__ == "__main__":
    unittest.main()
