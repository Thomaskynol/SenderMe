"""Symlink: caminho assinado não deve escapar da instalação (item 3).

Escopo honesto: ataque LOCAL isolado com chave SINTÉTICA (nunca
dono/privada.json, nunca dados/ real). Não demonstra forja de assinatura
nem criação remota do link — o link é pré-existente local e o manifesto
tem assinatura sintética válida p/ a instalação isolada. Cobre:
ataque por parent symlink (docs->fora), symlink final, caminho normal,
subdir novo e rollback/recuperação sem escape. FS: ext4 com symlink
(suporta); FAT32/NTFS/exFAT sem symlink ficam sem escape por link
(não alegado sem teste nesses FS).
"""
import hashlib
import json
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


def montar(arquivos):
    for nome, blob in arquivos.items():
        sm.update_montando[nome] = {"total": 1, "partes": {0: blob},
                                    "ts": sm.agora()}


def gravar(pasta, nome, blob):
    p = os.path.join(pasta, nome)
    os.makedirs(os.path.dirname(p) or pasta, exist_ok=True)
    with open(p, "wb") as f:
        f.write(blob)


def ler(pasta, nome):
    with open(os.path.join(pasta, nome), "rb") as f:
        return f.read()


class AtaqueSymlink(CasoIsolado):
    def test_parent_symlink_nao_grava_fora_e_aborta(self):
        definir_eu("alice")
        chave = instalar_chave_sintetica(self)
        fora = tempfile.mkdtemp(prefix="sm-symlink-fora-")
        self.addCleanup(shutil.rmtree, fora, True)
        externo = os.path.join(fora, "arquivo.txt")
        with open(externo, "wb") as f:
            f.write(b"fora-original")
        gravar(self._tmp.name, "senderme.py", b"velho-1")
        os.symlink(fora, os.path.join(self._tmp.name, "docs"))
        novos = {"senderme.py": b"novo-1", "docs/arquivo.txt": b"fora-modificado"}
        env, manif = assinar_release(chave, "99.0", novos)
        sm.update_manifest = manif
        sm.update_envelope = env
        sm.atualizando = True
        montar(novos)
        self.assertFalse(sm.finalizar_update())
        self.assertFalse(sm.atualizando)
        with open(externo, "rb") as f:
            self.assertEqual(f.read(), b"fora-original")
        self.assertEqual(ler(self._tmp.name, "senderme.py"), b"velho-1")
        self.assertFalse(os.path.exists(
            os.path.join(self._tmp.name, ".upd-pendente.json")))
        self.assertFalse(os.path.exists(
            os.path.join(self._tmp.name, ".upd-staging")))
        self.assertFalse(os.path.exists(
            os.path.join(self._tmp.name, ".upd-backup")))

    def test_symlink_final_nao_grava_fora(self):
        definir_eu("alice")
        chave = instalar_chave_sintetica(self)
        fora = tempfile.mkdtemp(prefix="sm-symlink-fora2-")
        self.addCleanup(shutil.rmtree, fora, True)
        externo = os.path.join(fora, "segredo.txt")
        with open(externo, "wb") as f:
            f.write(b"segredo-original")
        gravar(self._tmp.name, "senderme.py", b"velho-1")
        os.symlink(externo, os.path.join(self._tmp.name, "link.txt"))
        novos = {"senderme.py": b"novo-1", "link.txt": b"invasor"}
        env, manif = assinar_release(chave, "99.0", novos)
        sm.update_manifest = manif
        sm.update_envelope = env
        sm.atualizando = True
        montar(novos)
        self.assertFalse(sm.finalizar_update())
        with open(externo, "rb") as f:
            self.assertEqual(f.read(), b"segredo-original")
        self.assertEqual(ler(self._tmp.name, "senderme.py"), b"velho-1")

    def test_recuperacao_nao_restaura_para_fora(self):
        definir_eu("alice")
        fora = tempfile.mkdtemp(prefix="sm-symlink-fora3-")
        self.addCleanup(shutil.rmtree, fora, True)
        externo = os.path.join(fora, "arquivo.txt")
        with open(externo, "wb") as f:
            f.write(b"fora-original")
        gravar(self._tmp.name, "senderme.py", b"novo-parcial")
        os.symlink(fora, os.path.join(self._tmp.name, "docs"))
        bkp = os.path.join(self._tmp.name, ".upd-backup")
        os.makedirs(os.path.join(bkp, "docs"))
        with open(os.path.join(bkp, "docs", "arquivo.txt"), "wb") as f:
            f.write(b"backup-bom")
        with open(os.path.join(bkp, "senderme.py"), "wb") as f:
            f.write(b"velho-1")
        with open(os.path.join(self._tmp.name, ".upd-pendente.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"v": "99.0",
                       "arquivos": ["senderme.py", "docs/arquivo.txt"],
                       "novos": [], "tinha_manifesto": False}, f)
        # senderme.py (caminho seguro) pode voltar; docs/arquivo.txt deve
        # ficar faltando sem tocar o externo, marcador preservado.
        self.assertTrue(sm.recuperar_update())
        with open(externo, "rb") as f:
            self.assertEqual(f.read(), b"fora-original")
        self.assertEqual(ler(self._tmp.name, "senderme.py"), b"velho-1")
        self.assertTrue(os.path.exists(
            os.path.join(self._tmp.name, ".upd-pendente.json")))


