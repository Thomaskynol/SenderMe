#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SenderMe — tcp (extraído de senderme.py sem mudar lógica)."""
import socket
import threading
from . import estado as S
from . import diario as D
from .estado import agora, log, id_curto
from .eventos import processar, receber_pub, tratar_hist
from .arquivos import servir_arquivo, receber_chunk
from .update import tratar_ver, receber_update_meta, servir_update, receber_update_chunk
from .update_proto import cancelar_reoferta
from .manut import tentar_entregar_dm
from .transporte import enviar, ler_quadro, preparar_socket, fechar_socket
from config import PORTA_TCP, MAX_MIDS_INV, MAX_SYNC


def msg_pub():
    return {"t": "pub", "id": S.ident["id"], "n": format(S.ident["n"], "x"),
            "e": S.ident["e"]}


def registrar_conexao(pid, sock, addr, dialado=None):
    with S.L:
        cs = S.conns.setdefault(pid, set())
        cs.add(sock)
        S.sockets_vivos.add(sock)
        cheia = len(cs) > 2
        p = S.peers.setdefault(pid, {})
        p.setdefault("ip", addr[0])
        if dialado:
            p["ip"], p["porta"] = dialado[0], dialado[1]
        S.visto_presenca[pid] = True
        S.ultimo_contato[pid] = agora()
        total = len(S.conns)
    if cheia:
        fechar_socket(sock, pid)
        return False
    D.registrar("peer_conectou", peer=D.curto(pid),
                rede=D.mascarar_ip(addr[0] if addr else None),
                peers_conectados=total)
    return True


def ler_loop(sock, addr, dialado=None):
    pid = None
    try:
        while S.rodando:
            try:
                q = ler_quadro(sock)
            except socket.timeout:
                continue  # ocioso: mantém a conexão, tenta de novo
            if not isinstance(q, dict):
                continue
            if pid is None:
                if q.get("t") != "pub":
                    raise ConnectionError("handshake inválido")
                novo = receber_pub(q)
                if not novo:
                    raise ConnectionError("chave inválida")
                if not registrar_conexao(novo, sock, addr, dialado):
                    return
                pid = novo
                try:
                    enviar(sock, {"t": "ver", "v": S.VERSAO})
                    enviar(sock, {"t": "peers_req"})
                    with S.L:
                        meus = [e.get("mid") for e in S.historico[-MAX_MIDS_INV:]
                                if e.get("mid")]
                    enviar(sock, {"t": "hist_req", "tem": meus})
                except Exception:
                    pass
                threading.Thread(target=tentar_entregar_dm, args=(pid,), daemon=True).start()
                continue
            S.ultimo_contato[pid] = agora()
            tratar_quadro(q, pid, sock)
    except Exception as e:
        # EOF rotineiro (ConnectionError com peer conhecido) já aparece
        # como peer_desconectou; aqui só handshake ou erro incomum.
        if pid is None or not isinstance(e, ConnectionError):
            D.registrar("rede_falha",
                        fase="handshake" if pid is None else "sessao",
                        motivo=type(e).__name__,
                        peer=D.curto(pid) if pid else "nenhum")
    finally:
        fechar_socket(sock, pid)
        # update 1.12: cancela a reoferta diferida se o peer ficou sem
        # conexão viva (com outro socket vivo, mantém).
        try:
            cancelar_reoferta(pid, sock)
        except Exception:
            pass


def tratar_quadro(q, pid, sock):
    t = q.get("t")
    if t == "ev":
        processar(q.get("ev"), origem=pid)
    elif t == "hist_req":
        tem = q.get("tem")
        with S.L:
            if isinstance(tem, list) and tem:
                falta = set(x for x in tem if isinstance(x, str))
                evs = [e for e in S.historico
                       if not e.get("para") and e.get("mid") not in falta][-MAX_SYNC:]
            else:
                evs = [e for e in S.historico if not e.get("para")][-MAX_SYNC:]
            pubs = []
            vistos_autores = set()
            for e in evs:
                a = e.get("de")
                if a in vistos_autores:
                    continue
                vistos_autores.add(a)
                d = S.conhecidos.get(a)
                if d:
                    pubs.append({"id": a, "n": format(d["n"], "x"), "e": d["e"]})
        try:
            enviar(sock, {"t": "hist", "evs": evs, "pubs": pubs})
        except Exception:
            pass
    elif t == "hist":
        tratar_hist(q.get("evs"), q.get("pubs"), pid)
    elif t == "pub_req":
        alvo = q.get("id")
        with S.L:
            d = S.conhecidos.get(alvo)
        if d:
            try:
                enviar(sock, {"t": "pub", "id": alvo, "n": format(d["n"], "x"), "e": d["e"]})
            except Exception:
                pass
    elif t == "pub":
        receber_pub(q)
    elif t == "file_req":
        mid = q.get("mid")
        if isinstance(mid, str) and len(mid) == 64:
            threading.Thread(target=servir_arquivo, args=(pid, mid), daemon=True).start()
    elif t == "file_chunk":
        receber_chunk(q)
    elif t == "ping":
        try:
            enviar(sock, {"t": "pong"})
        except Exception:
            pass
    elif t == "pong":
        pass  # ler_loop já atualizou ultimo_contato
    elif t == "peers_req":
        with S.L:
            pares = []
            for p in list(S.peers.values()) + [{"ip": ip, "porta": int(ps)}
                                             for (ip, ps) in list(S.sementes)][:40]:
                ip, porta = p.get("ip"), p.get("porta")
                if ip and porta:
                    try:
                        pares.append([ip, int(porta)])
                    except Exception:
                        pass
                if len(pares) >= 20:
                    break
        try:
            enviar(sock, {"t": "peers", "pares": pares})
        except Exception:
            pass
    elif t == "peers":
        for item in (q.get("pares") or [])[:20]:
            try:
                ip, porta = str(item[0]), int(item[1])
            except Exception:
                continue
            if not ip or not porta or porta < 1 or porta > 65535:
                continue
            with S.L:
                S.sementes.add((ip, porta))
    elif t == "ver":
        tratar_ver(pid, sock, q.get("v"))
    elif t == "update_meta":
        receber_update_meta(q)
    elif t == "update_get":
        servir_update(pid, sock, q)
    elif t == "update_chunk":
        receber_update_chunk(q)


def dialar(ip, porta, pid=None):
    try:
        s = socket.create_connection((ip, porta), timeout=4)
    except Exception:
        return
    preparar_socket(s)
    with S.L:
        S.sockets_vivos.add(s)
    try:
        enviar(s, msg_pub())
    except Exception:
        fechar_socket(s)
        return
    ler_loop(s, (ip, porta), dialado=(ip, porta))


def abrir_servidor():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("", PORTA_TCP))
        s.listen(64)
        D.registrar("rede_tcp_ok", porta=PORTA_TCP)
        return s
    except OSError as e:
        log("Não consegui abrir TCP %d (%s)." % (PORTA_TCP, e))
        D.registrar("rede_tcp_falha", porta=PORTA_TCP, motivo=type(e).__name__)
        return None


def loop_aceitar(s):
    while S.rodando:
        try:
            c, addr = s.accept()
        except OSError:
            break
        preparar_socket(c)
        with S.L:
            S.sockets_vivos.add(c)
        threading.Thread(target=_aceitar, args=(c, addr), daemon=True).start()
    try:
        s.close()
    except Exception:
        pass


def _aceitar(c, addr):
    try:
        enviar(c, msg_pub())
    except Exception:
        fechar_socket(c)
        return
    ler_loop(c, addr)
