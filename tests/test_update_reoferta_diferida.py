"""Reoferta diferida após cooldown suprimir oferta (1.12).

Escopo honesto: defeito LOCAL determinístico (tmp+sintéticos, nunca
dono/privada.json, nunca dados/ real). Hoje `tratar_ver` retorna no
cooldown sem agendar nada (update_proto.py:94-96); após o intervalo,
sem novo `ver`, não há oferta em conexão aberta (só nova conexão
salva). Exigido: quando o cooldown suprimir oferta p/ peer antigo
ainda conectado, agendar UMA tentativa diferida p/ o fim do intervalo
(timer/thread daemon), que reoferta se peer/socket/versão ainda
justificarem; cancela no disconnect; teto de frequência e sem
duplicadas (1 oferta por (peer,versão)).

Escrito ANTES da correção (TDD red→green). O teste da espera real NÃO
limpa o cooldown manualmente; os rápidos usam relógio simulado
(cooldown curto via patch) + integração com agendamento real.
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
import senderme_app.update_proto as proto  # noqa: E402
from suporte import CasoIsolado, definir_eu, FakeSock, quadros  # noqa: E402

VELHA = "1.9"  # menor que a VERSAO real (1.11) em tupla


def esperar(cond, limite=10.0):
    fim = time.time() + limite
    while time.time() < fim:
        if cond():
            return True
        time.sleep(0.05)
    return bool(cond())


def _pendentes():
    d = getattr(proto, "_REOFERTA_AGENDADA", None)
    return d if isinstance(d, dict) else {}


class BaseDiferida(CasoIsolado):
    def setUp(self):
        super().setUp()
        definir_eu("alice")
        d = getattr(proto, "_REOFERTA_AGENDADA", None)
        if isinstance(d, dict):
            with sm.L:
                for _pid, ent in list(d.items()):
                    try:
                        t = ent[0] if isinstance(ent, tuple) else ent
                        t.cancel()
                    except Exception:
                        pass
                d.clear()
        proto._ULTIMA_TENTATIVA.clear()
        proto._META_SOCK.clear()

    def tearDown(self):
        d = getattr(proto, "_REOFERTA_AGENDADA", None)
        if isinstance(d, dict):
            with sm.L:
                for _pid, ent in list(d.items()):
                    try:
                        t = ent[0] if isinstance(ent, tuple) else ent
                        t.cancel()
                    except Exception:
                        pass
                d.clear()
        super().tearDown()

    def armar(self, pid, sock):
        sm.conns.setdefault(pid, set()).add(sock)
        sm.sockets_vivos.add(sock)
        return pid

    def desarmar(self, pid, sock):
        sm.conns.get(pid, set()).discard(sock)
        sm.sockets_vivos.discard(sock)
        canc = getattr(proto, "cancelar_reoferta", None)
        if callable(canc):
            try:
                canc(pid, sock)
            except Exception:
                pass


class FalhaReconexaoDentroCooldown(BaseDiferida):
    def test_reoferta_diferida_mesma_conexao_sem_limpar(self):
        # cooldown REAL (10 s); NENHUM clear após a 2ª ver (espera real).
        ruim = FakeSock()

        def falhar(b):
            raise OSError("sendall falhou (simulado)")

        ruim.sendall = falhar
        pid = "peer-sonda-diferida"
        self.armar(pid, ruim)
        sm.tratar_ver(pid, ruim, VELHA)
        time.sleep(1.0)  # thread de oferta falha sem marcar
        self.assertNotIn((pid, VELHA), sm.meta_enviada)
        # reconexão DENTRO do cooldown, com novo anúncio (suprimido+teto)
        self.desarmar(pid, ruim)
        bom = FakeSock()
        self.armar(pid, bom)
        sm.tratar_ver(pid, bom, VELHA)
        time.sleep(1.0)
        # sem tempestade: nada imediato na 2ª conexão
        self.assertEqual(quadros(bom), [])
        # após o intervalo, UMA oferta na MESMA conexão, sem 2º anúncio
        self.assertTrue(
            esperar(lambda: len(quadros(bom)) == 1, limite=15.0),
            "oferta diferida não chegou na mesma conexão após o cooldown")
        self.assertEqual(quadros(bom)[0]["t"], "update_meta")
        time.sleep(1.0)
        self.assertEqual(len(quadros(bom)), 1,
                         "duplicada após a diferida")


class SemSegundoAnuncio(BaseDiferida):
    def test_falha_unica_agenda_sem_reanuncio(self):
        # relógio simulado (cooldown curto) + agendamento real (Timer).
        with mock.patch.object(proto, "_COOLDOWN_REOFERTA", 0.4):
            sock = FakeSock()
            pid = "peer-sem-reanuncio"
            self.armar(pid, sock)
            chamadas = {"n": 0}
            real = proto.enviar

            def flaky(c, q):
                if q.get("t") == "update_meta" and chamadas["n"] == 0:
                    chamadas["n"] += 1
                    raise OSError("1a falha injetada (simulada)")
                return real(c, q)

            with mock.patch.object(proto, "enviar", side_effect=flaky):
                sm.tratar_ver(pid, sock, VELHA)
                # SEM 2º anúncio: a diferida chega na MESMA conexão
                self.assertTrue(
                    esperar(lambda: len(quadros(sock)) == 1, limite=5.0),
                    "falha única sem reanúncio não reagendou")
                self.assertEqual(quadros(sock)[0]["t"], "update_meta")


class QuedaAntes(BaseDiferida):
    def test_queda_antes_da_diferida_nada_envia(self):
        with mock.patch.object(proto, "_COOLDOWN_REOFERTA", 0.4):
            ruim = FakeSock()

            def falhar(b):
                raise OSError("sendall falhou (simulado)")

            ruim.sendall = falhar
            pid = "peer-queda-antes"
            self.armar(pid, ruim)
            sm.tratar_ver(pid, ruim, VELHA)
            time.sleep(0.6)
            self.assertNotIn((pid, VELHA), sm.meta_enviada)
            self.desarmar(pid, ruim)
            bom = FakeSock()
            self.armar(pid, bom)
            sm.tratar_ver(pid, bom, VELHA)  # suprimida: agenda diferida
            # peer cai ANTES da tentativa agendada
            self.desarmar(pid, bom)
            time.sleep(1.2)  # passa o intervalo
            self.assertEqual(quadros(bom), [],
                             "oferta saiu após o disconnect")
            self.assertNotIn((pid, VELHA), sm.meta_enviada)


class ConcorrenciaDiferida(BaseDiferida):
    def test_concorrentes_uma_oferta_mesmo_apos_intervalo(self):
        with mock.patch.object(proto, "_COOLDOWN_REOFERTA", 0.4):
            sock = FakeSock()
            pid = "peer-conc-diferida"
            self.armar(pid, sock)
            ts = [threading.Thread(target=sm.tratar_ver,
                                   args=(pid, sock, VELHA))
                  for _ in range(8)]
            for t in ts:
                t.start()
            for t in ts:
                t.join(timeout=10)
            self.assertTrue(all(not t.is_alive() for t in ts))
            self.assertTrue(esperar(lambda: len(quadros(sock)) == 1,
                                    limite=5.0))
            time.sleep(1.2)  # passa o intervalo da eventual diferida
            self.assertEqual(len(quadros(sock)), 1,
                             "duplicada após concorrência+intervalo")


class VersoesCancelam(BaseDiferida):
    def test_versao_igual_cancela_pendente(self):
        with mock.patch.object(proto, "_COOLDOWN_REOFERTA", 0.4):
            ruim = FakeSock()

            def falhar(b):
                raise OSError("sendall falhou (simulado)")

            ruim.sendall = falhar
            pid = "peer-versao-cancela"
            self.armar(pid, ruim)
            sm.tratar_ver(pid, ruim, VELHA)
            time.sleep(0.6)
            self.desarmar(pid, ruim)
            bom = FakeSock()
            self.armar(pid, bom)
            sm.tratar_ver(pid, bom, VELHA)  # suprimida: agenda
            # peer agora anuncia versão igual: pendente caduca
            sm.tratar_ver(pid, bom, sm.VERSAO)
            time.sleep(1.2)
            self.assertEqual(quadros(bom), [],
                             "oferta saiu após peer ficar igual")

    def test_versao_nova_cancela_pendente(self):
        with mock.patch.object(proto, "_COOLDOWN_REOFERTA", 0.4):
            ruim = FakeSock()

            def falhar(b):
                raise OSError("sendall falhou (simulado)")

            ruim.sendall = falhar
            pid = "peer-nova-cancela"
            self.armar(pid, ruim)
            sm.tratar_ver(pid, ruim, VELHA)
            time.sleep(0.6)
            self.desarmar(pid, ruim)
            bom = FakeSock()
            self.armar(pid, bom)
            sm.tratar_ver(pid, bom, VELHA)
            sm.tratar_ver(pid, bom, "99.99")
            time.sleep(1.2)
            self.assertEqual(quadros(bom), [],
                             "oferta saiu após peer ficar mais novo")


class MultiplosSockets(BaseDiferida):
    def test_um_socket_morre_outro_recebe(self):
        with mock.patch.object(proto, "_COOLDOWN_REOFERTA", 0.5):
            s1, s2 = FakeSock(), FakeSock()
            pid = "peer-multi-sock"
            self.armar(pid, s1)
            self.armar(pid, s2)
            chamadas = {"n": 0}
            real = proto.enviar

            def flaky(c, q):
                if q.get("t") == "update_meta" and chamadas["n"] == 0:
                    chamadas["n"] += 1
                    raise OSError("1a falha injetada (simulada)")
                return real(c, q)

            with mock.patch.object(proto, "enviar", side_effect=flaky):
                sm.tratar_ver(pid, s1, VELHA)
                # um socket morre na espera; o outro segue vivo
                self.desarmar(pid, s1)
                total = lambda: len(quadros(s2)) + len(quadros(s1))
                self.assertTrue(
                    esperar(lambda: total() >= 1, limite=5.0),
                    "diferida não saiu no socket sobrevivente")
                self.assertEqual(len(quadros(s2)), 1)


class DownloadRetomada(BaseDiferida):
    def test_interrupcao_retoma_em_nova_rodada(self):
        # interrupção no download + retomada (roda curta do mesmo
        # mecanismo de baixar_update já coberto em test_update_reoferta).
        import hashlib
        import socket as _socket
        definir_eu("alice")
        chave = suporte.chave_teste()
        n_hex = format(chave["n"], "x")
        p = mock.patch.multiple("senderme_app.estado", CHAVE_DONO_N=n_hex,
                                CHAVE_DONO_E=65537)
        p.start()
        self.addCleanup(p.stop)
        blob = b"retomada-bytes-" * 40000
        nome = "config.py"
        import tempfile
        srv = tempfile.mkdtemp(prefix="sm-dife-serv-")
        self.addCleanup(lambda: __import__("shutil").rmtree(srv, True))
        with open(os.path.join(srv, nome), "wb") as f:
            f.write(blob)
        manif = {"v": "99.0", "arquivos": [
            {"nome": nome, "tamanho": len(blob),
             "sha256": hashlib.sha256(blob).hexdigest()}]}
        env = {"manifest": manif,
               "sig": sm.assinar(sm.manifest_canonico(manif), chave).hex()}
        velho_codigo = sm.DIR_CODIGO
        sm.DIR_CODIGO = srv
        a, b = _socket.socketpair()
        b.settimeout(10)
        real_enviar = proto.enviar
        nfalhas = {"n": 0}

        def enviar_flaky(c, q):
            if q.get("t") == "update_chunk" and nfalhas["n"] < 1:
                nfalhas["n"] += 1
                raise OSError("interrupção simulada no meio")
            return real_enviar(c, q)

        pronto = threading.Event()

        def servo():
            try:
                while not pronto.is_set():
                    try:
                        q = sm.ler_quadro(b)
                    except Exception:
                        continue
                    if isinstance(q, dict) and q.get("t") == "update_get":
                        sm.servir_update("peerB-dife", b, q)
            except Exception:
                pass

        def leitor():
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
            sm.conns["peerB-dife"] = {a}
            sm.sockets_vivos.add(a)
            with mock.patch.object(
                    __import__("senderme_app.update", fromlist=["x"]),
                    "enviar", side_effect=enviar_flaky), \
                 mock.patch.object(proto, "enviar",
                                   side_effect=enviar_flaky), \
                 mock.patch("os._exit") as saida:
                fio.start()
                fio2.start()
                sm.baixar_update()
                self.assertTrue(
                    esperar(lambda: saida.called, limite=90),
                    "download não retomou após a interrupção")
                saida.assert_called_once_with(42)
        finally:
            pronto.set()
            sm.DIR_CODIGO = velho_codigo
            sm.conns.pop("peerB-dife", None)
            sm.sockets_vivos.discard(a)
            for s in (a, b):
                try:
                    s.close()
                except OSError:
                    pass


class P2PRealMesmaConexao(BaseDiferida):
    def test_oferta_diferida_mesma_conexao_sem_reanuncio(self):
        # P2P REAL entre processos: 1 conexão, 1 ver, só a 1ª falha
        # injetada (NÃO é falha de assinatura nem defeito de toda
        # desconexão). A oferta chega após o intervalo na MESMA conexão,
        # sem 2º anúncio nem 2ª conexão. Cooldown REAL (sem patch).
        import shutil
        import socket as _socket
        import struct
        import subprocess
        import tempfile
        self.assertEqual(os.getcwd(), RAIZ,
                         "cwd deve ser a raiz do projeto (absolutos)")
        os.environ["SENDERME_NO_BROADCAST"] = "1"
        definir_eu("servidor-novo")
        marca_dir = tempfile.mkdtemp(prefix="sm-dife-p2p-")
        self.addCleanup(shutil.rmtree, marca_dir, True)
        marca = os.path.join(marca_dir, "meta-chegou")
        srv = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        srv.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        srv.listen(8)
        porta = srv.getsockname()[1]
        self.addCleanup(srv.close)
        estado = {"aceitos": 0, "vers": 0, "metas_ok": 0}
        import senderme_app.tcp as tcp_mod
        orig_tratar = tcp_mod.tratar_ver
        orig_enviar = proto.enviar
        falhou = {"n": 0}
        inicio = time.time()

        def contar_ver(pid, sock, v):
            with sm.L:
                estado["vers"] += 1
            return orig_tratar(pid, sock, v)

        def flaky_enviar(sock, obj):
            if isinstance(obj, dict) and obj.get("t") == "update_meta" \
                    and falhou["n"] == 0:
                falhou["n"] += 1
                raise OSError("1a falha injetada no P2P (simulada)")
            r = orig_enviar(sock, obj)
            if isinstance(obj, dict) and obj.get("t") == "update_meta":
                with sm.L:
                    estado["metas_ok"] += 1
            return r

        cliente_src = (
            "import json,socket,struct,sys,time,random\n"
            "porta=%d\nmarca=%r\n"
            "def enviar(s,o):\n"
            " b=json.dumps(o).encode();s.sendall(struct.pack('!I',len(b))+b)\n"
            "def recn(s,n):\n"
            " b=bytearray()\n"
            " while len(b)<n:\n"
            "  c=s.recv(n-len(b))\n"
            "  if not c: raise ConnectionError('fechada')\n"
            "  b.extend(c)\n"
            " return bytes(b)\n"
            "def ler(s):\n"
            " n=struct.unpack('!I',recn(s,4))[0]\n"
            " return json.loads(recn(s,n).decode())\n"
            "s=socket.create_connection(('127.0.0.1',porta),timeout=10)\n"
            "s.settimeout(20)\n"
            "srv_pub=ler(s)\n"
            "n=random.getrandbits(512);e=65537\n"
            "sys.path.insert(0,%r)\n"
            "from crypto import fingerprint\n"
            "pid=fingerprint(n,e)\n"
            "enviar(s,{'t':'pub','id':pid,'n':format(n,'x'),'e':e})\n"
            "enviar(s,{'t':'ver','v':'1.9'})\n"
            "fim=time.time()+30\n"
            "while time.time()<fim:\n"
            " try: q=ler(s)\n"
            " except Exception: continue\n"
            " if isinstance(q,dict) and q.get('t')=='update_meta':\n"
            "  open(marca,'w').write('meta')\n"
            "  sys.exit(0)\n"
            "sys.exit(1)\n"
        ) % (porta, marca, RAIZ)
        cliente_path = os.path.join(marca_dir, "cliente.py")
        with open(cliente_path, "w", encoding="utf-8") as f:
            f.write(cliente_src)

        def aceitar():
            from senderme_app.transporte import preparar_socket, enviar, \
                fechar_socket
            try:
                while True:
                    try:
                        c, addr = srv.accept()
                    except OSError:
                        break
                    with sm.L:
                        estado["aceitos"] += 1
                    preparar_socket(c)
                    with sm.L:
                        sm.sockets_vivos.add(c)
                    try:
                        enviar(c, tcp_mod.msg_pub())
                    except Exception:
                        fechar_socket(c)
                        continue
                    tcp_mod.ler_loop(c, addr)
            except Exception:
                pass

        fio = threading.Thread(target=aceitar, daemon=True)
        with mock.patch.object(tcp_mod, "tratar_ver",
                               side_effect=contar_ver), \
             mock.patch.object(proto, "enviar",
                               side_effect=flaky_enviar):
            fio.start()
            env = dict(os.environ)
            env["SENDERME_NO_BROADCAST"] = "1"
            env["SENDERME_FIXOS"] = "127.0.0.1:%d" % porta
            proc = subprocess.Popen(
                [sys.executable, cliente_path], cwd=RAIZ, env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.addCleanup(lambda: proc.kill() if proc.poll() is None
                            else None)
            try:
                fim = time.time() + 30
                while time.time() < fim:
                    if os.path.exists(marca):
                        break
                    time.sleep(0.2)
                self.assertTrue(os.path.exists(marca),
                                "oferta diferida não chegou no P2P real "
                                "(1 conn, 1 ver, só a 1ª falha injetada)")
                decorrido = time.time() - inicio
                # esperou o cooldown real (sem 2ª conexão p/ salvar)
                self.assertGreaterEqual(
                    decorrido, 9.0,
                    "meta chegou cedo demais (não esperou o cooldown)")
                with sm.L:
                    naceitos, nvers, nmetas = (estado["aceitos"],
                                              estado["vers"],
                                              estado["metas_ok"])
                self.assertEqual(naceitos, 1,
                                 "2ª conexão aberta (exigido: mesma conexão)")
                self.assertEqual(nvers, 1,
                                 "2º anúncio (exigido: sem reanúncio)")
                self.assertEqual(nmetas, 1)
                self.assertEqual(proc.wait(timeout=10), 0)
            finally:
                try:
                    if proc.poll() is None:
                        proc.kill()
                except Exception:
                    pass
                try:
                    srv.close()
                except OSError:
                    pass


if __name__ == "__main__":
    unittest.main()
