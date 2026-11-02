"""Reoferta de update após falha/desconexão, com limite de frequência.

Escopo honesto: defeito LOCAL determinístico (nunca dono/privada.json,
nunca dados/ real, chaves sintéticas em tmp). A 1.10 marcava (peer, versão)
como "meta enviada" ANTES de enviar e engolia o erro (`except: pass`):
qualquer falha na primeira oferta bloqueava repetição até reiniciar quem
oferece. Exigido: marcar só após envio confirmado; nova oferta após falha
ou reconexão; teto de frequência por peer (sem tempestade); versões iguais
ou mais novas nunca disparam oferta; concorrência não duplica; download
retenta chunks faltantes em rodadas limitadas.

Escrito ANTES da correção (TDD red→green). Rede P2P real + restart de
verdade seguem em test_update_e2e_abc.py (classe ReinicioAposQueda).
"""
import os
import sys
import threading
import time
import unittest
from unittest import mock

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "tests"))
sys.path.insert(0, RAIZ)

import suporte  # noqa: E402
import senderme as sm  # noqa: E402
import senderme_app.update as upd_mod  # noqa: E402
from suporte import CasoIsolado, definir_eu, FakeSock, quadros  # noqa: E402

VELHA = "1.9"  # menor que a VERSAO real de teste (1.10) em tupla


def esperar(cond, limite=10.0):
    fim = time.time() + limite
    while time.time() < fim:
        if cond():
            return True
        time.sleep(0.05)
    return bool(cond())


class BaseReoferta(CasoIsolado):
    def setUp(self):
        super().setUp()
        definir_eu("alice")
        upd_mod._ULTIMA_TENTATIVA.clear()
        upd_mod._META_SOCK.clear()
        # cooldown REAL (10 s): os testes de retentativa limpam
        # _ULTIMA_TENTATIVA antes da segunda ver; os de frequência
        # exigem o teto de verdade.

    def armar_peer(self, sock):
        pid = "peer-remoto-sintetico"
        sm.conns.setdefault(pid, set()).add(sock)
        sm.sockets_vivos.add(sock)
        return pid

    def tratar(self, pid, sock, v=VELHA):
        sm.tratar_ver(pid, sock, v)


class FalhaInicialRetenta(BaseReoferta):
    def test_falha_nao_marca_e_segunda_ver_reenvia(self):
        ruim = FakeSock()

        def falhar(b):
            raise OSError("sendall falhou (simulado)")
        ruim.sendall = falhar
        pid = self.armar_peer(ruim)
        self.tratar(pid, ruim)
        # dá tempo da thread de oferta falhar sem marcar
        time.sleep(1.0)
        self.assertNotIn((pid, VELHA), sm.meta_enviada)
        # reconexão: socket válido no lugar, mesma versão anunciada de novo
        sm.conns[pid].discard(ruim)
        sm.sockets_vivos.discard(ruim)
        bom = FakeSock()
        sm.conns[pid].add(bom)
        sm.sockets_vivos.add(bom)
        upd_mod._ULTIMA_TENTATIVA.clear()
        self.tratar(pid, bom)
        self.assertTrue(
            esperar(lambda: len(quadros(bom)) == 1),
            "segunda oferta não saiu após a falha inicial")
        self.assertEqual(quadros(bom)[0]["t"], "update_meta")
        self.assertIn((pid, VELHA), sm.meta_enviada)

    def test_sucesso_marca_uma_vez(self):
        sock = FakeSock()
        pid = self.armar_peer(sock)
        self.tratar(pid, sock)
        self.assertTrue(esperar(lambda: len(quadros(sock)) == 1))
        self.assertIn((pid, VELHA), sm.meta_enviada)


class QuedaEvolucao(BaseReoferta):
    def test_reconexao_com_sock_morto_reoferta(self):
        s1 = FakeSock()
        pid = self.armar_peer(s1)
        self.tratar(pid, s1)
        self.assertTrue(esperar(lambda: len(quadros(s1)) == 1))
        self.assertIn((pid, VELHA), sm.meta_enviada)
        # queda: socket da entrega morreu; peer volta em outro socket
        sm.conns[pid].discard(s1)
        sm.sockets_vivos.discard(s1)
        s2 = FakeSock()
        sm.conns[pid].add(s2)
        sm.sockets_vivos.add(s2)
        self.tratar(pid, s2)
        self.assertTrue(
            esperar(lambda: len(quadros(s2)) == 1),
            "sem reoferta após a queda da conexão de entrega")
        self.assertEqual(quadros(s2)[0]["t"], "update_meta")

    def test_sem_conexao_nao_marca_e_retenta_depois(self):
        pid = "peer-fantasma"
        fantasma = FakeSock()  # nunca registrado em conns
        self.tratar(pid, fantasma)
        time.sleep(1.0)
        self.assertNotIn((pid, VELHA), sm.meta_enviada)
        bom = FakeSock()
        self.armar_peer2(pid, bom)
        upd_mod._ULTIMA_TENTATIVA.clear()
        self.tratar(pid, bom)
        self.assertTrue(esperar(lambda: len(quadros(bom)) == 1))

    def armar_peer2(self, pid, sock):
        sm.conns.setdefault(pid, set()).add(sock)
        sm.sockets_vivos.add(sock)


