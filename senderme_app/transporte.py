#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SenderMe — transporte (extraído de senderme.py sem mudar lógica)."""
import json
import socket
import struct
import threading
from . import estado as S
from . import diario as D
from config import MAX_QUADRO, TIMEOUT_SOCK


def enviar(sock, obj):
    b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    if len(b) > MAX_QUADRO:
        raise ValueError("quadro grande demais")
    with S.L:
        lck = S.envios_lck.get(sock)
        if lck is None:
            lck = threading.Lock()
            S.envios_lck[sock] = lck
    try:
        with lck:
            sock.sendall(struct.pack("!I", len(b)) + b)
    except Exception as e:
        # só rótulo do erro + tamanho (nunca payload nem str(exc)).
        D.registrar("envio_falha", bytes=len(b), motivo=type(e).__name__)
        raise


def _recv_exato(sock, n):
    buf = bytearray()
    while len(buf) < n:
        pedaco = sock.recv(n - len(buf))
        if not pedaco:
            raise ConnectionError("conexão fechada")
        buf.extend(pedaco)
    return bytes(buf)


def ler_quadro(sock):
    n = struct.unpack("!I", _recv_exato(sock, 4))[0]
    if n > MAX_QUADRO:
        raise ValueError("quadro grande demais")
    return json.loads(_recv_exato(sock, n).decode("utf-8"))


def preparar_socket(s):
    try:
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except (OSError, AttributeError):
        pass
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    except (OSError, AttributeError):
        pass
    try:
        s.settimeout(TIMEOUT_SOCK)  # recv e send limitados: nada trava para sempre
    except (OSError, AttributeError):
        pass


def fechar_socket(s, pid=None):
    caiu = False
    with S.L:
        S.sockets_vivos.discard(s)
        S.envios_lck.pop(s, None)
        if pid:
            cs = S.conns.get(pid)
            if cs is not None:
                cs.discard(s)
                if not cs:
                    S.conns.pop(pid, None)
                    caiu = True
    if caiu:
        D.registrar("peer_desconectou", peer=D.curto(pid),
                    peers_conectados=len(S.conns))
    try:
        s.close()
    except Exception:
        pass
