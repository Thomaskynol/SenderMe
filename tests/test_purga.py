"""Caracterização: purga 24h + teto 60MB (conteúdo sai, metadados ficam)."""
import json
import os
import unittest

import senderme as sm
import senderme_app.arquivos as _arqx
from suporte import CasoIsolado, definir_eu


class PurgarHistorico(CasoIsolado):
    def test_descarta_mais_24h_e_reconstroi_vistos(self):
        eu, _ = definir_eu("alice")
        velha = sm.criar_evento("msg", "velha")
        velha["ts"] = int(sm.agora()) - sm.RETENCAO - 10
        from suporte import reassinar
        reassinar(velha, eu)
        # insere direto (processar descartaria): retrata dado já em disco
        sm.historico.append(velha)
        sm.vistos.add(velha["mid"])
        nova = sm.criar_evento("msg", "nova")
        sm.processar(nova, disco=False)
        sm.purgar()
        mids = {e["mid"] for e in sm.historico}
        self.assertNotIn(velha["mid"], mids)
        self.assertIn(nova["mid"], mids)
        self.assertEqual(sm.vistos, mids)
        with open(os.path.join(sm.DADOS, "historico.jsonl"), encoding="utf-8") as f:
            self.assertEqual(len([l for l in f if l.strip()]), 1)


class PurgarArquivos(CasoIsolado):
    def _file_ev(self, txt, blob, idade_s=0):
        import hashlib as _h
        ev = sm.criar_evento_file(txt, txt + ".bin", len(blob),
                                  _h.sha256(blob).hexdigest())
        if idade_s:
            ev["ts"] = int(sm.agora()) - idade_s
            from suporte import reassinar
            reassinar(ev, {"n": sm.ident["n"], "e": sm.ident["e"],
                           "d": sm.ident["d"]})
        sm.historico.append(ev)
        sm.salvar_bytes_arquivo(ev["mid"], blob)
        return ev

    def test_idade_remove_bin_mantem_metadados(self):
        definir_eu("alice")
        velha = self._file_ev("velha", b"123", idade_s=sm.RETENCAO + 10)
        nova = self._file_ev("nova", b"456")
        sm.purgar_arquivos()
        self.assertIsNone(sm.ler_bytes_arquivo(velha["mid"]))
        self.assertEqual(sm.ler_bytes_arquivo(nova["mid"]), b"456")
        self.assertIsNotNone(sm.evento_por_mid(velha["mid"]))  # metadados ficam

    def test_orfao_sem_evento_usam_mtime(self):
        definir_eu("alice")
        os.makedirs(sm.DIR_ARQ, exist_ok=True)
        velho = os.path.join(sm.DIR_ARQ, "x" * 64 + ".bin")
        with open(velho, "wb") as f:
            f.write(b"o")
        t = sm.agora() - sm.RETENCAO - 10
        os.utime(velho, (t, t))
        sm.purgar_arquivos()
        self.assertFalse(os.path.exists(velho))

    def test_teto_remove_mais_antigos_primeiro(self):
        definir_eu("alice")
        agora = int(sm.agora())
        evs = []
        for i, txt in enumerate(("a", "b", "c")):
            evs.append(self._file_ev(txt, b"x" * 20))
            evs[-1]["ts"] = agora - (30 - i * 10)  # a mais velho, c mais novo
        teto, _arqx.MAX_ARQUIVOS_TOTAL = _arqx.MAX_ARQUIVOS_TOTAL, 45
        try:
            sm.purgar_arquivos()
        finally:
            _arqx.MAX_ARQUIVOS_TOTAL = teto
        self.assertIsNone(sm.ler_bytes_arquivo(evs[0]["mid"]))
        self.assertEqual(sm.ler_bytes_arquivo(evs[2]["mid"]), b"x" * 20)
        self.assertLessEqual(sm.total_arquivos(), 45)


if __name__ == "__main__":
    unittest.main()
