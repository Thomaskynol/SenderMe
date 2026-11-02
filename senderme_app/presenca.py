#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SenderMe — presenca (extraído de senderme.py sem mudar lógica)."""
import os
from . import estado as S
from .estado import agora, log, id_curto
from config import TIMEOUT_OFFLINE


def aplicar_nick(idp, novo, antigo=None, ts=0):
    """Atualiza nick com last-write-wins por ts (fix: msg velha não reverte)."""
    novo = (novo or "").strip()
    if not novo or len(novo) > 24:
        return
    try:
        ts = int(ts or 0)
    except Exception:
        ts = 0
    if ts < S.nick_ts.get(idp, 0):
        return  # evento velho: ignora
    S.nick_ts[idp] = ts
    if antigo:
        k = antigo.strip().lower()
        if S.nick_dono.get(k) == idp:
            del S.nick_dono[k]
    S.nick_de[idp] = novo
    k = novo.lower()
    dono = S.nick_dono.get(k)
    if dono is None or dono == idp:
        S.nick_dono[k] = idp
    else:
        # posse transfere se o dono sumiu (zerou e voltou com o mesmo nome);
        # com dois online, o dono atual mantém e o outro exibe (2).
        try:
            dono_online = presente(dono)
        except Exception:
            dono_online = False
        if not dono_online:
            S.nick_dono[k] = idp
            if os.environ.get("SENDERME_DEBUG"):
                log("nick %r: posse %s -> %s" % (novo, id_curto(dono), id_curto(idp)))
        elif os.environ.get("SENDERME_DEBUG"):
            log("nick %r: mantido %s (online)" % (novo, id_curto(dono)))
    d = S.conhecidos.get(idp)
    if d is not None:
        d["nick"] = novo


def dono_do_apelido(nome):
    return S.nick_dono.get((nome or "").strip().lower())


def apelido_exibido(idp, nome):
    dono = S.nick_dono.get((nome or "").strip().lower())
    if dono is None or dono == idp:
        return nome
    try:
        # (2) só desempata quem está online agora; histórico de quem saiu
        # mostra o nome puro (sem retroagir sufixo após transferência).
        if not presente(dono) or not presente(idp):
            return nome
    except Exception:
        return nome
    return nome + "(2)"


def apelido_de(idp):
    if idp == S.ident.get("id"):
        return S.nick
    return S.nick_de.get(idp, id_curto(idp))


def silenciado(idp):
    return idp in S.calados


def em_uso_online(nome, exceto=None):
    alvo = (nome or "").strip().lower()
    if not alvo:
        return None
    with S.L:
        for idp in list(S.visto_presenca) + [S.ident.get("id")]:
            if idp == exceto:
                continue
            if not presente(idp):
                continue
            if apelido_de(idp).strip().lower() == alvo:
                return idp
    return None


def presente(idp):
    if idp == S.ident.get("id"):
        return True
    if any(c in S.sockets_vivos for c in S.conns.get(idp, ())):
        return True
    if S.estado.get(idp) == "offline":
        return False  # saída anunciada: sem fantasma de 12 s
    return agora() - S.ultimo_contato.get(idp, 0) <= TIMEOUT_OFFLINE


def autor_silenciado(ev):
    if ev.get("tipo") == "leave":
        return silenciado(ev.get("txt", ""))
    return silenciado(ev.get("de", ""))


def tem_conexao_minha():
    return bool(S.sockets_vivos)


def pode_exibir_saida(alvo):
    if alvo == S.ident.get("id"):
        return True
    est = S.estado.get(alvo)
    if est == "online":
        return True
    if est is None and alvo in S.visto_presenca:
        return True
    return False


def lista_presentes():
    with S.L:
        ids = [S.ident["id"]]
        for i in set(list(S.visto_presenca) + list(S.peers) + list(S.conns)):
            if i != S.ident["id"] and presente(i):
                ids.append(i)
        out = []
        for i in ids:
            out.append({"id": i, "nick": apelido_de(i), "curto": id_curto(i),
                        "eu": i == S.ident["id"]})
    out.sort(key=lambda d: (not d["eu"], d["nick"].lower()))
    return out


def texto_quem():
    lst = lista_presentes()
    linhas = ["Presentes (%d):" % len(lst)]
    for d in lst:
        marca = "você" if d["eu"] else "     "
        linhas.append("  %s %-24s %s" % (marca, d["nick"], d["curto"]))
    return "\n".join(linhas)
