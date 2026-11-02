#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SenderMe — eventos (extraído de senderme.py sem mudar lógica)."""
import hashlib
import os
import secrets
import threading
from . import estado as S
from .estado import agora, log, id_curto
from .presenca import aplicar_nick, tem_conexao_minha, pode_exibir_saida
from .persist import salvar_conhecidos, anexar_historico, anexar_lote
from .arquivos import tem_arquivo
from .transporte import enviar, fechar_socket
from config import TIPOS_EVENTO, MAX_TEXTO, MAX_ARQUIVO, MAX_PENDENTES, MAX_SYNC, RETENCAO
from crypto import assinar, conferir, fingerprint


def campo_assinatura(ev):
    base = "%s|%s|%s|%d|%s|%s" % (ev["tipo"], ev["de"], ev["nick"],
                                  int(ev["ts"]), ev.get("txt", ""), ev["nonce"])
    if ev.get("para"):
        base += "|" + ev.get("para", "")
    arq = ev.get("arq")
    if isinstance(arq, dict):
        base += "|%s|%d|%s" % (arq.get("nome", ""), int(arq.get("tamanho", 0)),
                               arq.get("sha256", ""))
    return base


def criar_evento(tipo, txt, para=None):
    ev = {"tipo": tipo, "de": S.ident["id"], "nick": S.nick,
          "ts": int(agora()), "txt": txt, "nonce": secrets.token_hex(8)}
    if para:
        ev["para"] = para
    campo = campo_assinatura(ev).encode("utf-8")
    ev["sig"] = assinar(campo, S.ident).hex()
    ev["mid"] = hashlib.sha256(campo).hexdigest()
    return ev


def limpar_nome_arq(nome):
    nome = os.path.basename(nome or "arquivo")
    nome = nome.replace("\r", "").replace("\n", "").strip()
    if not nome or nome in (".", ".."):
        nome = "arquivo"
    return nome[:120]


def criar_evento_file(caption, nome, tamanho, sha256, para=None):
    nome = limpar_nome_arq(nome)
    ev = {"tipo": "file", "de": S.ident["id"], "nick": S.nick,
          "ts": int(agora()), "txt": caption or "", "nonce": secrets.token_hex(8),
          "arq": {"nome": nome, "tamanho": int(tamanho), "sha256": sha256}}
    if para:
        ev["para"] = para
    campo = campo_assinatura(ev).encode("utf-8")
    ev["sig"] = assinar(campo, S.ident).hex()
    ev["mid"] = hashlib.sha256(campo).hexdigest()
    return ev


def conferir_evento(ev):
    if ev["de"] == S.ident.get("id"):
        pub = {"n": S.ident["n"], "e": S.ident["e"]}
    else:
        pub = S.conhecidos.get(ev["de"])
    if not pub:
        return None
    try:
        campo = campo_assinatura(ev).encode("utf-8")
        sig = bytes.fromhex(ev.get("sig", ""))
    except Exception:
        return False
    if ev.get("mid") != hashlib.sha256(campo).hexdigest():
        return False
    return conferir(campo, sig, pub["n"], pub["e"])


def guardar_pendente(ev, origem):
    lista = S.pendentes.setdefault(ev["de"], [])
    if len(lista) < MAX_PENDENTES:
        lista.append((ev, origem))
    pedir_pub(ev["de"], origem)


def pedir_pub(idp, origem=None):
    t = agora()
    if t - S.pedidos_pub.get(idp, 0) < 60:
        return
    S.pedidos_pub[idp] = t
    msg = {"t": "pub_req", "id": idp}
    alvos = []
    if origem is not None:
        alvos = [c for c in S.conns.get(origem, ())]
    if not alvos:
        with S.L:
            for cs in S.conns.values():
                alvos.extend(cs)
    for c in alvos[:4]:
        try:
            enviar(c, msg)
        except Exception:
            pass


def receber_pub(msg):
    try:
        n = int(msg["n"], 16)
        e = int(msg["e"])
        idp = msg["id"]
    except Exception:
        return None
    if idp == S.ident.get("id"):
        return None  # nunca registra a própria chave (auto-dial via seeds)
    if fingerprint(n, e) != idp:
        return None
    novo = False
    with S.L:
        d = S.conhecidos.get(idp)
        if d is None:
            S.conhecidos[idp] = {"n": n, "e": e, "nick": ""}
            novo = True
        elif d["n"] != n:
            return None
        lista = S.pendentes.pop(idp, [])
    if novo:
        if not salvar_conhecidos():
            log("não consegui gravar conhecidos.json em %s "
                "(disco cheio ou sem permissão?)" % S.DADOS)
    if lista:
        for ev, origem in lista:
            processar(ev, origem=origem)
    return idp


def pedir_arquivo(mid, origem=None):
    t = agora()
    if t - S.pedidos_arq.get(mid, 0) < 30:
        return
    if tem_arquivo(mid):
        return
    S.pedidos_arq[mid] = t
    msg = {"t": "file_req", "mid": mid}
    alvos = []
    with S.L:
        if origem is not None:
            alvos = [c for c in S.conns.get(origem, ())]
        if not alvos:
            for cs in S.conns.values():
                alvos.extend(cs)
    for c in alvos[:4]:
        try:
            enviar(c, msg)
        except Exception:
            pass


