#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SenderMe — arquivos (extraído de senderme.py sem mudar lógica)."""
import base64
import hashlib
import os
from . import estado as S
from .estado import agora
from .persist import garantir_dados
from .transporte import enviar
from config import CHUNK_ARQ, MAX_ARQUIVO, MAX_ARQUIVOS_TOTAL, RETENCAO


def caminho_bin(mid):
    return os.path.join(S.DIR_ARQ, mid + ".bin")


def tem_arquivo(mid):
    try:
        return os.path.isfile(caminho_bin(mid))
    except Exception:
        return False


def salvar_bytes_arquivo(mid, dados):
    garantir_dados()
    with S._disco:
        try:
            tmp = caminho_bin(mid) + ".tmp"
            with open(tmp, "wb") as f:
                f.write(dados)
            os.replace(tmp, caminho_bin(mid))
            return True
        except Exception:
            return False


def ler_bytes_arquivo(mid):
    try:
        with open(caminho_bin(mid), "rb") as f:
            return f.read()
    except Exception:
        return None


def total_arquivos():
    tot = 0
    try:
        for nome in os.listdir(S.DIR_ARQ):
            if nome.endswith(".bin"):
                try:
                    tot += os.path.getsize(os.path.join(S.DIR_ARQ, nome))
                except OSError:
                    pass
    except FileNotFoundError:
        pass
    return tot


def evento_por_mid(mid):
    with S.L:
        for ev in S.historico:
            if ev.get("mid") == mid:
                return dict(ev)
    return None


def purgar_arquivos():
    """Aplica 24h + teto 60MB. Remove conteúdo, mantém metadados do evento."""
    garantir_dados()
    limite = agora() - RETENCAO
    with S.L:
        ts_por_mid = {e.get("mid"): e.get("ts", 0) for e in S.historico
                      if e.get("tipo") == "file" and e.get("mid")}
    try:
        nomes = [n for n in os.listdir(S.DIR_ARQ) if n.endswith(".bin")]
    except FileNotFoundError:
        return
    # 1) remove por idade
    for nome in nomes:
        mid = nome[:-4]
        ts = ts_por_mid.get(mid)
        if ts is None:
            # sem evento correspondente: usa mtime
            try:
                mt = os.path.getmtime(os.path.join(S.DIR_ARQ, nome))
                if mt < limite:
                    os.remove(os.path.join(S.DIR_ARQ, nome))
            except OSError:
                pass
        elif ts < limite:
            try:
                os.remove(os.path.join(S.DIR_ARQ, nome))
            except OSError:
                pass
    # 2) remove mais antigos até caber em 60MB
    def info():
        out = []
        for nome in os.listdir(S.DIR_ARQ):
            if not nome.endswith(".bin"):
                continue
            mid = nome[:-4]
            p = os.path.join(S.DIR_ARQ, nome)
            try:
                sz = os.path.getsize(p)
            except OSError:
                continue
            out.append((ts_por_mid.get(mid, 0), sz, p))
        return out
    try:
        while sum(s for _, s, _ in info()) > MAX_ARQUIVOS_TOTAL:
            lista = sorted(info())
            if not lista:
                break
            _, _, velho = lista[0]
            try:
                os.remove(velho)
            except OSError:
                break
    except FileNotFoundError:
        pass


def servir_arquivo(pid, mid):
    dados = ler_bytes_arquivo(mid)
    if dados is None:
        return
    total = (len(dados) + CHUNK_ARQ - 1) // CHUNK_ARQ or 1
    with S.L:
        cs = list(S.conns.get(pid, ()))
    if not cs:
        return
    sock = cs[0]
    for idx in range(total):
        ped = dados[idx * CHUNK_ARQ:(idx + 1) * CHUNK_ARQ]
        try:
            enviar(sock, {"t": "file_chunk", "mid": mid, "idx": idx,
                          "total": total, "dados": base64.b64encode(ped).decode()})
        except Exception:
            return


def receber_chunk(q):
    try:
        mid = q["mid"]
        idx = int(q["idx"])
        total = int(q["total"])
        dados = base64.b64decode(q["dados"])
    except Exception:
        return
    if not isinstance(mid, str) or len(mid) != 64:
        return
    if total <= 0 or total > (MAX_ARQUIVO // CHUNK_ARQ + 2):
        return
    if idx < 0 or idx >= total or len(dados) > CHUNK_ARQ + 1024:
        return
    ev = evento_por_mid(mid)
    if ev is None or ev.get("tipo") != "file":
        return
    if tem_arquivo(mid):
        return
    with S.L:
        slot = S.montando.setdefault(mid, {"total": total, "partes": {}, "ts": agora()})
        if slot["total"] != total:
            return
        slot["partes"][idx] = dados
        slot["ts"] = agora()
        if len(slot["partes"]) < total:
            return
        partes = [slot["partes"][i] for i in range(total)]
    blob = b"".join(partes)
    try:
        esperado = ev["arq"]["sha256"]
    except Exception:
        with S.L:
            S.montando.pop(mid, None)
        return
    if hashlib.sha256(blob).hexdigest() != esperado:
        with S.L:
            S.montando.pop(mid, None)
        return
    if salvar_bytes_arquivo(mid, blob):
        purgar_arquivos()
    with S.L:
        S.montando.pop(mid, None)
