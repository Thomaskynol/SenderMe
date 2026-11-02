#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SenderMe — manut (extraído de senderme.py sem mudar lógica)."""
import base64
import os
import threading
import time
from . import estado as S
from . import diario as D
from .estado import agora, log, id_curto, ip_local
from .eventos import criar_evento, publicar, pedir_arquivo
from .presenca import presente, pode_exibir_saida, apelido_de
from .arquivos import tem_arquivo, ler_bytes_arquivo
from .transporte import enviar, fechar_socket
from config import (FIXOS, PORTA_TCP, TIMEOUT_DIAL, TIMEOUT_OFFLINE, INTERVALO_PING, INTERVALO_PURGA, RETENCAO, JANELA_ENTRADA, JANELA_SAIDA, CHUNK_ARQ)


def _alvo_eu(ip, porta):
    try:
        if int(porta) != PORTA_TCP:
            return False
    except Exception:
        return False
    try:
        return ip in ("127.0.0.1", "localhost", ip_local())
    except Exception:
        return ip == "127.0.0.1"


def alvos_de_discagem():
    t = agora()
    with S.L:
        alvos = []
        vistos_chave = set()
        def agendar(ip, porta, pid):
            try:
                porta = int(porta)
            except Exception:
                return
            if not ip or porta < 1 or porta > 65535:
                return
            if _alvo_eu(ip, porta):
                return  # nunca disca para si mesmo
            chave = "%s:%d" % (ip, porta)
            if chave in vistos_chave:
                return
            vistos_chave.add(chave)
            if pid is not None and any(c in S.sockets_vivos for c in S.conns.get(pid, ())):
                return
            if t - S.ultimo_dial.get(chave, 0) < TIMEOUT_DIAL:
                return
            S.ultimo_dial[chave] = t
            alvos.append((ip, porta, pid))
        for pid, p in list(S.peers.items()):
            agendar(p.get("ip"), p.get("porta"), pid)
        for fx in FIXOS:
            ip, _, ps = fx.partition(":")
            try:
                porta = int(ps)
            except ValueError:
                continue
            agendar(ip, porta, _id_do_alvo(ip, porta))
        for (ip, porta) in list(S.sementes):
            agendar(ip, porta, _id_do_alvo(ip, porta))
    return alvos


def _id_do_alvo(ip, porta):
    for idp, p in S.peers.items():
        if p.get("ip") == ip and p.get("porta") == porta:
            return idp
    return None


def anunciar_entrada():
    t = agora()
    with S.L:
        if not S.logado or not S.nick:
            return
        if t - S.ultima_join_eu < JANELA_ENTRADA and S.ultima_leave_eu <= S.ultima_join_eu:
            return
        S.ultima_join_eu = t
    publicar(criar_evento("join", ""))


def anunciar_saida(pid):
    with S.L:
        if not pode_exibir_saida(pid):
            return
        if agora() - S.ultima_leave.get(pid, 0) < JANELA_SAIDA:
            return
        S.ultima_leave[pid] = agora()
    publicar(criar_evento("leave", pid))


def ausentes():
    t = agora()
    with S.L:
        alvos = []
        for pid in list(S.peers):
            if pid == S.ident.get("id"):
                continue
            ultimo = S.ultimo_contato.get(pid, 0)
            if ultimo == 0 or t - ultimo <= TIMEOUT_OFFLINE:
                continue
            if any(c in S.sockets_vivos for c in S.conns.get(pid, ())):
                continue
            if not pode_exibir_saida(pid):
                continue
            if t - S.ultima_leave.get(pid, 0) < JANELA_SAIDA:
                continue
            alvos.append(pid)
    return alvos