class CaminhoNormal(CasoIsolado):
    def test_dir_real_aplica_dentro(self):
        definir_eu("alice")
        chave = instalar_chave_sintetica(self)
        gravar(self._tmp.name, "senderme.py", b"velho-1")
        gravar(self._tmp.name, "docs/arquivo.txt", b"dentro-velho")
        novos = {"senderme.py": b"novo-1", "docs/arquivo.txt": b"dentro-novo"}
        env, manif = assinar_release(chave, "99.0", novos)
        sm.update_manifest = manif
        sm.update_envelope = env
        sm.atualizando = True
        montar(novos)
        self.assertTrue(sm.finalizar_update())
        self.assertEqual(ler(self._tmp.name, "senderme.py"), b"novo-1")
        self.assertEqual(ler(self._tmp.name, "docs/arquivo.txt"), b"dentro-novo")
        self.assertFalse(os.path.exists(
            os.path.join(self._tmp.name, ".upd-pendente.json")))

    def test_subdir_novo_aplica(self):
        definir_eu("alice")
        chave = instalar_chave_sintetica(self)
        gravar(self._tmp.name, "senderme.py", b"velho-1")
        novos = {"senderme.py": b"novo-1",
                 "novapasta/sub/arquivo.txt": b"novo-sub"}
        env, manif = assinar_release(chave, "99.0", novos)
        sm.update_manifest = manif
        sm.update_envelope = env
        sm.atualizando = True
        montar(novos)
        self.assertTrue(sm.finalizar_update())
        self.assertEqual(ler(self._tmp.name, "novapasta/sub/arquivo.txt"),
                         b"novo-sub")

    def test_falha_reverte_novo_em_subdir_e_poda(self):
        definir_eu("alice")
        chave = instalar_chave_sintetica(self)
        gravar(self._tmp.name, "senderme.py", b"velho-1")
        novos = {"senderme.py": b"novo-1",
                 "novapasta/sub/arquivo.txt": b"novo-sub"}
        env, manif = assinar_release(chave, "99.0", novos)
        sm.update_manifest = manif
        sm.update_envelope = env
        sm.atualizando = True
        montar(novos)
        real_replace = os.replace
        n = {"i": 0}

        def falhar_ultimo(src, dst, *a, **k):
            # troca staged->destino usa nome de um componente relativo a
            # fd fixado; tmp+replace (backup/marcador/envelope) termina
            # em .tmp e não conta.
            if isinstance(src, str) and not src.endswith(".tmp"):
                n["i"] += 1
                if n["i"] == len(novos):
                    raise OSError("disco cheio (simulado)")
            return real_replace(src, dst, *a, **k)

        with mock.patch("os.replace", side_effect=falhar_ultimo):
            self.assertFalse(sm.finalizar_update())
        self.assertEqual(ler(self._tmp.name, "senderme.py"), b"velho-1")
        self.assertFalse(os.path.exists(os.path.join(
            self._tmp.name, "novapasta", "sub", "arquivo.txt")))
        self.assertFalse(os.path.exists(os.path.join(
            self._tmp.name, "novapasta")))


if __name__ == "__main__":
    unittest.main()
