#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SenderMe — comandos (extraído de senderme.py sem mudar lógica)."""
import base64
import hashlib
import os
import threading
import time
from . import estado as S
from .estado import agora, log, ip_local, id_curto
from .eventos import criar_evento, criar_evento_file, publicar
from .presenca import (em_uso_online, aplicar_nick, apelido_de, apelido_exibido, lista_presentes, texto_quem, presente, autor_silenciado)
from .arquivos import salvar_bytes_arquivo, purgar_arquivos, tem_arquivo
from .transporte import enviar, fechar_socket
from .persist import anexar_historico, garantir_dados, _caminho, salvar_calados
from config import (MAX_TEXTO, RETENCAO, FIXOS, PORTA_TCP, PORTA_UDP, PORTA_HTTP, MAX_ARQUIVO, CHUNK_ARQ)


AJUDA_TXT = (
    "/dm @apelido mensagem — mensagem privada\n"
    "/quem — quem está presente agora\n"
    "/rede — IP/porta de cada par conectado\n"
    "/apelido novo — troca seu apelido (também na aba Configs)\n"
    "/calar @apelido — deixa de ver a pessoa (toggle)\n"
    "/ajuda — esta lista"
)


def validar_nick(novo):
    novo = (novo or "").strip()
    if not novo:
        return None, "Apelido não pode ficar vazio."
    if len(novo) > 24:
        return None, "Apelido longo demais (máx. 24 caracteres)."
    return novo, None


def fazer_login(novo):
    from .manut import anunciar_entrada as _anunciar_entrada
    novo, err = validar_nick(novo)
    if err:
        return False, err
    conflito = em_uso_online(novo, exceto=S.ident["id"])
    if conflito:
        return False, "O apelido %r já está em uso por %s — escolha outro." % (novo, apelido_de(conflito))
    with S.L:
        S.nick = novo
        aplicar_nick(S.ident["id"], novo, ts=int(agora()))
        S.logado = True
    try:
        garantir_dados()
        with open(_caminho("apelido.txt"), "w", encoding="utf-8") as f:
            f.write(novo)
    except Exception:
        log("não consegui gravar apelido.txt em %s "
            "(disco cheio ou sem permissão?)" % S.DADOS)
        threading.Thread(target=_anunciar_entrada, daemon=True).start()
        return True, ("Você é %s. (aviso: apelido.txt não foi salvo — "
                      "fará login de novo no próximo boot)" % novo)
    threading.Thread(target=_anunciar_entrada, daemon=True).start()
    return True, "Você é %s." % novo


def trocar_apelido(novo):
    if not S.logado:
        return False, "Faça login primeiro."
    novo, err = validar_nick(novo)
    if err:
        return False, err
    with S.L:
        if novo.lower() == S.nick.lower():
            return False, "Este já é o seu apelido."
    conflito = em_uso_online(novo, exceto=S.ident["id"])
    if conflito:
        return False, "O apelido %r já está em uso por %s — escolha outro." % (novo, apelido_de(conflito))
    with S.L:
        antigo = S.nick
    ev = criar_evento("nick", novo)
    with S.L:
        S.nick = novo
        aplicar_nick(S.ident["id"], novo, antigo=antigo, ts=int(agora()))
    try:
        garantir_dados()
        with open(_caminho("apelido.txt"), "w", encoding="utf-8") as f:
            f.write(novo)
    except Exception:
        log("não consegui gravar apelido.txt em %s "
            "(disco cheio ou sem permissão?)" % S.DADOS)
        publicar(ev)
        return True, ("Agora você é %s. (aviso: apelido.txt não foi salvo — "
                      "voltará ao anterior no próximo boot)" % novo)
    publicar(ev)
    return True, "Agora você é %s." % novo


def toggle_calar(nome):
    nome = (nome or "").strip().lstrip("@")
    if not nome:
        return False, "Uso: /calar @apelido"
    idp = achar_id(nome)
    if not idp:
        return False, "Não encontrei ninguém chamado %r." % nome
    with S.L:
        if idp in S.calados:
            S.calados.discard(idp)
            msg = "%s voltou a aparecer na sua tela." % apelido_de(idp)
        else:
            S.calados.add(idp)
            msg = "Você não vai ver mais %s (a rede continua guardando)." % apelido_de(idp)
    if not salvar_calados():
        log("não consegui gravar calados.json em %s "
            "(disco cheio ou sem permissão?)" % S.DADOS)
        return True, msg + " (aviso: calados.json não foi salvo)"
    return True, msg


