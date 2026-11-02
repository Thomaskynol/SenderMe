#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SenderMe — purgar, main e desligar (extraído de senderme.py)."""
import os
import sys
import threading
import time
from . import estado as S
from . import diario as D
from .estado import agora, log
from .persist import (garantir_dados, ler_json, carregar_identidade,
                    carregar_conhecidos, carregar_historico,
                    reescrever_historico, _caminho)
from .presenca import aplicar_nick
from .eventos import reconstruir, criar_evento, publicar
from .arquivos import purgar_arquivos
from .tcp import abrir_servidor, loop_aceitar
from .transporte import fechar_socket
from .udp import thread_udp
from .manut import thread_manutencao, thread_purga
from .http import thread_http
from .meta import VERSAO
from config import RETENCAO


def purgar():
    with S.L:
        limite = agora() - RETENCAO
        # in-place: outros módulos/testes podem guardar referência às listas
        S.historico[:] = [e for e in S.historico if e.get("ts", 0) >= limite]
        S.vistos.clear()
        S.vistos.update(e["mid"] for e in S.historico if e.get("mid"))
        if not reescrever_historico():
            log("não consegui reescrever historico.jsonl "
                "(disco cheio ou sem permissão?)")
    try:
        purgar_arquivos()
    except Exception:
        pass


def main():
    garantir_dados()
    D.iniciar()  # diário em <SENDERME_HOME>/logs (não no /tmp do launcher)
    D.instalar_hook_threads()  # exceção em thread vai p/ o diário (só tipo)
    D.registrar("boot", versao=VERSAO, run=D.RUN_ID)
    from .update import recuperar_update
    try:
        teve = recuperar_update()  # update interrompido antes: restaura do backup
        D.registrar("update_recuperacao", teve=bool(teve))
    except Exception as e:
        log("recuperação de update falhou (%r): não vou servir mistura" % (e,))
        D.registrar("update_recuperacao_falha", motivo=type(e).__name__)
        sys.exit(1)
    # R3: recuperação parcial mantém .upd-pendente.json + backup; servir
    # agora seria mistura nova/velha — falha clara (nunca 42), sem servir.
    # lexists (não exists): symlink quebrado conta como pendente; incerteza
    # (OSError) bloqueia (fail closed). Ver _marcador_restante no preboot.
    marcador = os.path.join(S.PASTA, ".upd-pendente.json")
    try:
        pendente = os.path.lexists(marcador)
    except OSError:
        pendente = True
    if pendente:
        log("update incompleto: recuperação pendente em %s "
            "(backup em .upd-backup); reinicie para tentar de novo, "
            "sem servir mistura" % marcador)
        D.registrar("update_pendente")
        sys.exit(1)
    S.ident.update(carregar_identidade())
    log("seu id: %s" % S.ident["id"])
    carregar_conhecidos()
    with S.L:
        S.calados.update(x for x in ler_json("calados.json", []) if isinstance(x, str))
    for ev in carregar_historico():
        reconstruir(ev)
    with S.L:
        if S.historico:
            log("histórico local: %d eventos das últimas 24h" % len(S.historico))
    # login persistente: apelido.txt
    salvo = ""
    try:
        with open(_caminho("apelido.txt"), encoding="utf-8") as f:
            salvo = f.read().strip()[:24]
    except Exception:
        salvo = ""
    if salvo:
        with S.L:
            S.nick = salvo
            aplicar_nick(S.ident["id"], S.nick, ts=int(agora()))
            S.logado = True
        log("logado como %s (apelido salvo)" % S.nick)
    else:
        log("sem apelido salvo: faça login no navegador")

    srv = abrir_servidor()
    if srv is None:
        sys.exit(1)
    threading.Thread(target=loop_aceitar, args=(srv,), daemon=True).start()
    threading.Thread(target=thread_udp, daemon=True).start()
    threading.Thread(target=thread_manutencao, daemon=True).start()
    threading.Thread(target=thread_purga, daemon=True).start()
    threading.Thread(target=thread_http, daemon=True).start()
    log("Terminal = servidor. Use o navegador. Ctrl+C = sair (avisa a rede).")
    try:
        while S.rodando:
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    desligar()


def desligar():
    if not S.rodando:
        return
    S.rodando = False
    try:
        if S.logado and S.nick:
            ev = criar_evento("leave", S.ident["id"])
            publicar(ev)
            time.sleep(0.6)
    except Exception:
        pass
    for c in list(S.sockets_vivos):
        fechar_socket(c)
    log("Até logo!")
    os._exit(0)
