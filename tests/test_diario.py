"""Diário persistente (senderme_app/diario.py): stdlib, habilitado por padrão.

Tmp + sintéticas + loopback + SENDERME_NO_BROADCAST; nunca o dir real nem
o start.sh real. Privacidade: apelido/IP/texto-canário nunca no arquivo.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import unittest
from unittest import mock

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "tests"))
sys.path.insert(0, RAIZ)

import suporte  # noqa: E402
from suporte import CasoIsolado  # noqa: E402
import senderme as sm  # noqa: E402
from senderme_app import diario as D  # noqa: E402

CANARIO_NICK = "ApelidoCanarioZXQ42"
CANARIO_IP = "192.168.77.88"
CANARIO_TXT = "TEXTO-CANARIO-SEGRETO-7f3a"
CANARIO_ID = "ab" * 32  # 64 hex falsos (nunca identidade real)


def linhas_log(tmp):
    p = os.path.join(tmp, "logs", "senderme.log")
    if not os.path.isfile(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def todo_logs(tmp):
    textos = []
    d = os.path.join(tmp, "logs")
    if not os.path.isdir(d):
        return ""
    for a in os.listdir(d):
        with open(os.path.join(d, a), encoding="utf-8", errors="replace") as f:
            textos.append(f.read())
    return "\n".join(textos)


class DiarioBase(CasoIsolado):
    def setUp(self):
        super().setUp()
        D.encerrar()
        os.environ["SENDERME_NO_BROADCAST"] = "1"
        self.assertEqual(D.iniciar(), os.path.join(self._tmp.name, "logs",
                                                   "senderme.log"))

    def tearDown(self):
        try:
            D.encerrar()
        finally:
            super().tearDown()


class DiarioArquivo(DiarioBase):
    def test_inicia_habilitado_por_padrao_em_logs_do_home(self):
        self.assertTrue(D.registrar("sonda_teste", num=1))
        p = os.path.join(self._tmp.name, "logs", "senderme.log")
        self.assertTrue(os.path.isfile(p))
        (linha,) = [l for l in linhas_log(self._tmp.name)
                    if l["evento"] == "sonda_teste"]
        self.assertEqual(linha["num"], 1)
        self.assertEqual(linha["run"], D.RUN_ID)
        self.assertEqual(linha["versao"], sm.VERSAO)

    def test_persistencia_entre_restarts(self):
        D.registrar("boot", fase="antes")
        D.encerrar()
        velho_run = D.RUN_ID
        D.RUN_ID = "run-falso-2"
        self.addCleanup(setattr, D, "RUN_ID", velho_run)
        D.iniciar()
        D.registrar("boot", fase="depois")
        fases = {l.get("fase"): l.get("run") for l in linhas_log(self._tmp.name)
                 if l["evento"] == "boot"}
        self.assertEqual(set(fases), {"antes", "depois"})
        self.assertNotEqual(fases["antes"], fases["depois"])

    def test_rotacao_limita_disco(self):
        D.encerrar()
        D.iniciar(max_bytes=1024, backups=2)
        for i in range(120):
            D.registrar("volume", i=i, n=i)
        D.encerrar()
        d = os.path.join(self._tmp.name, "logs")
        achados = sorted(a for a in os.listdir(d) if a.startswith("senderme.log"))
        self.assertEqual(achados, ["senderme.log", "senderme.log.1",
                                   "senderme.log.2"])
        total = sum(os.path.getsize(os.path.join(d, a)) for a in achados)
        self.assertLess(total, 3 * 1024 + 2048)
        for a in achados:
            with open(os.path.join(d, a), encoding="utf-8") as f:
                for l in f:
                    if l.strip():
                        json.loads(l)  # toda linha válida

    def test_sem_log_desliga_sem_quebrar(self):
        os.environ["SENDERME_SEM_LOG"] = "1"
        self.addCleanup(os.environ.pop, "SENDERME_SEM_LOG", None)
        D.encerrar()
        self.assertIsNone(D.iniciar())
        self.assertFalse(D.registrar("sonda_teste"))

    def test_falha_de_log_nunca_derruba(self):
        # PASTA vira arquivo: makedirs do logs falha em qualquer usuário.
        D.encerrar()
        shutil.rmtree(self._tmp.name)
        with open(self._tmp.name, "w") as f:
            f.write("x")
        try:
            self.assertIsNone(D.iniciar())
            self.assertFalse(D.registrar("sonda_teste"))  # sem levantar
            # o app segue funcionando em memória mesmo sem diário
            idt, _ = suporte.definir_eu(nick="alguem")
            ev = sm.criar_evento("msg", "oi")
            self.assertTrue(sm.processar(ev, origem=None, gravar=False))
        finally:
            os.remove(self._tmp.name)
            os.makedirs(self._tmp.name)


class DiarioEventos(DiarioBase):
    def test_peer_conecta_desconecta_sem_id_permanente(self):
        pid = CANARIO_ID
        a, b = socket.socketpair()
        self.addCleanup(a.close)
        self.addCleanup(b.close)
        sm.ident.clear()
        sm.ident.update(suporte.identidade_de(suporte.chave_teste()))
        self.assertTrue(sm.registrar_conexao(pid, a, (CANARIO_IP, 5000)))
        sm.fechar_socket(a, pid)
        evs = [l for l in linhas_log(self._tmp.name)
               if l["evento"] in ("peer_conectou", "peer_desconectou")]
        self.assertEqual([e["evento"] for e in evs],
                         ["peer_conectou", "peer_desconectou"])
        # rótulo temporário por execução (não deriva do id permanente)
        self.assertTrue(evs[0]["peer"].startswith("peer-"))
        self.assertEqual(evs[0]["peer"], evs[1]["peer"])
        self.assertEqual(evs[0]["rede"], "192.168.77.0/24")
        blob = todo_logs(self._tmp.name)
        self.assertNotIn(pid, blob)
        self.assertNotIn(CANARIO_IP, blob)

    def test_envio_falha_sem_payload(self):
        class Quebrado:
            def sendall(self, b):
                raise BrokenPipeError("tubo quebrou: segredo")
        with self.assertRaises(BrokenPipeError):
            sm.enviar(Quebrado(), {"t": "ev", "ev": {"txt": CANARIO_TXT}})
        (linha,) = [l for l in linhas_log(self._tmp.name)
                    if l["evento"] == "envio_falha"]
        self.assertEqual(linha["motivo"], "BrokenPipeError")
        blob = todo_logs(self._tmp.name)
        self.assertNotIn(CANARIO_TXT, blob)
        self.assertNotIn("tubo quebrou", blob)

    def test_handshake_falha_loopback(self):
        srv, cli = socket.socketpair()
        srv.close()  # EOF imediato do outro lado
        sm.preparar_socket(cli)
        sm.ler_loop(cli, ("127.0.0.1", 1))  # retorna; nunca levanta
        cli.close()
        evs = [l for l in linhas_log(self._tmp.name)
               if l["evento"] == "rede_falha"]
        self.assertTrue(evs)
        self.assertEqual(evs[0]["fase"], "handshake")

    def test_persist_falha_registra_arquivo_sem_conteudo(self):
        dados = os.path.join(self._tmp.name, "dados")
        shutil.rmtree(dados, ignore_errors=True)
        with open(dados, "w") as f:  # dir vira arquivo: tudo falha
            f.write("x")
        try:
            self.assertFalse(sm.salvar_json("sonda.json", {"a": 1}))
            self.assertFalse(sm.anexar_historico({"mid": "m",
                                                  "txt": CANARIO_TXT}))
        finally:
            os.remove(dados)
            os.makedirs(dados)
        evs = [l for l in linhas_log(self._tmp.name)
               if l["evento"] == "persist_falha"]
        self.assertTrue(len(evs) >= 2)
        self.assertTrue(all("arq" in e for e in evs))
        self.assertNotIn(CANARIO_TXT, todo_logs(self._tmp.name))

    def test_update_abortado_e_oferta_sem_caminhos(self):
        with sm.L:
            sm.update_manifest = None
            sm.update_envelope = None
        self.assertFalse(sm.finalizar_update())
        evs = [l for l in linhas_log(self._tmp.name)
               if l["evento"] == "update_abortado"]
        self.assertTrue(evs)
        # sem motivo livre (pode conter caminhos): fica só no terminal
        self.assertNotIn("motivo", evs[0])

    def test_mascarar_ip_e_curto(self):
        self.assertEqual(D.mascarar_ip("10.0.5.200"), "10.0.5.0/24")
        self.assertEqual(D.mascarar_ip("127.0.0.1"), "127.0.0.0/24")
        for ruim in (None, "", "não-ip", "1.2.3", "999.1.1.1", "::1"):
            self.assertEqual(D.mascarar_ip(ruim), "***")
        # curto() é rótulo temporário por execução, não prefixo do id
        a = D.curto("ab" * 32)
        self.assertTrue(a.startswith("peer-"))
        self.assertEqual(D.curto("ab" * 32), a)  # estável no run
        self.assertNotEqual(D.curto("cd" * 32), a)  # distingue peers
        self.assertEqual(D.curto(None), "?")
        self.assertEqual(D.curto(""), "?")
        self.assertEqual(D.sanear_versao("1.18"), "1.18")
        self.assertEqual(D.sanear_versao("NICK-canario"), "invalida")
        self.assertEqual(D._sanear_fio("Thread-1 (boom)"), "Thread-1-boom")
        self.assertEqual(D._sanear_fio("sm-teste-falha"), "sm-teste-falha")


class DiarioPrivacidade(DiarioBase):
    def test_varredura_canarios(self):
        idt, chave = suporte.definir_eu(nick=CANARIO_NICK)
        # hello assinado de par canário NOVO (descoberta) + DM + conexão
        pchave = suporte.chave_teste()
        par = suporte.identidade_de(pchave)
        hello = {"t": "hello", "id": par["id"], "n": format(pchave["n"], "x"),
                 "e": pchave["e"], "nick": CANARIO_NICK, "porta": 13337,
                 "udp": 13338, "ts": int(sm.agora()), "nonce": "n" * 16,
                 "sig": ""}
        campo = sm.campo_hello(par["id"], CANARIO_NICK, 13337, 13338,
                               hello["ts"], hello["nonce"])
        hello["sig"] = sm.assinar(campo.encode("utf-8"), pchave).hex()
        sm.tratar_hello(json.dumps(hello).encode("utf-8"), (CANARIO_IP, 1))
        ev_dm = suporte.criar_como(idt, CANARIO_NICK, "dm", CANARIO_TXT,
                                   para=par["id"])
        sm.processar(ev_dm, origem=None, gravar=True)
        a, b = socket.socketpair()
        self.addCleanup(a.close)
        self.addCleanup(b.close)
        sm.registrar_conexao(par["id"], a, (CANARIO_IP, 5000))
        sm.fechar_socket(a, par["id"])
        sm.tratar_comando_web("/nick " + CANARIO_NICK)
        blob = todo_logs(self._tmp.name)
        for canario in (CANARIO_NICK, CANARIO_IP, CANARIO_TXT, par["id"],
                        idt["id"]):
            self.assertNotIn(canario, blob,
                             "canário vazou p/ o diário: %r" % canario[:16])
        # e o útil ficou: descoberta/conexão com id curto + /24
        evs = {l["evento"] for l in linhas_log(self._tmp.name)}
        self.assertTrue({"peer_descoberto", "peer_conectou",
                         "peer_desconectou"} <= evs)

    def test_registrar_filtra_chaves_sensiveis(self):
        D.registrar("sonda_teste", nick=CANARIO_NICK, txt=CANARIO_TXT,
                    ip=CANARIO_IP, id=CANARIO_ID, num=7)
        (linha,) = [l for l in linhas_log(self._tmp.name)
                    if l["evento"] == "sonda_teste"]
        self.assertEqual(linha.get("num"), 7)
        for proibida in ("nick", "txt", "ip", "id"):
            self.assertNotIn(proibida, linha)
        self.assertNotIn(CANARIO_TXT, todo_logs(self._tmp.name))

    def test_registrar_allowlist_descarta_campo_desconhecido(self):
        D.registrar("sonda_teste", num=3, campo_novo_rede="CANARIO-VAZOU?")
        (linha,) = [l for l in linhas_log(self._tmp.name)
                    if l["evento"] == "sonda_teste"]
        self.assertEqual(linha.get("num"), 3)
        self.assertNotIn("campo_novo_rede", linha)
        self.assertNotIn("CANARIO-VAZOU?", todo_logs(self._tmp.name))


class DiarioConcorrencia(DiarioBase):
    def test_threads_concorrentes(self):
        n_thread, n_msg = 8, 50
        erros = []

        def lote(t):
            try:
                for i in range(n_msg):
                    if not D.registrar("carga", thread=t, i=i):
                        erros.append("não persistiu")
            except Exception as e:  # nunca deve acontecer
                erros.append(repr(e))

        ts = [threading.Thread(target=lote, args=(t,)) for t in range(n_thread)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(timeout=60)
        self.assertFalse([t for t in ts if t.is_alive()])
        self.assertEqual(erros, [])
        got = [l for l in linhas_log(self._tmp.name) if l["evento"] == "carga"]
        self.assertEqual(len(got), n_thread * n_msg)
        self.assertEqual(len({(l["thread"], l["i"]) for l in got}),
                         n_thread * n_msg)

    def test_multiprocesso_acrescenta_mesmo_arquivo(self):
        # Demonstra append entre processos (mesmo HOME). Rotação sob
        # multiprocesso NÃO é garantida (ver relatório) — aqui sem rotação.
        D.encerrar()
        template = ("import sys; sys.path.insert(0, {tests!r}); "
                    "sys.path.insert(0, {raiz!r}); "
                    "from senderme_app import diario as D; "
                    "D.iniciar(max_bytes=10*1024*1024, backups=1); "
                    "[D.registrar('filho', grp={grp}, i=i) for i in range(30)]; "
                    "D.encerrar()")
        env = dict(os.environ, SENDERME_HOME=self._tmp.name)
        ps = [subprocess.Popen(
            [sys.executable, "-c", template.format(
                tests=os.path.join(RAIZ, "tests"), raiz=RAIZ, grp=n)],
            env=env) for n in (0, 1)]
        for p in ps:
            self.assertEqual(p.wait(timeout=60), 0)
        D.iniciar()
        got = [l for l in linhas_log(self._tmp.name) if l["evento"] == "filho"]
        self.assertEqual(len(got), 60)
        self.assertTrue(all(set(l) >= {"ts", "run", "versao", "evento", "grp", "i"}
                            for l in got))


class DiarioPreboot(unittest.TestCase):
    def test_preboot_sem_marcador_silencioso(self):
        from senderme_app import preboot
        import tempfile
        tmp = tempfile.mkdtemp(prefix="sm-pre-")
        self.addCleanup(shutil.rmtree, tmp, True)
        self.assertEqual(preboot.main(["preboot.py", tmp]), 0)
        self.assertFalse(os.path.exists(os.path.join(tmp, "logs", "preboot.log")))

    def test_preboot_com_marcador_registra_sem_caminhos(self):
        from senderme_app import preboot
        import tempfile
        tmp = tempfile.mkdtemp(prefix="sm-pre2-")
        self.addCleanup(shutil.rmtree, tmp, True)
        with open(os.path.join(tmp, ".upd-pendente.json"), "w") as f:
            f.write("{ilegível")
        self.assertEqual(preboot.main(["preboot.py", tmp]), 1)
        p = os.path.join(tmp, "logs", "preboot.log")
        with open(p, encoding="utf-8") as f:
            (linha,) = [json.loads(l) for l in f if l.strip()]
        self.assertTrue(linha["teve_marcador"])
        self.assertTrue(linha["recuperacao_restante"])
        self.assertNotIn(tmp, json.dumps(linha))


class DiarioFalhaEscrita(DiarioBase):
    """Item 1: falha DEPOIS da abertura (write/flush/rotação) → False.

    Causa-raiz: o `logging` engole exceções de emit em `handleError`;
    `logger.info()` nunca levanta. Sem captura própria, `registrar()`
    retornava True sem persistir (ver repro da rodada).
    """

    def _handler(self):
        return D._log.handlers[0]

    def test_write_falha_retorna_false_com_um_aviso(self):
        D._aviso_falha = False
        h = self._handler()

        class DiscoCheio:
            def write(self, s):
                raise OSError("disco cheio")
            def flush(self):
                raise OSError("disco cheio")
            def close(self):
                pass

        real = h.stream
        h.stream = DiscoCheio()
        try:
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertFalse(D.registrar("sonda_falha", num=1))
                self.assertFalse(D.registrar("sonda_falha", num=2))
            # sem levantar, chat segue em memória mesmo sem diário
            idt, _ = suporte.definir_eu(nick="alguem")
            ev = sm.criar_evento("msg", "oi")
            self.assertTrue(sm.processar(ev, origem=None, gravar=False))
            avisos = [l for l in buf.getvalue().splitlines()
                      if "diario:" in l]
            self.assertEqual(len(avisos), 1)  # 1 vez, sem loop
        finally:
            h.stream = real

    def test_flush_falha_retorna_false(self):
        h = self._handler()

        class FlushQuebrado:
            def __init__(self, real):
                self._real = real
            def write(self, s):
                return self._real.write(s)
            def flush(self):
                raise OSError("flush quebrou")
            def close(self):
                pass

        real = h.stream
        h.stream = FlushQuebrado(real)
        try:
            self.assertFalse(D.registrar("sonda_falha", num=1))
        finally:
            h.stream = real
        self.assertTrue(D.registrar("sonda_ok", num=2))

    def test_rotacao_falha_retorna_false(self):
        self.assertTrue(D.registrar("sonda_ok", num=0))  # arquivo não vazio
        h = self._handler()
        velho = h.maxBytes
        h.maxBytes = 1  # força shouldRollover (3.14 não gira vazio)
        try:
            with mock.patch.object(h, "doRollover",
                                   side_effect=OSError("rotação")):
                self.assertFalse(D.registrar("sonda_falha", num=1))
        finally:
            h.maxBytes = velho
        self.assertTrue(D.registrar("sonda_ok", num=2))

    def test_corrida_retorno_reflete_propria_gravacao(self):
        """1.20/1: A-falha → B-sucesso-limpa → A-checa: A False, B True.

        Sem `_reg_lck`, o `h.erro` compartilhado fazia A retornar True sem
        persistir e sem aviso (RED da rodada). Com o lock, cada chamada
        reflete a própria gravação. Determinístico via eventos (A dorme
        em emit p/ B correr na janela); sem deadlock (join com timeout) e
        sem levantar (registrar nunca levanta).
        """
        D._aviso_falha = False
        h = self._handler()
        orig = h.emit
        entrou = threading.Event()
        out = {}

        def falso_emit(record):
            if threading.current_thread().name == "sm-corr-a":
                try:
                    raise OSError("rotacao")
                except OSError:
                    h.handleError(record)
                entrou.set()
                time.sleep(0.5)  # janela p/ B (só dorme, sem esperar B)
                return
            return orig(record)

        h.emit = falso_emit
        try:
            def chama_a():
                try:
                    out["a"] = D.registrar("corrida_a", num=1)
                except Exception as e:  # nunca deve acontecer
                    out["a"] = repr(e)

            def chama_b():
                entrou.wait(timeout=10)
                time.sleep(0.1)  # B limpa durante o sono de A (janela do bug)
                try:
                    out["b"] = D.registrar("corrida_b", num=2)
                except Exception as e:
                    out["b"] = repr(e)

            ta = threading.Thread(target=chama_a, name="sm-corr-a")
            tb = threading.Thread(target=chama_b, name="sm-corr-b")
            ta.start()
            tb.start()
            ta.join(timeout=10)
            tb.join(timeout=10)
            self.assertFalse(ta.is_alive(), "deadlock em A")
            self.assertFalse(tb.is_alive(), "deadlock em B")
            self.assertFalse(out["a"], "A falhou e deve retornar False")
            self.assertTrue(out["b"], "B persistiu e deve retornar True")
            self.assertTrue(D._aviso_falha, "falha de A deve avisar 1 vez")
            # B persistiu de verdade; A não (falha própria, sem silêncio)
            got = [l for l in linhas_log(self._tmp.name)
                   if l["evento"] in ("corrida_a", "corrida_b")]
            self.assertEqual([l["evento"] for l in got], ["corrida_b"])
        finally:
            h.emit = orig

    def test_concorrentes_com_falha_sem_deadlock_e_sem_levantar(self):
        """1.20/1: N threads sob contenção não travam e nunca levantam."""
        D._aviso_falha = False
        erros = []

        def lote(t):
            try:
                for i in range(30):
                    try:
                        D.registrar("carga_corr", thread=t, i=i)
                    except Exception as e:  # registrar nunca levanta
                        erros.append(repr(e))
            except Exception as e:
                erros.append(repr(e))

        ts = [threading.Thread(target=lote, args=(t,)) for t in range(8)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(timeout=30)
        self.assertFalse([t for t in ts if t.is_alive()], "deadlock")
        self.assertEqual(erros, [])


class DiarioPrebootSemLog(unittest.TestCase):
    """Item 2: SENDERME_SEM_LOG=1 → preboot não cria preboot.log."""

    def test_marcador_com_sem_log_nao_cria_log_e_mantem_resultado(self):
        from senderme_app import preboot
        import tempfile
        tmp = tempfile.mkdtemp(prefix="sm-presem-")
        self.addCleanup(shutil.rmtree, tmp, True)
        os.environ["SENDERME_SEM_LOG"] = "1"
        self.addCleanup(os.environ.pop, "SENDERME_SEM_LOG", None)
        with open(os.path.join(tmp, ".upd-pendente.json"), "w") as f:
            f.write("{ilegível")
        self.assertEqual(preboot.main(["preboot.py", tmp]), 1)
        self.assertFalse(os.path.exists(
            os.path.join(tmp, "logs", "preboot.log")))
        # resultado preservado: marcador mantido p/ intervenção manual
        self.assertTrue(os.path.lexists(
            os.path.join(tmp, ".upd-pendente.json")))

    def test_sem_marcador_com_sem_log_continua_silencioso(self):
        from senderme_app import preboot
        import tempfile
        tmp = tempfile.mkdtemp(prefix="sm-presem2-")
        self.addCleanup(shutil.rmtree, tmp, True)
        os.environ["SENDERME_SEM_LOG"] = "1"
        self.addCleanup(os.environ.pop, "SENDERME_SEM_LOG", None)
        self.assertEqual(preboot.main(["preboot.py", tmp]), 0)
        self.assertFalse(os.path.exists(
            os.path.join(tmp, "logs", "preboot.log")))


class DiarioProtocolo(DiarioBase):
    """Item 3: canários em DADOS DE PROTOCOLO (não só nick/txt/ip/id)."""

    def test_versao_arbitraria_da_rede_nao_vaza(self):
        pid = "cd" * 32
        hostil = "VER-CANARIO-PROTOCOLO-ZW9\nsegunda-linha"
        sm.tratar_ver(pid, None, hostil)  # oferta segue; log não leva o cru
        achou = [l for l in linhas_log(self._tmp.name)
                 if l["evento"] == "update_oferta"]
        self.assertTrue(achou)
        self.assertEqual(achou[-1]["versao_peer"], "invalida")
        self.assertTrue(achou[-1]["peer"].startswith("peer-"))
        blob = todo_logs(self._tmp.name)
        self.assertNotIn("VER-CANARIO-PROTOCOLO-ZW9", blob)
        self.assertNotIn("segunda-linha", blob)
        self.assertNotIn(pid, blob)

    def test_rotulo_temporario_nao_correla_entre_execucoes(self):
        pid = "ef" * 32
        rotulo = D.curto(pid)
        D.registrar("sonda_teste", peer=rotulo, num=1)
        self.assertIn(pid[:4], pid)  # sanidade: canário válido
        blob = todo_logs(self._tmp.name)
        self.assertNotIn(pid, blob)
        self.assertNotIn(pid[:8], blob)
        # nova "execução": o mesmo id permanente ganha outro rótulo
        D.encerrar()
        D.iniciar()
        rotulo2 = D.curto(pid)
        self.assertTrue(rotulo2.startswith("peer-"))
        self.assertEqual(rotulo2, "peer-1")


class DiarioVersaoCategoria(DiarioBase):
    """1.20/2: valor externo nunca vira `versao` pré-assinatura.

    `receber_update_meta` com update em andamento + `v` IP + sig
    inválida gravava o IP como versão ANTES de conferir. Agora o
    pré-assinatura (ignorado/recusado) só leva categoria fixa em
    `motivo` (anterior/igual/superior/invalida); a versão real só
    aparece pós-assinatura (update_recebido, do dono). Protocolo
    intacto (ver_tupla/decisão/estado). IPv4 e 4-partes são
    indistinguíveis: 4 partes numéricas = invalida no log.
    """

    def _ignorado(self, v_ext):
        with sm.L:
            sm.atualizando = True
            sm.update_manifest = {"v": "9.9", "arquivos": []}
            sm.update_envelope = None
        try:
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                sm.receber_update_meta(
                    {"manifest": {"v": v_ext, "arquivos": [
                        {"nome": "senderme.py", "tamanho": 1,
                         "sha256": "0" * 64}]}, "sig": "00"})
            term = buf.getvalue()
        finally:
            with sm.L:
                sm.atualizando = False
                sm.update_manifest = None
                sm.update_envelope = None
        return term

    def test_ip_pre_assinatura_so_categoria(self):
        term = self._ignorado("192.168.1.123")
        blob = todo_logs(self._tmp.name)
        self.assertNotIn("192.168.1.123", blob, "IP vazou p/ o diário")
        self.assertNotIn("192.168.1.123", term, "IP vazou p/ o terminal")
        got = [l for l in linhas_log(self._tmp.name)
               if l["evento"] == "update_ignorado"]
        self.assertEqual(len(got), 1)
        # 4 partes numéricas indistinguíveis de IPv4: invalida, sem cru
        self.assertEqual(got[0].get("motivo"), "invalida")
        self.assertNotIn("versao_peer", got[0])
        # `versao` da linha é a LOCAL (1.19), nunca a externa
        self.assertEqual(got[0].get("versao"), sm.VERSAO)
        # protocolo intacto: segue atualizando? (reset no finally) + sem
        # manifest novo durante a chamada (estado preservado p/ teste)
        self.assertNotIn("192.168.1.123", json.dumps(got[0]))

    def test_versao_superior_pre_assinatura_so_categoria(self):
        term = self._ignorado("99.0")
        blob = todo_logs(self._tmp.name)
        self.assertNotIn("99.0", blob.replace(sm.VERSAO, ""),
                         "versão externa crua vazou pré-assinatura")
        self.assertNotIn("99.0", term)
        (got,) = [l for l in linhas_log(self._tmp.name)
                  if l["evento"] == "update_ignorado"]
        self.assertEqual(got.get("motivo"), "superior")

    def test_externos_nao_versao_descartados_sem_vazar(self):
        for hostil in (CANARIO_NICK, CANARIO_TXT, CANARIO_ID,
                       "1.2.3.4", "apelido", "v1.19\ninjecao"):
            D.encerrar()
            D.iniciar()
            with sm.L:
                sm.atualizando = True
                sm.update_manifest = {"v": "9.9", "arquivos": []}
                sm.update_envelope = None
            try:
                sm.receber_update_meta(
                    {"manifest": {"v": hostil, "arquivos": [
                        {"nome": "senderme.py", "tamanho": 1,
                         "sha256": "0" * 64}]}, "sig": "00"})
            finally:
                with sm.L:
                    sm.atualizando = False
                    sm.update_manifest = None
            blob = todo_logs(self._tmp.name)
            # o que não for versão segura vira categoria ou nem loga
            # (anterior/igual retorna cedo sem log); nunca o cru
            if len(hostil) <= 16:
                self.assertNotIn(hostil, blob,
                                 "externo vazou: %r" % hostil[:16])
            for parte in (CANARIO_NICK, CANARIO_TXT, CANARIO_ID):
                self.assertNotIn(parte, blob)
            # estado preservado (compatibilidade): nada foi aceito
            self.assertFalse(sm.atualizando)
            self.assertIsNone(sm.update_manifest)

    def test_recusado_pre_assinatura_so_categoria(self):
        with open(os.path.join(self._tmp.name, ".upd-pendente.json"),
                  "w") as f:
            f.write("{}")
        with sm.L:
            sm.atualizando = False
            sm.update_manifest = None
            sm.update_envelope = None
        try:
            sm.receber_update_meta(
                {"manifest": {"v": "192.168.9.9", "arquivos": [
                    {"nome": "senderme.py", "tamanho": 1,
                     "sha256": "0" * 64}]}, "sig": "00"})
        finally:
            try:
                os.remove(os.path.join(self._tmp.name,
                                       ".upd-pendente.json"))
            except OSError:
                pass
        blob = todo_logs(self._tmp.name)
        self.assertNotIn("192.168.9.9", blob)
        (got,) = [l for l in linhas_log(self._tmp.name)
                  if l["evento"] == "update_recusado"]
        self.assertEqual(got.get("motivo"), "invalida")
        self.assertEqual(got.get("versao"), sm.VERSAO)

    def test_sanear_rejeita_4_partes_indistinguiveis_de_ip(self):
        self.assertEqual(D.sanear_versao("192.168.1.123"), "invalida")
        self.assertEqual(D.sanear_versao("1.2.3.4"), "invalida")
        self.assertEqual(D.sanear_versao("99.0"), "99.0")
        self.assertEqual(D.sanear_versao("1.2.3"), "1.2.3")
        self.assertEqual(D.sanear_versao("1.19"), "1.19")

    def test_recebido_pos_assinatura_mantem_versao(self):
        # versão segura e necessária: envelope SINTÉTICO assinado.
        from unittest import mock as _mock
        from suporte import chave_teste
        chave = chave_teste()
        n_hex = format(chave["n"], "x")
        import hashlib
        manif = {"v": "99.0", "arquivos": [
            {"nome": "senderme.py", "tamanho": 1,
             "sha256": hashlib.sha256(b"x").hexdigest()}]}
        sig = sm.assinar(sm.manifest_canonico(manif), chave).hex()
        with _mock.patch.multiple("senderme_app.estado", CHAVE_DONO_N=n_hex,
                                  CHAVE_DONO_E=65537):
            with _mock.patch("senderme_app.update.baixar_update",
                             lambda: None):
                with sm.L:
                    sm.atualizando = False
                    sm.update_manifest = None
                sm.receber_update_meta({"manifest": manif, "sig": sig})
                try:
                    self.assertTrue(sm.atualizando)
                    (got,) = [l for l in linhas_log(self._tmp.name)
                              if l["evento"] == "update_recebido"]
                    self.assertEqual(got.get("versao"), "99.0")
                finally:
                    with sm.L:
                        sm.atualizando = False
                        sm.update_manifest = None
                        sm.update_envelope = None


class DiarioThreads(DiarioBase):
    """Item 4: exceção REAL em thread aparece no diário (só o tipo)."""

    def test_excecao_real_em_thread_sem_msg_da_excecao(self):
        self.assertTrue(D.instalar_hook_threads())

        def boom():
            raise ValueError("CANARIO-THREAD-SEGREDO-99")

        t = threading.Thread(target=boom, name="sm-teste-falha",
                             daemon=True)
        t.start()
        t.join(timeout=10)
        self.assertFalse(t.is_alive())  # a thread morreu normalmente
        fim = time.time() + 10
        got = []
        while time.time() < fim:  # espera por condição, sem sleep fixo
            got = [l for l in linhas_log(self._tmp.name)
                   if l["evento"] == "thread_falha"]
            if got:
                break
            time.sleep(0.05)
        self.assertTrue(got, "thread_falha ausente no diário")
        self.assertEqual(got[0]["motivo"], "ValueError")
        self.assertEqual(got[0]["fio"], "sm-teste-falha")
        blob = todo_logs(self._tmp.name)
        self.assertNotIn("CANARIO-THREAD-SEGREDO-99", blob)
        # o chat segue: o diário ainda persiste depois da falha
        self.assertTrue(D.registrar("sonda_ok", num=1))


class DiarioListas(unittest.TestCase):
    def test_runtime_allowlist_e_manifesto_cobrem_diario(self):
        import senderme_app.meta as meta
        self.assertIn("senderme_app/diario.py", meta.ARQUIVOS_UPDATE)
        with open(os.path.join(RAIZ, "start.sh"), encoding="utf-8") as f:
            self.assertIn("senderme_app/diario.py", f.read())
        with open(os.path.join(RAIZ, "build_dist.sh"), encoding="utf-8") as f:
            self.assertIn("senderme_app/diario.py", f.read())
        # contrato sm.* (testes usam senderme como fachada)
        self.assertTrue(callable(sm.registrar_diario))
        self.assertTrue(callable(sm.iniciar_diario))
        self.assertTrue(callable(sm.mascarar_ip))
        self.assertTrue(callable(sm.curto))
        self.assertTrue(callable(sm.instalar_hook_threads))
        self.assertTrue(callable(sm.sanear_versao))
        self.assertEqual(len(sm.RUN_ID), 12)


if __name__ == "__main__":
    unittest.main()
