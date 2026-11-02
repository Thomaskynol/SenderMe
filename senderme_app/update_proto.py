#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SenderMe — update_proto: protocolo/transferência do update.

Extraído de senderme_app/update.py (1.11, sem mudar lógica):
versão/manifesto, oferta (ver/meta com reoferta limitada), pedido
e entrega de chunks. NÃO importa senderme_app.update (update.py é
quem importa daqui); o disparo do download usa import adiado de
update.baixar_update. Sem estado global próprio além do controle
de reoferta; preboot.py segue autônomo (script direto, sem
importar senderme_app).
"""
import base64
import json
import os
import threading
import time
from . import estado as S
from . import diario as D
from .estado import agora, log, id_curto
from .transporte import enviar
from config import CHUNK_ARQ
from crypto import conferir

# Reoferta (achado 2 da revisão 1.10): a marca (peer, versão) só sai após
# envio confirmado — falha nunca marca, e a próxima ver retenta. _META_SOCK
# guarda em qual socket a entrega saiu (morreu → reoferta imediata, 1 push
# por handshake). _ULTIMA_TENTATIVA impõe o teto de frequência (piso do
# redial TIMEOUT_DIAL=10 s: ver repetida após falha recente não tempesta).
# _REOFERTA_AGENDADA (1.12): quando o teto suprime uma oferta p/ peer
# antigo ainda conectado — ou quando o envio falha com o peer ainda
# conectado — agenda UMA tentativa diferida p/ o fim do intervalo
# (Timer daemon). A tentativa revalida peer/socket/versão e reoferta;
# cancela no disconnect (sem conexão viva, nada é enviado, sem erro).
_COOLDOWN_REOFERTA = 10.0
_ULTIMA_TENTATIVA = {}
_META_SOCK = {}
_REOFERTA_AGENDADA = {}


def _caminho_marcador():
    return os.path.join(S.PASTA, ".upd-pendente.json")


def _ha_recuperacao_pendente():
    """Journal de update anterior no disco (B): nova transação não pode
    sobrescrever backup+marcador — o boot precisa recuperar primeiro.
    lexists (não exists): symlink pendente conta como pendente (fail closed)."""
    try:
        return os.path.lexists(_caminho_marcador())
    except Exception:
        return os.path.exists(_caminho_marcador())


def ver_tupla(v):
    try:
        return tuple(int(x) for x in str(v).strip().split("."))
    except Exception:
        return (0,)


def _classe_versao(v):
    """Categoria fixa p/ log pré-assinatura (nunca o cru da rede).

    1.20: `manifest["v"]` é dado externo; antes da assinatura pode ser IP
    ("192.168.1.123" tem formato N.N.N.N), apelido ou canário. IPv4 e
    versão de 4 partes são indistinguíveis, então o log pré-assinatura
    nunca grava o cru — só anterior/igual/superior/invalida. A versão
    real só aparece no diário pós-assinatura (update_recebido), quando é
    do dono e necessária. Não muda protocolo (ver_tupla/decisão intactas).
    """
    try:
        if not isinstance(v, str):
            return "invalida"
        s = v[:16]
        if D.sanear_versao(s) == "invalida":
            return "invalida"
        tv = ver_tupla(s)
        tl = ver_tupla(S.VERSAO)
        if tv < tl:
            return "anterior"
        if tv == tl:
            return "igual"
        return "superior"
    except Exception:
        return "invalida"


def manifest_canonico(manifest):
    return json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def conferir_manifest(manifest, sig_hex):
    try:
        n = int(S.CHAVE_DONO_N, 16)
        sig = bytes.fromhex(sig_hex)
    except Exception:
        return False
    return conferir(manifest_canonico(manifest), sig, n, S.CHAVE_DONO_E)


def caminho_update_origem(nome):
    """De onde sirvo arquivos do update: código em execução, senão pendrive."""
    p1 = os.path.join(S.DIR_CODIGO, nome)
    if os.path.isfile(p1):
        return p1
    return os.path.join(S.PASTA, nome)


def tratar_ver(pid, sock, v):
    if not isinstance(v, str) or not v:
        return
    with S.L:
        S.peer_ver[pid] = v
    if ver_tupla(v) >= ver_tupla(S.VERSAO):
        # peer igual/novo: pendente velha caduca (versão já não justifica).
        cancelar_reoferta(pid, forcar=True)
        if ver_tupla(v) > ver_tupla(S.VERSAO):
            return  # ele é mais novo: ele vai me servir
        return  # igual: nunca oferta
    if ver_tupla(v) < ver_tupla(S.VERSAO):
        with S.L:
            marcado = (pid, v) in S.meta_enviada
            entrega_viva = _META_SOCK.get((pid, v)) in S.sockets_vivos
            if marcado and entrega_viva:
                return  # já entregue nesta conexão viva: sem duplicar
            if marcado:
                # a conexão da entrega morreu (queda/reinício do receptor):
                # desfaz a marca e reoferta já (1 push por handshake).
                S.meta_enviada.discard((pid, v))
                cancelar_reoferta(pid, forcar=True)
            elif agora() - _ULTIMA_TENTATIVA.get(pid, 0.0) \
                    < _COOLDOWN_REOFERTA:
                # ver repetida após falha recente: teto de frequência.
                # Agenda UMA tentativa diferida p/ o fim do intervalo se o
                # peer segue conectado (sem ela, sem novo `ver`, a conexão
                # aberta nunca recebe oferta — só nova conexão salvava).
                _agendar_reoferta(pid, v)
                return
            _ULTIMA_TENTATIVA[pid] = agora()
        log("peer %s na %s, servindo update %s" % (id_curto(pid), D.sanear_versao(v), S.VERSAO))
        D.registrar("update_oferta", peer=D.curto(pid), versao_peer=str(v)[:16])
        threading.Thread(target=empurrar_update, args=(pid, v),
                         daemon=True).start()


def _tem_conexao_viva(pid):
    try:
        return any(c in S.sockets_vivos for c in S.conns.get(pid, ()))
    except Exception:
        return False


def _agendar_reoferta(pid, v):
    """Agenda UMA tentativa diferida p/ o fim do cooldown (1.12).

    Só agenda p/ peer antigo ainda conectado, sem duplicar (1 por peer;
    a tentativa carrega a versão e revalida antes de ofertar). Retorna
    True se agendou ou já havia pendente p/ a mesma versão."""
    with S.L:
        if (pid, v) in S.meta_enviada \
                and _META_SOCK.get((pid, v)) in S.sockets_vivos:
            return False  # já entregue viva: nada a reagendar
        ent = _REOFERTA_AGENDADA.get(pid)
        if ent is not None:
            try:
                t_old, v_old = ent
            except Exception:
                _REOFERTA_AGENDADA.pop(pid, None)
                ent = None
            else:
                if v_old == v and t_old.is_alive():
                    return True  # já agendada: sem tempestade
                try:
                    t_old.cancel()
                except Exception:
                    pass
                _REOFERTA_AGENDADA.pop(pid, None)
        try:
            espera = _COOLDOWN_REOFERTA - (agora()
                                           - _ULTIMA_TENTATIVA.get(pid, 0.0))
        except Exception:
            espera = _COOLDOWN_REOFERTA
        if espera <= 0:
            espera = 0.05
        if not _tem_conexao_viva(pid):
            return False
        t = threading.Timer(espera + 0.05, _disparar_reoferta,
                            args=(pid, v))
        t.daemon = True
        _REOFERTA_AGENDADA[pid] = (t, v)
    try:
        t.start()
    except Exception:
        with S.L:
            _REOFERTA_AGENDADA.pop(pid, None)
        return False
    return True


def _disparar_reoferta(pid, v):
    """Tentativa diferida: reoferta se peer/socket/versão justificarem."""
    reagendar_para = None
    ofertar = False
    with S.L:
        ent = _REOFERTA_AGENDADA.get(pid)
        if ent is None:
            return  # cancelada no disconnect
        try:
            _t, v_ag = ent
        except Exception:
            _REOFERTA_AGENDADA.pop(pid, None)
            return
        if v_ag != v:
            return  # outra versão assumiu; a velha não dispara
        _REOFERTA_AGENDADA.pop(pid, None)
        cur = S.peer_ver.get(pid)
        if cur != v:
            # versão mudou na espera: se a atual ainda é velha e sem
            # entrega viva, reagenda p/ ela fora do lock; senão aborta.
            if isinstance(cur, str) and cur \
                    and ver_tupla(cur) < ver_tupla(S.VERSAO) \
                    and not ((pid, cur) in S.meta_enviada
                             and _META_SOCK.get((pid, cur))
                             in S.sockets_vivos):
                reagendar_para = cur
            else:
                return
        elif (pid, v) in S.meta_enviada \
                and _META_SOCK.get((pid, v)) in S.sockets_vivos:
            return  # outra via entregou na espera: sem duplicar
        elif (pid, v) in S.meta_enviada:
            # entrega morreu na espera: desfaz a marca e oferta já
            # (teto já vencido pelo agendamento).
            S.meta_enviada.discard((pid, v))
            ofertar = True
            _ULTIMA_TENTATIVA[pid] = agora()
        elif agora() - _ULTIMA_TENTATIVA.get(pid, 0.0) \
                < _COOLDOWN_REOFERTA:
            # ver concorrente ofertou na espera: reagenda o resto.
            reagendar_para = v
        else:
            _ULTIMA_TENTATIVA[pid] = agora()
            ofertar = True
        if (ofertar or reagendar_para is not None) \
                and not _tem_conexao_viva(pid):
            # peer caiu antes da tentativa: nada enviado, sem erro.
            return
        if ofertar:
            v_oferta = v
    if reagendar_para is not None:
        _agendar_reoferta(pid, reagendar_para)
        return
    if ofertar:
        log("peer %s na %s, servindo update %s (diferida)"
            % (id_curto(pid), D.sanear_versao(v_oferta), S.VERSAO))
        D.registrar("update_oferta", peer=D.curto(pid),
                    versao_peer=str(v_oferta)[:16], diferida=True)
        threading.Thread(target=empurrar_update, args=(pid, v_oferta),
                         daemon=True).start()


def cancelar_reoferta(pid, sock=None, forcar=False):
    """Cancela a tentativa diferida (1.12).

    No disconnect (tcp.ler_loop/finally, forcar=False), só cancela se o
    peer ficou sem conexão viva — com outro socket vivo do mesmo peer,
    mantém (múltiplos sockets). Com forcar=True (peer anunciou versão
    igual/nova, ou reoferta imediata supersede a pendente), cancela
    mesmo com conexão viva. Idempotente."""
    if not pid:
        return
    with S.L:
        if not forcar:
            try:
                viva = _tem_conexao_viva(pid)
            except Exception:
                viva = False
            if viva:
                return
        ent = _REOFERTA_AGENDADA.pop(pid, None)
    if ent is not None:
        try:
            t = ent[0] if isinstance(ent, tuple) else ent
            t.cancel()
        except Exception:
            pass


def ler_manifest_local():
    for cand in (os.path.join(S.DIR_CODIGO, "update-manifest.json"),
                 os.path.join(S.PASTA, "update-manifest.json")):
        try:
            with open(cand, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict) and isinstance(d.get("manifest"), dict):
                return d
        except Exception:
            continue
    return None


def empurrar_update(pid, v):
    d = ler_manifest_local()
    if not d:
        return
    with S.L:
        cs = list(S.conns.get(pid, ()))
    if not cs:
        return  # sem conexão: a próxima ver tenta de novo (sem marcar)
    try:
        enviar(cs[0], {"t": "update_meta", "manifest": d["manifest"], "sig": d["sig"]})
    except Exception as e:
        # falha antes de confirmar: sem marcar. Além da próxima ver, uma
        # tentativa diferida cobre a MESMA conexão sem novo anúncio (1.12):
        # só agenda com o peer ainda conectado (senão nada, sem erro).
        log("falha ao ofertar update p/ %s (%r): nova tentativa na próxima "
            "ver" % (id_curto(pid), e))
        D.registrar("update_oferta_falha", peer=D.curto(pid),
                    motivo=type(e).__name__)
        try:
            _agendar_reoferta(pid, v)
        except Exception:
            pass
        return
    with S.L:
        S.meta_enviada.add((pid, v))
        for antiga in [k for k in _META_SOCK
                       if k[0] == pid and k != (pid, v)]:
            _META_SOCK.pop(antiga, None)
        _META_SOCK[(pid, v)] = cs[0]


def receber_update_meta(q):
    """Aceita oferta de update assinada (uma transação por vez).

    Política (A+B): a 1ª oferta válida vence; ofertas simultâneas
    posteriores — versão igual ou diferente — são rejeitadas sem mudar o
    estado (sem ordenação garantida, só unicidade). Com recuperação
    pendente (.upd-pendente.json no disco), recusa até o próximo boot
    recuperar o estado velho coerente. Tudo sob S.L (checagem+aceite
    atômicos); a verificação (rápida) roda dentro do lock de propósito.
    """
    if not isinstance(q, dict):
        return
    manifest = q.get("manifest")
    sig = q.get("sig")
    if not isinstance(manifest, dict) or not isinstance(sig, str):
        return
    if ver_tupla(manifest.get("v")) <= ver_tupla(S.VERSAO):
        return  # sem downgrade / mesma versão
    with S.L:
        if S.atualizando:
            cat = _classe_versao(manifest.get("v"))
            log("update (%s) ignorado: já atualizando" % cat)
            D.registrar("update_ignorado", motivo=cat)
            return
        if _ha_recuperacao_pendente():
            cat = _classe_versao(manifest.get("v"))
            log("update (%s) recusado: recuperação pendente em %s "
                "(reinicie para recuperar antes de nova tentativa)"
                % (cat, _caminho_marcador()))
            D.registrar("update_recusado", motivo=cat)
            return
        if not conferir_manifest(manifest, sig):
            log("update com assinatura inválida (ignorado)")
            D.registrar("update_sig_invalida")
            return
        arqs = manifest.get("arquivos")
        if not isinstance(arqs, list) or not arqs:
            return
        for a in arqs:
            if not isinstance(a, dict) or not nome_update_ok(a.get("nome", "")):
                log("update com nome inválido (ignorado)")
                D.registrar("update_nome_invalido")
                return
        log("update v%s recebido, baixando %d arquivos..."
            % (manifest.get("v"), len(arqs)))
        D.registrar("update_recebido", versao=str(manifest.get("v"))[:16],
                    n_arquivos=len(arqs))
        S.update_manifest = manifest
        # Guarda o envelope assinado: sem ele o peer atualizado não consegue
        # provar nem retransmitir a release (finalizar_update o persiste).
        S.update_envelope = {"manifest": manifest, "sig": sig}
        S.atualizando = True
        S.update_montando.clear()
    from .update import baixar_update as _baixar  # adiado: update importa este módulo
    threading.Thread(target=_baixar, daemon=True).start()


def nome_update_ok(nome):
    if not isinstance(nome, str) or not nome or len(nome) > 120:
        return False
    if nome.startswith("/") or "\\" in nome or "\r" in nome or "\n" in nome:
        return False
    partes = nome.split("/")
    if not partes or any(p in ("", ".", "..") for p in partes):
        return False
    return True


def servir_update(pid, sock, q):
    try:
        nome = str(q.get("nome", ""))
        idx = int(q.get("idx", -1))
    except Exception:
        return
    if not nome_update_ok(nome):
        return
    # Só serve o conjunto atual: arquivos que saíram dele (ex. README/docs
    # de releases antigas) ficam no disco de quem tem, mas não viajam mais
    # — e o update nunca os apaga (ver finalizar_update).
    if not any(nome == a for a in S.ARQUIVOS_UPDATE):
        return
    if os.environ.get("SENDERME_DEBUG"):
        log("update_get %s#%d de %s" % (nome, idx, id_curto(pid)))
    p = caminho_update_origem(nome)
    try:
        with open(p, "rb") as f:
            dados = f.read()
    except Exception:
        return
    total = (len(dados) + CHUNK_ARQ - 1) // CHUNK_ARQ or 1
    if idx < 0 or idx >= total:
        return
    try:
        enviar(sock, {"t": "update_chunk", "nome": nome, "idx": idx,
                      "total": total,
                      "dados": base64.b64encode(dados[idx * CHUNK_ARQ:(idx + 1) * CHUNK_ARQ]).decode()})
    except Exception:
        pass


def receber_update_chunk(q):
    try:
        nome = str(q["nome"])
        idx = int(q["idx"])
        total = int(q["total"])
        dados = base64.b64decode(q["dados"])
    except Exception:
        return
    with S.L:
        if not S.atualizando or not isinstance(S.update_manifest, dict):
            return
        esperado = None
        for a in S.update_manifest.get("arquivos", []):
            if isinstance(a, dict) and a.get("nome") == nome:
                esperado = a
                break
        if not esperado:
            return
        try:
            tot_esp = (int(esperado["tamanho"]) + CHUNK_ARQ - 1) // CHUNK_ARQ or 1
        except Exception:
            return
        if total != tot_esp or idx < 0 or idx >= total or len(dados) > CHUNK_ARQ + 1024:
            return
        slot = S.update_montando.setdefault(nome, {"total": total, "partes": {}, "ts": agora()})
        if slot["total"] != total:
            return
        slot["partes"][idx] = dados
        slot["ts"] = agora()
