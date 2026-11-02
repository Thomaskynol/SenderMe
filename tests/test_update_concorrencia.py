"""A: ofertas de update simultâneas — só 1 transação por vez (TDD red→green).

Escopo honesto: estado em memória + threads reais no mesmo processo, chave de
assinatura SINTÉTICA em tmp (nunca dono/privada.json, nunca dados/ real). O
download é um contador (não executa rede/escrita); o caminho P2P real com
restart exit 42 segue coberto em test_update_e2e_abc.py. Política exigida:
a 1ª oferta válida vence; ofertas simultâneas posteriores (versão igual ou
diferente) são rejeitadas sem mudar o estado; sem ordenação garantida entre
versões — só unicidade da transação.
"""
import threading
import unittest
from unittest import mock

import senderme as sm
from suporte import CasoIsolado, chave_teste


def instalar_chave_sintetica(tc):
    chave = chave_teste()
    n_hex = format(chave["n"], "x")
    p = mock.patch.multiple("senderme_app.estado", CHAVE_DONO_N=n_hex,
                            CHAVE_DONO_E=65537)
    p.start()
    tc.addCleanup(p.stop)
    return chave


def envelope(chave, versao):
    manifest = {"v": versao, "arquivos": [
        {"nome": "senderme.py", "tamanho": 1, "sha256": "0" * 64}]}
    sig = sm.assinar(sm.manifest_canonico(manifest), chave).hex()
    return {"manifest": manifest, "sig": sig}


class OfertasSimultaneas(CasoIsolado):
    def test_so_um_download_ativo_com_barreira_na_verificacao(self):
        """2 ofertas válidas ao mesmo tempo: 1 download, 1 manifesto."""
        chave = instalar_chave_sintetica(self)
        sm.atualizando = False
        barreira = threading.Barrier(2)
        import senderme_app.update as upd_mod
        real = upd_mod.conferir_manifest
        chamadas = []
        chamadas_lck = threading.Lock()

        def verificar(m, sig):
            valido = real(m, sig)
            try:
                barreira.wait(timeout=2)
            except threading.BrokenBarrierError:
                pass  # serializou antes de verificar: aceitável
            return valido

        def download():
            with chamadas_lck:
                chamadas.append(1)

        with mock.patch("senderme_app.update_proto.conferir_manifest",
                        side_effect=verificar), \
             mock.patch("senderme_app.update.baixar_update",
                        side_effect=download):
            ts = [threading.Thread(target=sm.receber_update_meta,
                                   args=(envelope(chave, v),))
                  for v in ("99.0", "100.0")]
            for t in ts:
                t.start()
            for t in ts:
                t.join(timeout=10)
            self.assertTrue(all(not t.is_alive() for t in ts),
                            "threads não terminaram")
        self.assertEqual(len(chamadas), 1,
                         "dois downloads operando no mesmo estado")
        self.assertTrue(sm.atualizando)
        self.assertIn(sm.update_manifest["v"], ("99.0", "100.0"))

    def test_oferta_com_transacao_ativa_rejeitada_igual_ou_diferente(self):
        """Com download em curso, nova oferta (mesma ou outra versão) não
        troca o manifesto nem inicia outro download."""
        chave = instalar_chave_sintetica(self)
        env99 = envelope(chave, "99.0")
        with mock.patch("senderme_app.update.baixar_update", lambda: None):
            sm.receber_update_meta(env99)
        self.assertTrue(sm.atualizando)
        self.assertEqual(sm.update_manifest["v"], "99.0")
        with mock.patch("senderme_app.update.baixar_update") as dl:
            sm.receber_update_meta(envelope(chave, "99.0"))  # igual
            sm.receber_update_meta(envelope(chave, "100.0"))  # diferente
            dl.assert_not_called()
        self.assertEqual(sm.update_manifest["v"], "99.0")
        self.assertEqual(sm.update_envelope, env99)


if __name__ == "__main__":
    unittest.main()