def manutencao():
    from .tcp import dialar as _dialar  # adiado: tcp importa tentar_entregar_dm
    S.ciclo_manut += 1
    with S.L:
        ncon = len(S.sockets_vivos)
        ok = bool(S.logado and S.nick)
        # limpa cadáveres: sockets mortos que ficaram em conns
        for pid in list(S.conns):
            cs = S.conns[pid]
            vivas = {c for c in cs if c in S.sockets_vivos}
            if vivas != cs:
                if vivas:
                    S.conns[pid] = vivas
                else:
                    S.conns.pop(pid, None)
        for s in list(S.envios_lck):
            if s not in S.sockets_vivos:
                S.envios_lck.pop(s, None)
    if ncon == 0:
        S.tinha_conexao = False
    elif ok and not S.tinha_conexao:
        anunciar_entrada()
        S.tinha_conexao = True
    if S.ciclo_manut % INTERVALO_PING == 0:
        with S.L:
            todos = [c for cs in S.conns.values() for c in cs if c in S.sockets_vivos]
        for c in todos:
            try:
                enviar(c, {"t": "ping"})
            except Exception:
                pass
    # varredura: puxa até 2 conteúdos de arquivo faltantes por ciclo
    try:
        with S.L:
            falt = [e["mid"] for e in S.historico
                    if e.get("tipo") == "file" and not e.get("para")
                    and not tem_arquivo(e.get("mid", ""))][:4]
        for mid in falt[:2]:
            pedir_arquivo(mid)
    except Exception:
        pass
    # varredura: redelivery de DM (cobre qualquer gatilho perdido)
    if S.ciclo_manut % 10 == 0:
        try:
            with S.L:
                dests = {e.get("para") for e in S.historico
                         if e.get("para") and e.get("de") == S.ident.get("id")
                         and e.get("ts", 0) >= agora() - RETENCAO}
            for d in dests:
                if d != S.ident.get("id") and presente(d):
                    threading.Thread(target=tentar_entregar_dm, args=(d,), daemon=True).start()
        except Exception:
            pass
    alvos = alvos_de_discagem()
    for alvo in alvos:
        threading.Thread(target=_dialar, args=alvo, daemon=True).start()
    for pid in ausentes():
        anunciar_saida(pid)
    t = agora()
    with S.L:
        for idp in list(S.pendentes):
            lista = S.pendentes[idp]
            S.pendentes[idp] = [x for x in lista if t - x[0].get("ts", 0) < 120]
            if not S.pendentes[idp]:
                S.pendentes.pop(idp, None)
        for idp in [k for k, v in S.pedidos_pub.items() if t - v > 300]:
            S.pedidos_pub.pop(idp, None)
        for mid in [k for k, v in S.montando.items() if t - v.get("ts", 0) > 600]:
            S.montando.pop(mid, None)
        for mid in [k for k, v in S.pedidos_arq.items() if t - v > 300]:
            S.pedidos_arq.pop(mid, None)


def thread_manutencao():
    while S.rodando:
        time.sleep(1.0)
        if not S.rodando:
            return
        try:
            manutencao()
        except Exception as e:
            log("erro na manutenção: %r" % (e,))
            D.registrar("manut_falha", motivo=type(e).__name__)


def thread_purga():
    from .app import purgar  # adiado: app importa thread_purga
    while S.rodando:
        time.sleep(INTERVALO_PURGA)
        if not S.rodando:
            return
        try:
            purgar()
        except Exception as e:
            D.registrar("purga_falha", motivo=type(e).__name__)


def dms_pendentes_para(para):
    """DMs (texto+arquivo) recentes para este destino, vindas de mim."""
    with S.L:
        out = [e for e in S.historico
               if e.get("para") == para and e.get("de") == S.ident.get("id")
               and e.get("ts", 0) >= agora() - RETENCAO]
    out.sort(key=lambda e: e.get("ts", 0))
    return out[-20:]


def tentar_entregar_dm(pid):
    """Reenvia DMs recentes direto ao destino quando ele volta. Sem gossip."""
    dbg = bool(os.environ.get("SENDERME_DEBUG"))
    if pid == S.ident.get("id"):
        return
    with S.L:
        css = [c for c in S.conns.get(pid, ()) if c in S.sockets_vivos]
    if not css:
        if dbg:
            log("redelivery %s: sem conn" % id_curto(pid))
        return  # sem conexão: não queima o throttle
    pend = dms_pendentes_para(pid)
    if not pend:
        return  # nada a fazer: também não queima o throttle
    if agora() - S.dm_retry.get(pid, 0) < 120:
        if dbg:
            log("redelivery %s: throttle" % id_curto(pid))
        return
    S.dm_retry[pid] = agora()
    if os.environ.get("SENDERME_DEBUG"):
        log("redelivery: %d p/ %s" % (len(pend), id_curto(pid)))
    for sock in css:
        try:
            for ev in pend:
                enviar(sock, {"t": "ev", "ev": ev})
                if ev.get("tipo") == "file":
                    blob = ler_bytes_arquivo(ev.get("mid", ""))
                    if blob is None:
                        continue
                    total = (len(blob) + CHUNK_ARQ - 1) // CHUNK_ARQ or 1
                    for idx in range(total):
                        enviar(sock, {"t": "file_chunk", "mid": ev["mid"], "idx": idx,
                                       "total": total,
                                       "dados": base64.b64encode(blob[idx * CHUNK_ARQ:(idx + 1) * CHUNK_ARQ]).decode()})
            log("DMs pendentes entregues p/ %s (%d)" % (id_curto(pid), len(pend)))
            D.registrar("redelivery", peer=D.curto(pid), n=len(pend))
            return
        except Exception as e:
            fechar_socket(sock, pid)
            log("falha redelivery p/ %s: %r" % (id_curto(pid), e))
            D.registrar("redelivery_falha", peer=D.curto(pid),
                        motivo=type(e).__name__)
    return
