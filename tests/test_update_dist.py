"""Update assinado + distribuição: manifesto, assinador e regras (comportamental).

A lista de arquivos é dinâmica (ARQUIVOS_UPDATE em senderme_app/meta.py, fonte
única): nada de número fixo. Comportamento de launcher/build é testado com
execução real em test_dist_boot.py; aqui ficam manifesto, assinatura e regras.
"""
import hashlib
import importlib.util
import json
import os
import unittest

import senderme as sm
from suporte import CasoIsolado, definir_eu

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def carregar_assinador():
    spec = importlib.util.spec_from_file_location(
        "assinar_update", os.path.join(RAIZ, "dono", "assinar_update.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class VersaoManifestLocal(CasoIsolado):
    def test_manifest_bate_com_disco_e_assinatura(self):
        with open(os.path.join(RAIZ, "update-manifest.json"), encoding="utf-8") as f:
            d = json.load(f)
        self.assertEqual(d["manifest"]["v"], sm.VERSAO)
        self.assertEqual([a["nome"] for a in d["manifest"]["arquivos"]],
                         sm.ARQUIVOS_UPDATE)
        for a in d["manifest"]["arquivos"]:
            with open(os.path.join(RAIZ, a["nome"]), "rb") as f:
                blob = f.read()
            self.assertEqual(len(blob), a["tamanho"], a["nome"])
            self.assertEqual(hashlib.sha256(blob).hexdigest(), a["sha256"], a["nome"])
        self.assertTrue(sm.conferir_manifest(d["manifest"], d["sig"]))

    def test_assinador_usa_a_mesma_fonte_unica(self):
        mod = carregar_assinador()
        self.assertEqual(mod.ARQUIVOS, sm.ARQUIVOS_UPDATE)
        import senderme_app.meta as meta
        self.assertIs(mod.ARQUIVOS, meta.ARQUIVOS_UPDATE)
        self.assertEqual(mod.versao_do_codigo(), sm.VERSAO)

    def test_manifest_canonico_deterministico(self):
        m1 = {"v": "1.3", "arquivos": [{"nome": "a", "tamanho": 1, "sha256": "x"}]}
        m2 = {"arquivos": [{"sha256": "x", "tamanho": 1, "nome": "a"}], "v": "1.3"}
        self.assertEqual(sm.manifest_canonico(m1), sm.manifest_canonico(m2))

    def test_ver_tupla(self):
        self.assertGreater(sm.ver_tupla("1.10"), sm.ver_tupla("1.3"))
        self.assertEqual(sm.ver_tupla("1.3"), sm.ver_tupla("1.3"))
        self.assertEqual(sm.ver_tupla("lixo"), (0,))


class RegrasUpdate(CasoIsolado):
    def test_nome_update_ok(self):
        for bom in ("senderme.py", "senderme_app/update.py",
                    "docs/01-produto.md", "a" * 120):
            self.assertTrue(sm.nome_update_ok(bom), bom)
        for ruim in ("", "../x", "/abs", "a\\b", "a/../b", "docs/",
                     "senderme_app/", "x" * 121, "a\rb", "a\nb"):
            self.assertFalse(sm.nome_update_ok(ruim), repr(ruim))

    def test_meta_versao_menor_ou_igual_rejeitada_sem_efeito(self):
        definir_eu("alice")
        for v in ("0.1", sm.VERSAO):
            sm.receber_update_meta({"manifest": {"v": v, "arquivos": []}, "sig": "00"})
            self.assertFalse(sm.atualizando)
            self.assertIsNone(sm.update_manifest)

    def test_meta_nova_com_sig_invalida_rejeitada(self):
        definir_eu("alice")
        sm.receber_update_meta({"manifest": {"v": "99.0", "arquivos": []}, "sig": "00"})
        self.assertFalse(sm.atualizando)


class PreservaDocsAntigos(CasoIsolado):
    """Arquivos que saíram do conjunto (README/docs): o update novo não apaga.

    Instalações antigas MANTÊM seus docs no disco — o updater só escreve os
    arquivos do manifesto novo e nunca remove arquivos de usuário.
    """

    def test_finalizar_update_novo_mantem_docs_antigos(self):
        from test_update_falhas import (instalar_chave_sintetica,
                                        assinar_release, montar_no_estado,
                                        gravar, ler)
        definir_eu("alice")
        chave = instalar_chave_sintetica(self)
        velhos = {"README.md": b"doc meu\n",
                  "docs/01-produto.md": b"produto meu\n",
                  "docs/02-arquitetura.md": b"arq minha\n",
                  "docs/03-progresso.md": b"prog meu\n"}
        for nome, blob in velhos.items():
            gravar(sm.PASTA, nome, blob)
        novos = {"senderme.py": b"novo-py\n", "config.py": b"novo-cfg\n"}
        env, manif = assinar_release(chave, "99.0", novos)
        sm.update_manifest = manif
        sm.update_envelope = env
        sm.atualizando = True
        sm.update_montando.clear()
        montar_no_estado(novos)
        self.assertTrue(sm.finalizar_update())
        for nome, blob in velhos.items():
            self.assertEqual(ler(sm.PASTA, nome), blob, nome)
        for nome, blob in novos.items():
            self.assertEqual(ler(sm.PASTA, nome), blob, nome)

    def test_servir_update_recusa_docs_fora_do_conjunto(self):
        from suporte import FakeSock, quadros
        sock = FakeSock()
        sm.servir_update("pid-sonda", sock,
                         {"nome": "docs/01-produto.md", "idx": 0})
        self.assertEqual(quadros(sock), [])


class TerceirosViajaNoUpdate(CasoIsolado):
    """TERCEIROS.md chega pelo update; docs antigos continuam preservados."""

    AVISO = "TERCEIROS.md"

    def test_aviso_no_conjunto_e_nome_ok(self):
        self.assertIn(self.AVISO, sm.ARQUIVOS_UPDATE)
        self.assertTrue(sm.nome_update_ok(self.AVISO))

    def test_finalizar_entrega_aviso_e_preserva_docs(self):
        from test_update_falhas import (instalar_chave_sintetica,
                                        assinar_release, montar_no_estado,
                                        gravar, ler)
        definir_eu("alice")
        chave = instalar_chave_sintetica(self)
        velhos = {"README.md": b"doc meu\n",
                  "docs/01-produto.md": b"produto meu\n"}
        for nome, blob in velhos.items():
            gravar(sm.PASTA, nome, blob)
        with open(os.path.join(RAIZ, self.AVISO), "rb") as f:
            aviso_novo = f.read()
        novos = {"senderme.py": b"novo-py\n", self.AVISO: aviso_novo}
        env, manif = assinar_release(chave, "99.0", novos)
        sm.update_manifest = manif
        sm.update_envelope = env
        sm.atualizando = True
        sm.update_montando.clear()
        montar_no_estado(novos)
        self.assertTrue(sm.finalizar_update())
        self.assertEqual(ler(sm.PASTA, self.AVISO), aviso_novo)
        for nome, blob in velhos.items():
            self.assertEqual(ler(sm.PASTA, nome), blob, nome)

    def test_servir_aviso_para_peer_antigo(self):
        from suporte import FakeSock, quadros
        sock = FakeSock()
        sm.servir_update("pid-sonda", sock, {"nome": self.AVISO, "idx": 0})
        got = quadros(sock)
        self.assertTrue(got, "peer antigo não recebeu %s" % self.AVISO)
        self.assertEqual(got[0].get("nome"), self.AVISO)


if __name__ == "__main__":
    unittest.main()
