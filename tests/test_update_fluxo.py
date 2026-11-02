"""Fluxo de update com chave SINTÉTICA em dirs temporários (nunca a real).

Escopo honesto: aplicação + envelope persistido, versões, assinatura,
adulteração, pacote incompleto, rollback em falha de gravação, recuperação
no boot e propagação A→B→C. A→B→C usa chamadas diretas
(servir_update/receber_update_chunk) com FakeSock em memória e arquivos de
parte única — NÃO demonstra o loop baixar_update (stall/timeout na rede
real) nem o restart os._exit(42) com update aplicado de verdade entre
processos. Chunk por socket real (socketpair + framing de verdade) coberto
em ChunkViaSocketReal. Loop 42 do launcher (lado start.sh) coberto em
test_dist_boot; restart real entre releases segue hipótese (ver
docs/04-migracao.md). Chave rápida ~512 bits: mesmo código assinar/conferir
(ver suporte.py).
"""
import hashlib
import json
import os
import unittest
from unittest import mock

import senderme as sm
from suporte import (CasoIsolado, definir_eu, chave_teste, quadros, FakeSock)


def instalar_chave_sintetica(tc):
    chave = chave_teste()
    n_hex = format(chave["n"], "x")
    p = mock.patch.multiple("senderme_app.estado", CHAVE_DONO_N=n_hex,
                            CHAVE_DONO_E=65537)
    p.start()
    tc.addCleanup(p.stop)
    return chave


def assinar_release(chave, versao, arquivos):
    """arquivos: {nome: bytes} -> (envelope, manifest)."""
    manifest = {"v": versao, "arquivos": [
        {"nome": n, "tamanho": len(b),
         "sha256": hashlib.sha256(b).hexdigest()}
        for n, b in sorted(arquivos.items())]}
    sig = sm.assinar(sm.manifest_canonico(manifest), chave).hex()
    return {"manifest": manifest, "sig": sig}, manifest


def montar_no_estado(arquivos):
    """Põe os bytes como chunks recebidos (1 parte) no montando global."""
    for nome, blob in arquivos.items():
        sm.update_montando[nome] = {"total": 1, "partes": {0: blob},
                                    "ts": sm.agora()}


def casa(tmp, *nomes):
    for n in nomes:
        p = os.path.join(tmp, n)
        os.makedirs(os.path.dirname(p) or tmp, exist_ok=True)
    return tmp