def enviar_dm_para(alvo_nome, texto, com_estado=False):
    """DM direta. Retorna (ok, msg); com com_estado=True, (ok, msg, estado, transmitida).

    `estado` ∈ {entregue, guardada, somente_memoria, erro} para a UI decidir
    sem farejar texto (Achado 1); `ok`/`msg` inalterados (compat). `transmitida`
    (Item 2) é true quando os bytes foram entregues ao socket — NUNCA afirma
    confirmação de recebimento/leitura pelo destinatário. Distingue as duas
    `somente_memoria`: enviada sem persistir (true) vs não enviada (false).
    Item 3: a camada HTTP expõe `nivel` ("socket" se transmitida, senão
    "local"), `confirmado=false` (hoje nunca há confirmação) e `peers`
    (nº de peers conectados); valores aqui intactos p/ compat."""
    def _ret(ok, msg, estado, transmitida):
        if com_estado:
            return ok, msg, estado, transmitida
        return ok, msg
    partes_nome = (alvo_nome or "").strip()
    if not partes_nome.startswith("@"):
        return _ret(False, "Uso: /dm @apelido mensagem", "erro", False)
    alvo = achar_id(partes_nome)
    texto = (texto or "").strip()
    if not alvo:
        return _ret(False, "Não encontrei %r." % partes_nome, "erro", False)
    if not texto:
        return _ret(False, "Mensagem vazia.", "erro", False)
    if len(texto) > MAX_TEXTO:
        texto = texto[:MAX_TEXTO]
    with S.L:
        cs = list(S.conns.get(alvo, ()))
    ev = criar_evento("dm", texto, para=alvo)
    with S.L:
        S.vistos.add(ev["mid"])
        S.historico.append(ev)
        persist_ok = anexar_historico(ev)
        if not persist_ok:
            log("não consegui anexar DM em historico.jsonl "
                "(disco cheio ou sem permissão?)")
    if not cs:
        if persist_ok:
            return _ret(False, "Sem conexão com %s agora (guardada; entrego quando voltar)." % apelido_de(alvo), "guardada", False)
        return _ret(False, ("Sem conexão com %s agora (AVISO: não consegui salvar "
                       "em historico.jsonl — ficará só em memória e será "
                       "perdida ao reiniciar)." % apelido_de(alvo)), "somente_memoria", False)
    ok = False
    for c in cs:
        try:
            enviar(c, {"t": "ev", "ev": ev})
            ok = True
            break
        except Exception:
            fechar_socket(c, alvo)
    if not ok:
        if persist_ok:
            return _ret(False, "Não consegui enviar para %s (guardada; entrego quando voltar)." % apelido_de(alvo), "guardada", False)
        return _ret(False, ("Não consegui enviar para %s (AVISO: não consegui salvar "
                       "em historico.jsonl — ficará só em memória e será "
                       "perdida ao reiniciar)." % apelido_de(alvo)), "somente_memoria", False)
    if not persist_ok:
        return _ret(True, ("Enviada para %s (aviso: não consegui salvar em "
                      "historico.jsonl — ficará só em memória)." % apelido_de(alvo)), "somente_memoria", True)
    return _ret(True, "", "entregue", True)


