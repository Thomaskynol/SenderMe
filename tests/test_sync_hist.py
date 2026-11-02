"""Caracterização: hist_req/hist (merge Lego) — inventário, sem DM, lote+pubs."""
import json
import os
import unittest

import senderme as sm
from suporte import (CasoIsolado, FakeSock, criar_como, definir_eu,
                     definir_par, quadros)


class HistReqResponde(CasoIsolado):
    def setUp(self):
        super().setUp()
        self.eu, self.chave = definir_eu("alice")
        self.peer, self.pchave = definir_par("bob")
        self.m1 = sm.criar_evento("msg", "um")
        sm.processar(self.m1, disco=False)
        self.m2 = sm.criar_evento("msg", "dois")
        sm.processar(self.m2, disco=False)
        self.dm = sm.criar_evento("dm", "segredo", para=self.peer["id"])
        sm.processar(self.dm, disco=False)
        # evento do par, para pubs
        self.p1 = criar_como(self.peer, "bob", "msg", "do par")
        sm.processar(self.p1, disco=False)

    def pedir(self, tem):
        sock = FakeSock()
        sm.tratar_quadro({"t": "hist_req", "tem": tem}, self.peer["id"], sock)
        (resp,) = quadros(sock)
        return resp

    def test_com_inventario_responde_so_falta(self):
        resp = self.pedir([self.m1["mid"]])
        mids = {e["mid"] for e in resp["evs"]}
        self.assertIn(self.m2["mid"], mids)
        self.assertIn(self.p1["mid"], mids)
        self.assertNotIn(self.m1["mid"], mids)

    def test_nunca_traz_dm(self):
        resp = self.pedir([self.m1["mid"]])
        self.assertNotIn(self.dm["mid"], {e["mid"] for e in resp["evs"]})
        resp2 = self.pedir([])
        self.assertNotIn(self.dm["mid"], {e["mid"] for e in resp2["evs"]})
        for e in resp2["evs"]:
            self.assertIsNone(e.get("para"))

    def test_sem_inventario_janela_dos_ultimos(self):
        resp = self.pedir(None)
        mids = {e["mid"] for e in resp["evs"]}
        self.assertEqual(mids, {self.m1["mid"], self.m2["mid"], self.p1["mid"]})

    def test_pubs_traz_chave_do_autor(self):
        resp = self.pedir([])
        ids = {p["id"] for p in resp["pubs"]}
        self.assertIn(self.peer["id"], ids)


class TratarHist(CasoIsolado):
    def test_persiste_lote_aplica_pubs_e_ignora_dm_alheia(self):
        eu, _ = definir_eu("alice")
        peer_idt, pchave = definir_par("bob")  # sem registrar: chega via pubs
        sm.conhecidos.clear()
        sm.nick_de.clear()
        p1 = criar_como(peer_idt, "bob", "msg", "nova")
        dm_mim = criar_como(peer_idt, "bob", "dm", "psst", para=eu["id"])
        terceiro, _ = definir_par("carol")
        dm_outro = criar_como(peer_idt, "bob", "dm", "nada", para=terceiro["id"])
        # processa a "duplicada" antes para simular já-vista
        sm.conhecidos[peer_idt["id"]] = {"n": pchave["n"], "e": pchave["e"], "nick": "bob"}
        pubs = [{"id": peer_idt["id"], "n": format(pchave["n"], "x"), "e": pchave["e"]}]
        sm.conhecidos.clear()  # finge que a chave ainda não era conhecida
        sm.tratar_hist([p1, dict(p1), dm_mim, dm_outro,
                        dict(p1, txt="adulterado")], pubs, "algum-pid")
        mids = {e["mid"] for e in sm.historico}
        self.assertIn(p1["mid"], mids)
        self.assertIn(dm_mim["mid"], mids)  # DM para mim: aplico, não propago
        self.assertNotIn(dm_outro["mid"], mids)  # DM alheia: nunca guardo
        self.assertNotIn("adulterado", [e.get("txt") for e in sm.historico])
        # lote em uma escrita: só os novos no arquivo
        with open(os.path.join(sm.DADOS, "historico.jsonl"), encoding="utf-8") as f:
            linhas = [json.loads(l) for l in f if l.strip()]
        self.assertEqual({e["mid"] for e in linhas}, {p1["mid"], dm_mim["mid"]})

    def test_puxa_conteudo_de_file_faltante(self):
        eu, _ = definir_eu("alice")
        peer_idt, pchave = definir_par("bob")
        blob = b"conteudo-arquivo"
        import hashlib as _h
        ev = criar_como(peer_idt, "bob", "file", "leg",
                        arq={"nome": "f.bin", "tamanho": len(blob),
                             "sha256": _h.sha256(blob).hexdigest()})
        sm.tratar_hist([ev], [{"id": peer_idt["id"], "n": format(pchave["n"], "x"),
                                                                 "e": pchave["e"]}], "x")
        self.assertIn(ev["mid"], sm.pedidos_arq)  # pediu o conteúdo


if __name__ == "__main__":
    unittest.main()