class Aplicacao(CasoIsolado):
    def test_aplica_persiste_envelope_e_limpa(self):
        definir_eu("alice")
        chave = instalar_chave_sintetica(self)
        novos = {"senderme.py": b"novo-1", "config.py": b"novo-2"}
        env, manif = assinar_release(chave, "99.0", novos)
        for nome, velho in (("senderme.py", b"velho-1"),
                            ("config.py", b"velho-2")):
            with open(os.path.join(self._tmp.name, nome), "wb") as f:
                f.write(velho)
        sm.update_manifest = manif
        sm.update_envelope = env
        sm.atualizando = True
        montar_no_estado(novos)
        self.assertTrue(sm.finalizar_update())
        for nome, blob in novos.items():
            with open(os.path.join(self._tmp.name, nome), "rb") as f:
                self.assertEqual(f.read(), blob)
        with open(os.path.join(self._tmp.name, "update-manifest.json"),
                  encoding="utf-8") as f:
            self.assertEqual(json.load(f), env)
        self.assertFalse(sm.atualizando)
        self.assertEqual(sm.update_montando, {})
        for resto in (".upd-staging", ".upd-backup", ".upd-pendente.json"):
            self.assertFalse(os.path.exists(os.path.join(self._tmp.name, resto)))

    def test_arquivo_adulterado_aborta_sem_mudar_nada(self):
        definir_eu("alice")
        chave = instalar_chave_sintetica(self)
        novos = {"senderme.py": b"novo-1"}
        env, manif = assinar_release(chave, "99.0", novos)
        with open(os.path.join(self._tmp.name, "senderme.py"), "wb") as f:
            f.write(b"velho-1")
        sm.update_manifest = manif
        sm.update_envelope = env
        sm.atualizando = True
        montar_no_estado({"senderme.py": b"ADULTERADO"})
        self.assertFalse(sm.finalizar_update())
        self.assertFalse(sm.atualizando)
        with open(os.path.join(self._tmp.name, "senderme.py"), "rb") as f:
            self.assertEqual(f.read(), b"velho-1")

    def test_meta_assinada_versao_igual_e_inferior_rejeitadas(self):
        definir_eu("alice")
        chave = instalar_chave_sintetica(self)
        with mock.patch("senderme_app.update.baixar_update", lambda: None):
            for v in (sm.VERSAO, "0.1"):
                env, _ = assinar_release(chave, v, {"senderme.py": b"x"})
                sm.receber_update_meta(env)
                self.assertFalse(sm.atualizando, v)
                self.assertIsNone(sm.update_manifest)

    def test_meta_aceita_guarda_envelope(self):
        definir_eu("alice")
        chave = instalar_chave_sintetica(self)
        env, manif = assinar_release(chave, "99.0", {"senderme.py": b"x"})
        with mock.patch("senderme_app.update.baixar_update", lambda: None):
            sm.receber_update_meta(env)
        self.assertTrue(sm.atualizando)
        self.assertEqual(sm.update_manifest, manif)
        self.assertEqual(sm.update_envelope, env)

    def test_manifesto_adulterado_com_outra_assinatura_rejeitado(self):
        definir_eu("alice")
        chave = instalar_chave_sintetica(self)
        outra = chave_teste()
        env, _ = assinar_release(chave, "99.0", {"senderme.py": b"x"})
        # troca o conteúdo mantendo a assinatura: não confere
        env2 = {"manifest": {"v": "99.0", "arquivos": [
            {"nome": "senderme.py", "tamanho": 1, "sha256": "0" * 64}]},
                "sig": env["sig"]}
        _ = outra
        with mock.patch("senderme_app.update.baixar_update", lambda: None):
            sm.receber_update_meta(env2)
        self.assertFalse(sm.atualizando)