def enviar_dm_arquivo(alvo_nome, caption, nome_arq, blob):
    if len(blob) > MAX_ARQUIVO:
        return False, "Arquivo grande demais (máx. 20 MB)."
    alvo = achar_id((alvo_nome or "").strip())
    if not alvo:
        return False, "Não encontrei %r." % alvo_nome
    sha = hashlib.sha256(blob).hexdigest()
    ev = criar_evento_file((caption or "")[:MAX_TEXTO], nome_arq, len(blob), sha, para=alvo)
    if not salvar_bytes_arquivo(ev["mid"], blob):
        return False, "Não consegui salvar o arquivo."
    purgar_arquivos()
    with S.L:
        cs = list(S.conns.get(alvo, ()))
    if not cs:
        with S.L:
            S.vistos.add(ev["mid"])
            S.historico.append(ev)
            persist_ok = anexar_historico(ev)
            if not persist_ok:
                log("não consegui anexar arquivo-DM em historico.jsonl "
                    "(disco cheio ou sem permissão?)")
        if persist_ok:
            return False, "Sem conexão com %s agora (arquivo salvo local)." % apelido_de(alvo)
        return False, ("Sem conexão com %s agora (arquivo salvo local; AVISO: "
                       "evento não foi salvo em historico.jsonl — ficará só "
                       "em memória e será perdido ao reiniciar)." % apelido_de(alvo))
    ok = False
    for c in cs:
        try:
            enviar(c, {"t": "ev", "ev": ev})
            ok = True
            break
        except Exception:
            fechar_socket(c, alvo)
    if ok:
        total = (len(blob) + CHUNK_ARQ - 1) // CHUNK_ARQ or 1
        for c in list(S.conns.get(alvo, ())):
            try:
                for idx in range(total):
                    ped = blob[idx * CHUNK_ARQ:(idx + 1) * CHUNK_ARQ]
                    enviar(c, {"t": "file_chunk", "mid": ev["mid"], "idx": idx,
                               "total": total, "dados": base64.b64encode(ped).decode()})
                break
            except Exception:
                fechar_socket(c, alvo)
    with S.L:
        S.vistos.add(ev["mid"])
        S.historico.append(ev)
        persist_ok = anexar_historico(ev)
        if not persist_ok:
            log("não consegui anexar arquivo em historico.jsonl "
                "(disco cheio ou sem permissão?)")
    if not persist_ok:
        return True, ("Enviada para %s (aviso: evento não foi salvo em "
                      "historico.jsonl — ficará só em memória)." % apelido_de(alvo))
    return True, ""


def publicar_arquivo_global(caption, nome_arq, blob):
    if len(blob) > MAX_ARQUIVO:
        return False, "Arquivo grande demais (máx. 20 MB)."
    sha = hashlib.sha256(blob).hexdigest()
    ev = criar_evento_file((caption or "")[:MAX_TEXTO], nome_arq, len(blob), sha)
    if not salvar_bytes_arquivo(ev["mid"], blob):
        return False, "Não consegui salvar o arquivo."
    purgar_arquivos()
    publicar(ev)
    return True, ""


def tratar_comando_web(texto, com_estado=False):
    """Retorna (ok, resposta). Com com_estado=True, (ok, resposta, estado, transmitida).

    `estado` segue o contrato da API (Achado 1); `ok`/resposta inalterados.
    Item 3 (contrato explícito, valores intactos p/ compat): `transmitida`
    tem semântica por contexto — no /dm repassa o socket (bytes entregues,
    sem confirmar recebimento/leitura); nos demais, true = aceitação local
    (publicado/aceito; reenvio duplicaria). A camada HTTP desambigua com
    `nivel` ("socket" só p/ /dm com transmitida, senão "local"),
    `confirmado=false` (hoje nunca há confirmação) e `peers` (nº conectados);
    nenhum afirma recebimento/leitura."""
    def _ret(ok, msg, estado, transmitida=None):
        if transmitida is None:
            transmitida = bool(ok)
        if com_estado:
            return ok, msg, estado, transmitida
        return ok, msg
    if not S.logado:
        return _ret(False, "Faça login primeiro.", "erro")
    linha = (texto or "").replace("\r\n", "\n")
    if not linha.strip():
        return _ret(False, "", "erro")
    if not linha.lstrip().startswith("/"):
        msg = linha.strip(" \t")
        # preserva quebras internas, remove linhas vazias nas bordas
        msg = msg.strip("\n")
        if not msg.strip():
            return _ret(False, "", "erro")
        if len(msg) > MAX_TEXTO:
            msg = msg[:MAX_TEXTO]
        publicar(criar_evento("msg", msg))
        return _ret(True, "", "entregue")
    cmd, _, resto = linha.strip().partition(" ")
    cmd = cmd.lower()
    if cmd == "/ajuda":
        return _ret(True, AJUDA_TXT, "entregue")
    if cmd == "/quem":
        return _ret(True, texto_quem(), "entregue")
    if cmd == "/rede":
        return _ret(True, texto_rede(), "entregue")
    if cmd == "/apelido":
        ok, msg = trocar_apelido(resto)
        return _ret(ok, msg, "entregue" if ok else "erro")
    if cmd == "/calar":
        ok, msg = toggle_calar(resto)
        return _ret(ok, msg, "entregue" if ok else "erro")
    if cmd == "/dm":
        partes = resto.split(None, 1)
        if len(partes) < 2:
            return _ret(False, "Uso: /dm @apelido mensagem", "erro")
        return enviar_dm_para(partes[0], partes[1], com_estado=com_estado)
    if cmd in ("/sair", "/limpar"):
        return _ret(False, "Comando removido na versão navegador. Para sair, Ctrl+C no terminal do servidor.", "erro")
    return _ret(False, "Comando desconhecido %r — digite /ajuda." % cmd, "erro")