class Versoes(BaseReoferta):
    def test_versao_igual_nunca_oferta(self):
        sock = FakeSock()
        pid = self.armar_peer(sock)
        self.tratar(pid, sock, v=sm.VERSAO)
        time.sleep(1.0)
        self.assertEqual(quadros(sock), [])
        self.assertEqual(sm.meta_enviada, set())

    def test_versao_nova_nunca_oferta(self):
        sock = FakeSock()
        pid = self.armar_peer(sock)
        self.tratar(pid, sock, v="99.99")
        time.sleep(1.0)
        self.assertEqual(quadros(sock), [])


class FrequenciaEConcorrencia(BaseReoferta):
    def test_ver_repetida_na_mesma_conexao_nao_tempesta(self):
        sock = FakeSock()
        pid = self.armar_peer(sock)
        for _ in range(5):
            self.tratar(pid, sock)
        self.assertTrue(esperar(lambda: len(quadros(sock)) == 1))
        time.sleep(1.0)
        self.assertEqual(len(quadros(sock)), 1,
                         "tempestade de ofertas na mesma conexão")

    def test_ver_simultaneas_uma_oferta(self):
        sock = FakeSock()
        pid = self.armar_peer(sock)
        ts = [threading.Thread(target=self.tratar, args=(pid, sock))
              for _ in range(8)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(timeout=10)
        self.assertTrue(all(not t.is_alive() for t in ts))
        self.assertTrue(esperar(lambda: len(quadros(sock)) == 1))
        time.sleep(0.5)
        self.assertEqual(len(quadros(sock)), 1,
                         "ofertas duplicadas sob concorrência")


class DownloadRetenta(CasoIsolado):
    def test_chunks_faltantes_repedidos_em_nova_rodada(self):
        import hashlib
        import socket as _socket
        import tempfile
        definir_eu("alice")
        chave = suporte.chave_teste()
        n_hex = format(chave["n"], "x")
        p = mock.patch.multiple("senderme_app.estado", CHAVE_DONO_N=n_hex,
                                CHAVE_DONO_E=65537)
        p.start()
        self.addCleanup(p.stop)
        upd_mod._ULTIMA_TENTATIVA.clear()
        upd_mod._META_SOCK.clear()
        blob = b"release-bytes-" * 40000  # ~560 KB: 2 chunks de 512 KB
        nome = "config.py"
        srv = tempfile.mkdtemp(prefix="sm-serv-")
        self.addCleanup(lambda: __import__("shutil").rmtree(srv, True))
        with open(os.path.join(srv, nome), "wb") as f:
            f.write(blob)
        manif = {"v": "99.0", "arquivos": [
            {"nome": nome, "tamanho": len(blob),
             "sha256": hashlib.sha256(blob).hexdigest()}]}
        env = {"manifest": manif,
               "sig": sm.assinar(sm.manifest_canonico(manif), chave).hex()}
        with open(os.path.join(self._tmp.name, nome), "wb") as f:
            f.write(b"velho")
        velho_codigo = sm.DIR_CODIGO
        sm.DIR_CODIGO = srv
        a, b = _socket.socketpair()
        b.settimeout(10)
        pedidos = []
        pedidos_lck = threading.Lock()
        real_enviar = upd_mod.enviar
        nfalhas = {"n": 0}

        def enviar_flaky(c, q):
            # os 2 primeiros chunks se perdem na volta (perda simulada);
            # as requisições chegam e são repedidas na rodada seguinte
            if q.get("t") == "update_chunk" and nfalhas["n"] < 2:
                nfalhas["n"] += 1
                raise OSError("rede instável (simulada)")
            return real_enviar(c, q)

        pronto = threading.Event()

        def servo():
            try:
                while not pronto.is_set():
                    try:
                        q = sm.ler_quadro(b)
                    except Exception:
                        continue
                    if not isinstance(q, dict):
                        continue
                    if q.get("t") == "update_get":
                        with pedidos_lck:
                            pedidos.append((q.get("nome"), q.get("idx")))
                        sm.servir_update("peerB", b, q)
            except Exception:
                pass

        def leitor():
            # o que em produção é o tcp.ler_loop: quadros que chegam no
            # socket do receptor viram chunks montados em memória.
            a.settimeout(5)
            try:
                while not pronto.is_set():
                    try:
                        q = sm.ler_quadro(a)
                    except Exception:
                        continue
                    if isinstance(q, dict) and q.get("t") == "update_chunk":
                        sm.receber_update_chunk(q)
            except Exception:
                pass

        fio = threading.Thread(target=servo, daemon=True)
        fio2 = threading.Thread(target=leitor, daemon=True)
        try:
            sm.update_manifest = manif
            sm.update_envelope = env
            sm.atualizando = True
            sm.update_montando.clear()
            sm.conns["peerB"] = {a}
            sm.sockets_vivos.add(a)
            with mock.patch.object(upd_mod, "enviar",
                                   side_effect=enviar_flaky), \
                 mock.patch("senderme_app.update_proto.enviar",
                            side_effect=enviar_flaky), \
                 mock.patch("os._exit") as saida:
                fio.start()
                fio2.start()
                sm.baixar_update()
                self.assertTrue(
                    esperar(lambda: saida.called, limite=90),
                    "download não concluiu após a perda inicial")
                saida.assert_called_once_with(42)
            with pedidos_lck:
                idx0 = [i for (n, i) in pedidos if i == 0]
            self.assertGreaterEqual(
                len(idx0), 2,
                "chunk 0 perdido não foi repedido em nova rodada")
        finally:
            pronto.set()
            sm.DIR_CODIGO = velho_codigo
            sm.conns.pop("peerB", None)
            sm.sockets_vivos.discard(a)
            for s in (a, b):
                try:
                    s.close()
                except OSError:
                    pass


if __name__ == "__main__":
    unittest.main()