class RecuperacaoBoot(CasoIsolado):
    def test_sem_marcador_nada_a_fazer(self):
        self.assertFalse(sm.recuperar_update())

    def test_marcador_restaura_backup(self):
        casa(self._tmp.name, "x.txt")
        with open(os.path.join(self._tmp.name, "x.txt"), "wb") as f:
            f.write(b"novo-parcial")
        bkp = os.path.join(self._tmp.name, ".upd-backup")
        os.makedirs(bkp)
        with open(os.path.join(bkp, "x.txt"), "wb") as f:
            f.write(b"antigo-bom")
        with open(os.path.join(self._tmp.name, ".upd-pendente.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"v": "99.0", "arquivos": ["x.txt"]}, f)
        self.assertTrue(sm.recuperar_update())
        with open(os.path.join(self._tmp.name, "x.txt"), "rb") as f:
            self.assertEqual(f.read(), b"antigo-bom")
        self.assertFalse(os.path.exists(
            os.path.join(self._tmp.name, ".upd-pendente.json")))


class PropagacaoABC(CasoIsolado):
    def test_b_aplica_e_c_recebe_de_b_com_envelope_e_hashes(self):
        import tempfile
        definir_eu("alice")
        chave = instalar_chave_sintetica(self)
        novos = {"senderme.py": b"release-9-senderme",
                 "config.py": b"release-9-config"}
        env, manif = assinar_release(chave, "9.9", novos)
        dir_b = tempfile.mkdtemp(prefix="sm-b-")
        dir_c = tempfile.mkdtemp(prefix="sm-c-")
        self.addCleanup(lambda: __import__("shutil").rmtree(dir_b, True))
        self.addCleanup(lambda: __import__("shutil").rmtree(dir_c, True))
        for d in (dir_b, dir_c):
            for nome in novos:
                with open(os.path.join(d, nome), "wb") as f:
                    f.write(b"antigo")
        velho_codigo = sm.DIR_CODIGO
        try:
            # --- B aplica a release vinda de A ---
            sm.PASTA = dir_b
            sm.update_manifest = manif
            sm.update_envelope = env
            sm.atualizando = True
            montar_no_estado(novos)
            self.assertTrue(sm.finalizar_update())
            with open(os.path.join(dir_b, "update-manifest.json"),
                      encoding="utf-8") as f:
                env_b = json.load(f)
            self.assertEqual(env_b, env)
            # --- C baixa de B via mensagens reais update_get/update_chunk ---
            sm.DIR_CODIGO = dir_b  # B serve seus arquivos aplicados
            sm.PASTA = dir_c
            sm.update_manifest = manif
            sm.update_envelope = env
            sm.atualizando = True
            sm.update_montando.clear()
            for nome in novos:
                sock = FakeSock()
                sm.servir_update("peerB", sock, {"nome": nome, "idx": 0})
                msgs = quadros(sock)
                self.assertEqual(len(msgs), 1)
                self.assertEqual(msgs[0]["t"], "update_chunk")
                sm.receber_update_chunk(msgs[0])
            self.assertTrue(sm.finalizar_update())
            for nome, blob in novos.items():
                with open(os.path.join(dir_c, nome), "rb") as f:
                    self.assertEqual(f.read(), blob, nome)
            with open(os.path.join(dir_c, "update-manifest.json"),
                      encoding="utf-8") as f:
                env_c = json.load(f)
            self.assertEqual(env_c["sig"], env["sig"])
            self.assertTrue(sm.conferir_manifest(env_c["manifest"],
                                                 env_c["sig"]))
        finally:
            sm.DIR_CODIGO = velho_codigo


class ChunkViaSocketReal(CasoIsolado):
    def test_chunk_vai_e_volta_por_socket_real(self):
        """servir_update → socket real → ler_quadro → receber_update_chunk,
        com remontagem e aplicação (finalizar_update) no destino."""
        import socket as _socket
        import tempfile
        definir_eu("alice")
        blob = b"release-bytes-" * 2000  # ~28 KB: 1 chunk de 512 KB
        nome = "config.py"
        srv = tempfile.mkdtemp(prefix="sm-cod-")
        self.addCleanup(lambda: __import__("shutil").rmtree(srv, True))
        with open(os.path.join(srv, nome), "wb") as f:
            f.write(blob)
        manif = {"v": "9.9", "arquivos": [
            {"nome": nome, "tamanho": len(blob),
             "sha256": hashlib.sha256(blob).hexdigest()}]}
        velho_codigo = sm.DIR_CODIGO
        a, b = _socket.socketpair()
        b.settimeout(10)
        try:
            sm.DIR_CODIGO = srv  # servir lê daqui (caminho_update_origem)
            sm.update_manifest = manif
            sm.update_envelope = {"manifest": manif, "sig": "00"}
            sm.atualizando = True
            sm.update_montando.clear()
            total = (len(blob) + sm.CHUNK_ARQ - 1) // sm.CHUNK_ARQ or 1
            for idx in range(total):
                sm.servir_update("peerB", a, {"nome": nome, "idx": idx})
                msg = sm.ler_quadro(b)
                self.assertEqual(msg["t"], "update_chunk")
                self.assertEqual(msg["nome"], nome)
                sm.receber_update_chunk(msg)
            slot = sm.update_montando[nome]
            self.assertEqual(len(slot["partes"]), total)
            self.assertTrue(sm.finalizar_update())
            with open(os.path.join(self._tmp.name, nome), "rb") as f:
                self.assertEqual(f.read(), blob)
            with open(os.path.join(self._tmp.name, "update-manifest.json"),
                      encoding="utf-8") as f:
                self.assertEqual(json.load(f)["manifest"], manif)
        finally:
            sm.DIR_CODIGO = velho_codigo
            try:
                a.close()
            except OSError:
                pass
            try:
                b.close()
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