def processar(ev, origem=None, gravar=True, disco=True):
    """disco=False adia a escrita (o chamador persiste o lote depois)."""
    from .manut import tentar_entregar_dm as _entregar_dm
    from .manut import anunciar_entrada as _anunciar_entrada
    if not isinstance(ev, dict):
        return False
    tipo = ev.get("tipo")
    if tipo not in TIPOS_EVENTO:
        return False
    for k in ("de", "nick", "ts", "nonce", "sig", "mid"):
        if ev.get(k) in (None, ""):
            return False
    if ev.get("txt") is None or len(str(ev["txt"])) > MAX_TEXTO * 4:
        return False
    if tipo in ("dm",) and not ev.get("para"):
        return False
    if tipo == "file":
        arq = ev.get("arq")
        if not isinstance(arq, dict):
            return False
        try:
            tam = int(arq.get("tamanho", 0))
        except Exception:
            return False
        if tam <= 0 or tam > MAX_ARQUIVO:
            return False
        nome_a = arq.get("nome", "")
        if not nome_a or len(nome_a) > 120 or "/" in nome_a or "\\" in nome_a:
            return False
        if "\r" in nome_a or "\n" in nome_a:
            return False
        sha_a = arq.get("sha256", "")
        if len(sha_a) != 64 or any(c not in "0123456789abcdef" for c in sha_a.lower()):
            return False

    with S.L:
        if ev["mid"] in S.vistos:
            return False
        if ev["ts"] < agora() - RETENCAO:
            S.vistos.add(ev["mid"])
            return False
        ok = conferir_evento(ev)

    if ok is None:
        guardar_pendente(ev, origem)
        return False
    if ok is False:
        if os.environ.get("SENDERME_DEBUG"):
            log("evento rejeitado tipo=%s de=%s" % (ev.get("tipo"), id_curto(str(ev.get("de")))))
        return False
    # DM (texto ou arquivo): só para mim
    if ev.get("para") and ev["para"] != S.ident.get("id") and ev["de"] != S.ident.get("id"):
        return False

    corrigir = False
    with S.L:
        if ev["mid"] in S.vistos:
            return False
        S.vistos.add(ev["mid"])
        ts = int(ev.get("ts", 0))
        if tipo == "nick":
            aplicar_nick(ev["de"], ev["txt"], antigo=ev["nick"], ts=ts)
        else:
            aplicar_nick(ev["de"], ev["nick"], ts=ts)

        if tipo == "leave":
            alvo = ev["txt"]
            if alvo == S.ident.get("id") and tem_conexao_minha():
                if agora() - S.ultima_ajuste_eu > 30:
                    corrigir = True
            elif pode_exibir_saida(alvo):
                S.estado[alvo] = "offline"
        elif tipo == "join":
            if S.estado.get(ev["de"]) != "online":
                S.estado[ev["de"]] = "online"
                threading.Thread(target=_entregar_dm, args=(ev["de"],), daemon=True).start()

        if gravar:
            S.historico.append(ev)
            if disco:
                if not anexar_historico(ev):
                    log("não consegui anexar evento em historico.jsonl "
                        "(disco cheio ou sem permissão?)")

    # arquivo global: pede conteúdo se não tenho
    if tipo == "file" and not ev.get("para"):
        if not tem_arquivo(ev["mid"]):
            pedir_arquivo(ev["mid"], origem)
    if tipo != "dm" and not ev.get("para"):
        propagar(ev, origem)
    if corrigir:
        threading.Thread(target=_anunciar_entrada, daemon=True).start()
    return True


def publicar(ev):
    processar(ev, origem=None, gravar=True)


def propagar(ev, origem=None):
    with S.L:
        alvos = [(idp, list(cs)) for idp, cs in S.conns.items() if idp != origem]
    for idp, cs in alvos:
        for c in cs:
            try:
                enviar(c, {"t": "ev", "ev": ev})
                break
            except Exception:
                fechar_socket(c, idp)


def reconstruir(ev):
    if not isinstance(ev, dict):
        return
    tipo = ev.get("tipo")
    if tipo not in TIPOS_EVENTO:
        return
    if ev.get("mid") in S.vistos:
        return
    if ev.get("ts", 0) < agora() - RETENCAO:
        return
    if conferir_evento(ev) is not True:
        return
    if ev.get("para") and ev.get("para") != S.ident.get("id") and ev.get("de") != S.ident.get("id"):
        return
    with S.L:
        S.vistos.add(ev["mid"])
        ts = int(ev.get("ts", 0))
        if tipo == "nick":
            aplicar_nick(ev["de"], ev["txt"], antigo=ev["nick"], ts=ts)
        else:
            aplicar_nick(ev["de"], ev["nick"], ts=ts)
        if tipo == "join":
            S.estado[ev["de"]] = "online"
        elif tipo == "leave" and ev.get("txt") != S.ident.get("id"):
            S.estado[ev["txt"]] = "offline"
        S.historico.append(ev)


def tratar_hist(evs, pubs, pid):
    if isinstance(pubs, list):
        for p in pubs:
            if isinstance(p, dict):
                receber_pub(p)
    if not isinstance(evs, list):
        return
    novos = []
    for ev in evs[:MAX_SYNC]:
        if processar(ev, origem=pid, gravar=True, disco=False):
            novos.append(ev)
    if not anexar_lote(novos):  # um open/write para o lote inteiro
        log("não consegui persistir lote do sync em historico.jsonl "
            "(disco cheio ou sem permissão?)")
    # puxa conteúdo dos arquivos anunciados que ainda não tenho
    with S.L:
        faltando = [e["mid"] for e in S.historico
                    if e.get("tipo") == "file" and not e.get("para")
                    and not tem_arquivo(e.get("mid", ""))]
    for mid in faltando[-20:]:
        pedir_arquivo(mid, pid)
