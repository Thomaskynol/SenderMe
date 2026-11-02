#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SenderMe — udp (extraído de senderme.py sem mudar lógica)."""
import json
import os
import secrets
import socket
import threading
from . import estado as S
from . import diario as D
from .estado import agora, log
from .presenca import aplicar_nick
from .persist import salvar_conhecidos
from .manut import tentar_entregar_dm
from crypto import assinar, conferir, fingerprint
from config import PORTA_TCP, PORTA_UDP, INTERVALO_ANUNCIO, JANELA_HELLO


def campo_hello(idp, nome, porta, udp, ts, nonce):
    return "hello|%s|%s|%d|%d|%d|%s" % (idp, nome, porta, udp, ts, nonce)


def montar_hello():
    ts = int(agora())
    nonce = secrets.token_hex(8)
    campo = campo_hello(S.ident["id"], S.nick, PORTA_TCP, PORTA_UDP, ts, nonce)
    return {"t": "hello", "id": S.ident["id"], "n": format(S.ident["n"], "x"),
            "e": S.ident["e"], "nick": S.nick, "porta": PORTA_TCP,
            "udp": PORTA_UDP, "ts": ts, "nonce": nonce,
            "sig": assinar(campo.encode("utf-8"), S.ident).hex()}


def tratar_hello(dados, addr):
    try:
        m = json.loads(dados.decode("utf-8"))
    except Exception:
        return
    if not isinstance(m, dict) or m.get("t") != "hello":
        return
    try:
        n = int(m["n"], 16)
        e = int(m["e"])
        idp = m["id"]
        nome = str(m["nick"])
        porta = int(m["porta"])
        udp = int(m["udp"])
        ts = int(m["ts"])
        nonce = str(m["nonce"])
        sig = bytes.fromhex(m["sig"])
    except Exception:
        return
    if idp == S.ident.get("id"):
        return
    if abs(agora() - ts) > JANELA_HELLO:
        return
    if fingerprint(n, e) != idp:
        return
    campo = campo_hello(idp, nome, porta, udp, ts, nonce)
    if not conferir(campo.encode("utf-8"), sig, n, e):
        return
    novo = False
    with S.L:
        d = S.conhecidos.get(idp)
        if d is None:
            S.conhecidos[idp] = {"n": n, "e": e, "nick": nome}
            novo = True
        elif d["n"] != n:
            return
        p = S.peers.setdefault(idp, {})
        p["ip"], p["porta"], p["udp"] = addr[0], porta, udp
        p["ultimo_hello"] = agora()
        S.ultimo_contato[idp] = agora()
        S.visto_presenca[idp] = True
        if nome:
            aplicar_nick(idp, nome, ts=ts)
    if novo:
        if not salvar_conhecidos():
            log("não consegui gravar conhecidos.json em %s "
                "(disco cheio ou sem permissão?)" % S.DADOS)
        D.registrar("peer_descoberto", peer=D.curto(idp))
    threading.Thread(target=tentar_entregar_dm, args=(idp,), daemon=True).start()


def thread_udp():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.bind(("", PORTA_UDP))
    except OSError as e:
        log("UDP %d indisponível (%s)." % (PORTA_UDP, e))
        D.registrar("rede_udp_falha", porta=PORTA_UDP, motivo=type(e).__name__)
        try:
            s.close()
        except Exception:
            pass
        return
    D.registrar("rede_udp_ok", porta=PORTA_UDP)
    s.settimeout(1.0)
    ciclo = 0
    proximo = agora()
    while S.rodando:
        if agora() >= proximo:
            proximo = agora() + INTERVALO_ANUNCIO
            ciclo += 1
            if S.nick and S.logado:
                try:
                    b = json.dumps(montar_hello(), ensure_ascii=False).encode("utf-8")
                    if not os.environ.get("SENDERME_NO_BROADCAST"):
                        s.sendto(b, ("255.255.255.255", PORTA_UDP))
                    if ciclo % 3 == 0:
                        with S.L:
                            alvos = [(p.get("ip"), p.get("udp")) for p in S.peers.values()
                                     if p.get("ip") and p.get("udp")]
                        for ip, udp in alvos:
                            try:
                                s.sendto(b, (ip, udp))
                            except Exception:
                                pass
                except Exception:
                    pass
        try:
            dados, addr = s.recvfrom(65535)
        except socket.timeout:
            continue
        except OSError:
            break
        tratar_hello(dados, addr)
    try:
        s.close()
    except Exception:
        pass