def achar_id(nome):
    alvo = (nome or "").strip().lstrip("@").lower()
    if not alvo:
        return None
    with S.L:
        candidatos = set(S.nick_de) | set(S.conhecidos)
        achados = [i for i in candidatos
                   if i != S.ident.get("id")
                   and S.nick_de.get(i, S.conhecidos.get(i, {}).get("nick", ""))
                   .strip().lower() == alvo]
        for i in achados:
            if presente(i):
                return i
        return achados[0] if achados else None


def texto_rede():
    linhas = ["Você está em %s (TCP %d / UDP %d / HTTP %d)"
             % (ip_local(), PORTA_TCP, PORTA_UDP, PORTA_HTTP)]
    with S.L:
        for fx in FIXOS:
            linhas.append("  fixo  %s" % fx)
        for i, cs in S.conns.items():
            p = S.peers.get(i, {})
            ip, porta = p.get("ip", "?"), p.get("porta", "?")
            linhas.append("  %s:%s  %s  (%d conexão(ões))" % (ip, porta, id_curto(i), len(cs)))
    return "\n".join(linhas)


def hora_de(ts):
    try:
        return time.strftime("%d/%m %H:%M", time.localtime(ts))
    except Exception:
        return "--/-- --:--"


def cor_idx(idp):
    try:
        h = int(hashlib.sha256((idp or "?").encode()).hexdigest()[:4], 16)
        return h % 8
    except Exception:
        return 0


def evento_para_api(ev):
    tipo = ev.get("tipo")
    ts = ev.get("ts", 0)
    de = ev.get("de", "")
    proprio = (de == S.ident.get("id"))
    dm = bool(ev.get("para"))
    base = {"mid": ev.get("mid", ""), "tipo": tipo, "de": de, "ts": ts,
            "hora": hora_de(ts), "proprio": proprio, "dm": dm,
            "cor": cor_idx(de)}
    if tipo in ("msg", "dm"):
        base["nick"] = apelido_exibido(de, ev.get("nick", ""))
        base["txt"] = ev.get("txt", "")
    elif tipo == "file":
        base["nick"] = apelido_exibido(de, ev.get("nick", ""))
        base["txt"] = ev.get("txt", "")
        arq = ev.get("arq") or {}
        mid = ev.get("mid", "")
        base["arq"] = {"nome": arq.get("nome", "arquivo"),
                       "tamanho": int(arq.get("tamanho", 0)),
                       "pronto": tem_arquivo(mid)}
    elif tipo == "join":
        base["nick"] = apelido_exibido(de, ev.get("nick", ""))
        base["txt"] = "* %s entrou no chat" % base["nick"]
    elif tipo == "leave":
        alvo = ev.get("txt", "")
        base["nick"] = apelido_de(alvo)
        base["txt"] = "* %s saiu do chat" % base["nick"]
    elif tipo == "nick":
        base["nick"] = apelido_exibido(de, ev.get("nick", ""))
        base["txt"] = "* %s agora é %s" % (base["nick"], ev.get("txt", ""))
    else:
        return None
    return base


def mensagens_para_api(depois_mid, limite=200):
    with S.L:
        if not S.historico:
            return [], lista_presentes()
        if depois_mid:
            ini = None
            for i, e in enumerate(S.historico):
                if e.get("mid") == depois_mid:
                    ini = i + 1
                    break
            if ini is None:
                janela = S.historico[-50:]
            else:
                janela = S.historico[ini:ini + limite]
        else:
            janela = S.historico[-50:]
        out = []
        for ev in janela:
            if autor_silenciado(ev):
                continue
            d = evento_para_api(ev)
            if d:
                out.append(d)
        presentes = lista_presentes()
    return out, presentes
