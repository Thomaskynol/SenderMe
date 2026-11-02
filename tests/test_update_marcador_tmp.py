"""Corrida no temporário do marcador/manifesto (achado 1 da revisão 1.9).

Escopo honesto: alteração LOCAL concorrente com chave SINTÉTICA em tmp
(nunca dono/privada.json, nunca dados/ real). Exige capacidade de alterar
os diretórios da instalação durante o update + suporte a symlink. Não
demonstra ataque remoto, forja de assinatura nem ganho de privilégio.

Cobre as janelas que seguiam por caminho absoluto na 1.9:
- `.upd-pendente.json.tmp` aberto com builtins.open antes do replace;
- `update-manifest.json.tmp` aberto com builtins.open antes do replace;
- preboot: `update-manifest.json.upd-tmp` aberto com open() antes do replace.

Exigido DEPOIS da correção: arquivo externo intacto, erro detectado
(retorna False no update / faltando no preboot), journal preservado quando
já houver algo aplicado, mensagem honesta (sem afirmar "revertida" nem
sucesso). O gancho casa pelo basename no os.open de criação (O_CREAT), de
modo a forçar o entrelaçamento qualquer que seja o chamador.
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
import senderme_app.preboot as preboot_mod  # noqa: E402
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


def ler_bin(p):
    with open(p, "rb") as f:
        return f.read()


def gravar(pasta, nome, blob):
    p = os.path.join(pasta, nome)
    os.makedirs(os.path.dirname(p) or pasta, exist_ok=True)
    with open(p, "wb") as f:
        f.write(blob)


def preparar_update(tc, base, conteudo):
    """Assina release sintética e monta as partes em memória."""
    chave = instalar_chave_sintetica(tc)
    env, manif = assinar_release(chave, "99.0", conteudo)
    sm.update_manifest = manif
    sm.update_envelope = env
    sm.atualizando = True
    for nome, blob in conteudo.items():
        sm.update_montando[nome] = {"total": 1, "partes": {0: blob},
                                    "ts": sm.agora()}


def gancho_criacao(mod, alvo_rel, alvo_abs, base, alvo_externo):
    """Troca `base/alvo_rel` por symlink p/ alvo_externo na janela exata da
    criação do temporário: casa tanto `_escrever_rel` relativo a fd fixado
    (pós-correção) quanto `builtins.open` por caminho absoluto (pré-correção,
    para o RED demonstrar o bug real). Retorna (ctxs, estado)."""
    import builtins
    pronto = threading.Event()
    terminou = threading.Event()
    erros = []
    estado = {"gatilhos": 0}

    def atacante():
        try:
            if not pronto.wait(10):
                raise RuntimeError("janela de criação não atingida")
            os.symlink(alvo_externo, os.path.join(base, alvo_rel))
        except BaseException as exc:  # noqa: BLE001
            erros.append(repr(exc))
        finally:
            terminou.set()

    def sincronizar():
        if estado["gatilhos"] == 0:
            estado["gatilhos"] += 1
            pronto.set()
            if not terminou.wait(10):
                raise RuntimeError("troca local não concluiu")
            if erros:
                raise RuntimeError(str(erros))

    fio = threading.Thread(target=atacante, daemon=True)
    fio.start()
    orig_escrever = mod._escrever_rel

    def escrever_sincronizado(root_fd, rel, dados):
        if rel == alvo_rel:
            sincronizar()
        return orig_escrever(root_fd, rel, dados)

    orig_open = builtins.open

    def open_sincronizado(path, *a, **kw):
        try:
            nome = os.fspath(path)
        except Exception:
            nome = ""
        modo = a[0] if a else kw.get("mode", "r")
        if nome == alvo_abs and isinstance(modo, str) \
                and modo.startswith("w"):
            sincronizar()
        return orig_open(path, *a, **kw)

    ctx1 = mock.patch.object(mod, "_escrever_rel",
                             side_effect=escrever_sincronizado)
    ctx2 = mock.patch("builtins.open", side_effect=open_sincronizado)
    return (ctx1, ctx2), fio, pronto, erros, estado


class CorridaTemporariosUpdate(CasoIsolado):
    def test_marcador_tmp_nao_altera_externo_e_aborta(self):
        definir_eu("alice")
        base = self._tmp.name
        fora = tempfile.mkdtemp(prefix="sm-marcador-fora-")
        self.addCleanup(shutil.rmtree, fora, True)
        externo = os.path.join(fora, "arquivo-sintetico.txt")
        with open(externo, "wb") as f:
            f.write(b"conteudo-original")
        gravar(base, "senderme.py", b"velho")
        with open(os.path.join(base, "update-manifest.json"), "w") as f:
            f.write('{"v": "old"}')
        preparar_update(self, base, {"senderme.py": b"novo"})
        ctxs, fio, pronto, erros, estado = gancho_criacao(
            upd_mod, ".upd-pendente.json.tmp",
            os.path.join(base, ".upd-pendente.json.tmp"), base, externo)
        logs = []
        with ctxs[0], ctxs[1], mock.patch.object(upd_mod, "log",
                                                 lambda t: logs.append(t)):
            ok = sm.finalizar_update()
        fio.join(timeout=10)
        print("retorno_update=%r marcador=%r backup=%r externo_intacto=%r"
              % (ok, os.path.lexists(os.path.join(base, ".upd-pendente.json")),
                 os.path.isdir(os.path.join(base, ".upd-backup")),
                 ler_bin(externo) == b"conteudo-original"))
        self.assertTrue(pronto.is_set(),
                        "a criação do marcador não chegou ao ponto gancho")
        self.assertFalse(erros, str(erros))
        with open(externo, "rb") as f:
            self.assertEqual(f.read(), b"conteudo-original",
                             "arquivo externo foi alterado; update=%r" % ok)
        self.assertFalse(ok)
        with open(os.path.join(base, "senderme.py"), "rb") as f:
            self.assertEqual(f.read(), b"velho")
        texto = "\n".join(logs)
        self.assertNotIn("revertida", texto)
        self.assertNotIn("aplicado, reiniciando", texto)

    def test_manifesto_tmp_nao_altera_externo_e_preserva_journal(self):
        definir_eu("alice")
        base = self._tmp.name
        fora = tempfile.mkdtemp(prefix="sm-manifesto-fora-")
        self.addCleanup(shutil.rmtree, fora, True)
        externo = os.path.join(fora, "arquivo-sintetico.txt")
        with open(externo, "wb") as f:
            f.write(b"conteudo-original")
        gravar(base, "senderme.py", b"velho")
        with open(os.path.join(base, "update-manifest.json"), "w") as f:
            f.write('{"v": "old"}')
        preparar_update(self, base, {"senderme.py": b"novo"})
        ctxs, fio, pronto, erros, estado = gancho_criacao(
            upd_mod, "update-manifest.json.tmp",
            os.path.join(base, "update-manifest.json.tmp"), base, externo)
        logs = []
        with ctxs[0], ctxs[1], mock.patch.object(upd_mod, "log",
                                                 lambda t: logs.append(t)):
            ok = sm.finalizar_update()
        fio.join(timeout=10)
        print("retorno_update=%r marcador=%r backup=%r externo_intacto=%r"
              % (ok, os.path.lexists(os.path.join(base, ".upd-pendente.json")),
                 os.path.isdir(os.path.join(base, ".upd-backup")),
                 ler_bin(externo) == b"conteudo-original"))
        self.assertTrue(pronto.is_set(),
                        "a criação do manifesto não chegou ao ponto gancho")
        self.assertFalse(erros, str(erros))
        with open(externo, "rb") as f:
            self.assertEqual(f.read(), b"conteudo-original",
                             "arquivo externo foi alterado; update=%r" % ok)
        self.assertFalse(ok)
        # algo já havia sido aplicado (marcador gravado): journal fica p/ boot
        self.assertTrue(os.path.lexists(
            os.path.join(base, ".upd-pendente.json")))
        self.assertTrue(os.path.isdir(os.path.join(base, ".upd-backup")))
        texto = "\n".join(logs)
        self.assertNotIn("revertida", texto)
        self.assertNotIn("aplicado, reiniciando", texto)


class CorridaTemporarioPreboot(CasoIsolado):
    def test_preboot_manifesto_tmp_nao_altera_externo(self):
        base = self._tmp.name
        fora = tempfile.mkdtemp(prefix="sm-preboot-fora-")
        self.addCleanup(shutil.rmtree, fora, True)
        externo = os.path.join(fora, "arquivo-sintetico.txt")
        with open(externo, "wb") as f:
            f.write(b"conteudo-original")
        # estado de update interrompido: destino novo + backup do velho
        gravar(base, "senderme.py", b"novo-interrompido")
        gravar(base, ".upd-backup/senderme.py", b"velho")
        gravar(base, ".upd-backup/update-manifest.json", b'{"v": "old"}')
        import json
        with open(os.path.join(base, ".upd-pendente.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"v": "99.0", "arquivos": ["senderme.py"],
                       "novos": [], "tinha_manifesto": True}, f)
        ctxs, fio, pronto, erros, estado = gancho_criacao(
            preboot_mod, "update-manifest.json.upd-tmp",
            os.path.join(base, "update-manifest.json.upd-tmp"),
            base, externo)
        logs = []
        with ctxs[0], ctxs[1]:
            teve = preboot_mod.recuperar(
                base, log=lambda t: logs.append(t))
        fio.join(timeout=10)
        print("teve=%r marcador=%r backup=%r externo_intacto=%r"
              % (teve, os.path.lexists(os.path.join(base, ".upd-pendente.json")),
                 os.path.isdir(os.path.join(base, ".upd-backup")),
                 ler_bin(externo) == b"conteudo-original"))
        self.assertTrue(pronto.is_set(),
                        "a criação do .upd-tmp não chegou ao ponto gancho")
        self.assertFalse(erros, str(erros))
        with open(externo, "rb") as f:
            self.assertEqual(f.read(), b"conteudo-original",
                             "arquivo externo foi alterado")
        self.assertTrue(teve)
        self.assertTrue(os.path.lexists(
            os.path.join(base, ".upd-pendente.json")))
        self.assertTrue(os.path.isdir(os.path.join(base, ".upd-backup")))


if __name__ == "__main__":
    unittest.main()
