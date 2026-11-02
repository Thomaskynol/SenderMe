#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SenderMe — diário persistente (logs em arquivo, só stdlib).

Folha sem dependências do resto do app (só `meta`): `estado` é lido de
forma adiada para não criar ciclo de importação.

Contrato:
- Habilitado por padrão; `SENDERME_SEM_LOG=1` desliga (terminal continua).
- Destino: `<SENDERME_HOME>/logs/senderme.log` (pasta da INSTALAÇÃO —
  nunca o /tmp copiado pelo start.sh, que aponta SENDERME_HOME p/ o disco).
- Rotativo: principal + 5 backups (`senderme.log` + `.1`..`.5`, 6 arquivos,
  ~6 MiB no total).
- Uma linha JSON por evento, só com campos seguros (allowlist
  CAMPOS_PERMITIDOS + validação por campo): nunca texto de
  mensagens/DMs, apelidos, nomes/conteúdo de arquivos, IPs completos, ids
  permanentes, chaves, identidade, histórico, caminhos pessoais,
  queries/corpos HTTP, dados arbitrários da rede (versões e demais valores
  externos são validados; o que não passa vira rótulo fixo ou é
  descartado), nem `str(exc)`/payloads — só rótulos fixos, contadores e
  nomes de tipos de exceção.
- Peers aparecem como rótulo temporário por execução (`peer-1`, `peer-2`
  …): correlaciona dentro de um run, sem derivar do id permanente nem
  ligar identidade entre execuções.
- Falha de log NUNCA derruba o chat: retorna False + 1 aviso no terminal.
  Como o `logging` engole exceções de write/flush/rotação, o handler
  próprio (`_ArquivoSeguro`) captura a falha e `registrar()` a reporta.
- Exceção inesperada em thread: `instalar_hook_threads()` (chamado no
  boot) registra `thread_falha` só com tipo da exceção + nome sanitizado
  da thread; o traceback completo vai só p/ o terminal. Não cobre o que
  mata o processo (os._exit, SIGKILL, segfault) nem a thread principal
  (ver sys.excepthook) — limite documentado, não afirmado.
- Thread-safe (`logging` + lock na configuração). Multiprocesso no mesmo
  arquivo NÃO é garantido (rotação sob 2 escritores pode intercalar);
  cada linha carrega `run` (id da execução) p/ separar. Na prática 2
  instâncias no mesmo SENDERME_HOME nem sobem (portas em conflito).
"""
import json
import logging
import os
import re
import sys
import threading
import time
import uuid
from logging.handlers import RotatingFileHandler

from .meta import VERSAO

MAX_BYTES = 1024 * 1024  # ~1 MiB por arquivo
BACKUPS = 5              # senderme.log + .1 .. .5 (~6 MiB no total)
NOME_ARQ = "senderme.log"

RUN_ID = uuid.uuid4().hex[:12]

# Chaves que NUNCA vão p/ o arquivo (mesmo que um hook as passe por engano).
SENSIVEIS = frozenset({
    "texto", "txt", "msg", "mensagem", "dm", "ev", "evento_txt",
    "nick", "apelido", "nome", "arquivo", "anexo", "conteudo", "dados",
    "ip", "addr", "endereco", "id", "de", "para", "origem", "destino",
    "sig", "n", "e", "d", "chave", "token", "segredo", "identidade",
    "historico", "query", "corpo", "caminho", "path", "pasta", "motivo_txt",
})

# Allowlist de campos da linha JSON (item 3b): blacklist de nomes NÃO
# basta — dado da rede pode chegar em qualquer campo "inocente" (ex.
# string arbitrária como versão em `tratar_ver`). Chave fora daqui é
# descartada; cada valor passa por _sanear_campo.
CAMPOS_PERMITIDOS = frozenset({
    "peer", "versao", "versao_peer", "rede", "fase", "motivo", "op",
    "arq", "porta", "bytes", "n", "n_arquivos", "peers_conectados",
    "num", "thread", "i", "grp", "teve", "diferida", "run", "fio",
})

_VERSAO_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){0,2}$")
# 1-3 partes: 4 partes numéricas são indistinguíveis de IPv4
# ("192.168.1.123" passaria como versão) — p/ log, 4 partes = invalida.
# Só afeta exibição/log (sanear_versao); a decisão de protocolo (ver_tupla)
# segue aceitando qualquer formato.
_TIPO_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,63}$")
_ROTULO_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.:/\-]{0,63}$")
_PEER_RE = re.compile(r"^(peer-\d+|\?|nenhum|\*\*\*)$")
_REDE_RE = re.compile(r"^(\d{1,3}\.\d{1,3}\.\d{1,3}\.0/24|\*\*\*)$")
_EVENTO_RE = re.compile(r"^[a-z0-9_]{1,40}$")

_lck = threading.Lock()
_reg_lck = threading.RLock()
_log = None
_dir_atual = None
_params = (None, None)
_aviso_falha = False
_mapa_peer = {}
_prox_peer = 1
_hook_threads_ok = False
_orig_thread_hook = None


class _ArquivoSeguro(RotatingFileHandler):
    """RotatingFileHandler que CAPTURA falha em vez de engolir em silêncio.

    Causa-raiz do item 1: `logging` trata erro de emit (write/flush/
    doRollover) em `handleError`, que por padrão só cospe no stderr —
    `logger.info()` nunca levanta, então `registrar()` retornava True sem
    persistir. Aqui a falha fica em `erro` p/ `registrar()` checar e
    reportar (False + 1 aviso no terminal). Sem o `super()`: nada de
    traceback no stderr; o diagnóstico único sai via `_avisar`.
    """

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.erro = None

    def handleError(self, record):
        try:
            self.erro = sys.exc_info()[1]
        except Exception:
            self.erro = True


def curto(idp):
    """Rótulo temporário do peer p/ o diário (`peer-1`, `peer-2`, …).

    Item 3a: o prefixo do id permanente (`id[:8]`) correlacionava o peer
    entre execuções. Aqui o mapa vive só na memória do run (zerado em
    `encerrar()`); fora do run o rótulo não diz nada.
    """
    global _prox_peer
    try:
        if not isinstance(idp, str) or not idp:
            return "?"
        with _lck:
            lab = _mapa_peer.get(idp)
            if lab is None:
                lab = "peer-%d" % _prox_peer
                _prox_peer += 1
                _mapa_peer[idp] = lab
            return lab
    except Exception:
        return "?"


def sanear_versao(v):
    """Versão externa p/ exibição/log: válida (`N[.N[.N]]`) ou `invalida`.

    Item 3b: string arbitrária da rede nunca passa crua (nem no terminal).
    1.20: 4 partes numéricas viram `invalida` (indistinguíveis de IPv4).
    """

    try:
        if isinstance(v, str) and _VERSAO_RE.match(v[:16]):
            return v[:16]
    except Exception:
        pass
    return "invalida"


def mascarar_ip(ip):
    """IPv4 -> /24 (`a.b.c.0/24`); resto/ausente -> `***` (sem IP completo)."""
    try:
        partes = str(ip).split(".")
        if len(partes) == 4 and all(p.isdigit() and 0 <= int(p) <= 255
                                    for p in partes):
            return "%s.%s.%s.0/24" % (partes[0], partes[1], partes[2])
    except Exception:
        pass
    return "***"


def _dir_logs():
    try:
        from . import estado as S
        base = S.PASTA
    except Exception:
        base = None
    if not base:
        base = os.environ.get("SENDERME_HOME") or os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "logs")


def _avisar(txt):
    global _aviso_falha
    if _aviso_falha:
        return
    _aviso_falha = True
    try:
        print("[senderme] diario: %s" % txt, flush=True)
    except Exception:
        pass


def _sanear_campo(k, v):
    """Devolve (presente, valor) p/ um campo da allowlist. Nunca levanta.

    Versões/valores externos fora do formato viram rótulo fixo
    (`invalida`/`?`/`***`/`erro`) em vez de vazar cru; resto inválido é
    descartado (presente=False).
    """
    try:
        if k in ("versao", "versao_peer"):
            return True, sanear_versao(v) if isinstance(v, str) else "invalida"
        if k == "peer":
            if isinstance(v, str) and _PEER_RE.match(v):
                return True, v
            return True, "?"
        if k == "rede":
            if isinstance(v, str) and _REDE_RE.match(v):
                return True, v
            return True, "***"
        if k == "motivo":
            if isinstance(v, str) and _TIPO_RE.match(v):
                return True, v
            return True, "erro"
        if k in ("fase", "op", "arq", "run", "fio"):
            if isinstance(v, str) and _ROTULO_RE.match(v[:64]):
                return True, v[:64]
            return False, None
        if k in ("teve", "diferida"):
            return True, bool(v)
        if isinstance(v, bool):
            return True, v
        if isinstance(v, int):
            return True, v
        if isinstance(v, float):
            return True, v
        return False, None
    except Exception:
        return False, None


def _filtrar(campos):
    """Só campos da allowlist, com valor validado (nunca levanta)."""
    limpos = {}
    try:
        for k, v in (campos or {}).items():
            try:
                if not isinstance(k, str) or k not in CAMPOS_PERMITIDOS:
                    continue
                ok, val = _sanear_campo(k, v)
                if ok:
                    limpos[k] = val
            except Exception:
                continue
    except Exception:
        pass
    return limpos


def iniciar(max_bytes=MAX_BYTES, backups=BACKUPS):
    """Prepara o arquivo de log. Idempotente; reabre se SENDERME_HOME mudou
    (isolamento de testes). Retorna o caminho ou None (desligado/falha)."""
    global _log, _dir_atual, _params
    if os.environ.get("SENDERME_SEM_LOG"):
        return None
    destino = _dir_logs()
    with _lck:
        if _log is not None and _dir_atual == destino \
                and _params == (max_bytes, backups):
            return os.path.join(destino, NOME_ARQ)
        try:
            os.makedirs(destino, exist_ok=True)
            caminho = os.path.join(destino, NOME_ARQ)
            logger = logging.getLogger("senderme.diario")
            logger.setLevel(logging.INFO)
            logger.propagate = False
            for h in list(logger.handlers):
                try:
                    logger.removeHandler(h)
                    h.close()
                except Exception:
                    pass
            fh = _ArquivoSeguro(caminho, maxBytes=max_bytes,
                                     backupCount=backups, encoding="utf-8")
            fh.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(fh)
            _log, _dir_atual, _params = logger, destino, (max_bytes, backups)
            return caminho
        except Exception as e:
            _avisar("sem log em arquivo (%s); sigo só com terminal"
                    % type(e).__name__)
            return None


def registrar(evento, **campos):
    """Uma linha JSON no diário. Nunca levanta; False = não persistiu.

    Item 1: `logger.info()` nunca levanta mesmo com disco cheio (o
    `logging` engole em `handleError`), então a falha é checada no
    `_ArquivoSeguro` (erro de write/flush/rotação) + `flush()` explícito.
    1.20: limpa/emit/checa sob `_reg_lck` para o retorno refletir a
    PRÓPRIA gravação (sem ele, A-falha → B-sucesso-limpa → A-checa-limpo
    retornava True sem persistir). RLock: reentrada na mesma thread não
    trava; falha nunca derruba o chat.
    """
    try:
        if os.environ.get("SENDERME_SEM_LOG"):
            return False
        logger = _log
        if logger is None:
            if iniciar() is None:
                return False
            logger = _log
            if logger is None:
                return False
        try:
            ev = str(evento)[:40]
        except Exception:
            return False
        if not _EVENTO_RE.match(ev):
            ev = "evento_invalido"
        linha = {"ts": int(time.time()), "run": RUN_ID, "versao": VERSAO,
                 "evento": ev}
        linha.update(_filtrar(campos))
        try:
            texto = json.dumps(linha, ensure_ascii=False)
        except Exception:
            return False
        hs = [h for h in logger.handlers
              if isinstance(h, _ArquivoSeguro)]
        if not hs:
            return False
        with _reg_lck:
            for h in hs:
                h.erro = None
            try:
                logger.info(texto)
            except Exception as e:
                _avisar("falha ao escrever (%s); sigo só com terminal"
                        % type(e).__name__)
                return False
            falhou = None
            for h in hs:
                try:
                    h.flush()
                except Exception as e:
                    if falhou is None:
                        falhou = e
                if falhou is None and h.erro is not None:
                    falhou = h.erro
            if falhou is not None:
                nome = type(falhou).__name__ \
                    if isinstance(falhou, BaseException) else "erro"
                _avisar("falha ao escrever (%s); sigo só com terminal" % nome)
                return False
            return True
    except Exception:
        return False


def _sanear_fio(nome):
    """Nome de thread p/ o diário: só [A-Za-z0-9_.\\-], resto vira `-`.

    O 3.14 nomeia threads como `Thread-1 (boom)`; descartar tudo perderia
    o diagnóstico. Nomes de thread são internos (nunca dado da rede).
    """
    try:
        if not isinstance(nome, str) or not nome:
            return "thread"
        limpo = re.sub(r"[^A-Za-z0-9_.\-]+", "-", nome)
        limpo = limpo.strip("-")[:64].strip("-")
        if not limpo or not _ROTULO_RE.match(limpo):
            return "thread"
        return limpo
    except Exception:
        return "thread"


def instalar_hook_threads():
    """Captura exceção inesperada em thread p/ o diário (item 4).

    Instala `threading.excepthook` seguro e idempotente: registra
    `thread_falha` só com o NOME do tipo da exceção + nome sanitizado da
    thread (sem msg da exceção, payloads ou locals); avisa no terminal e
    preserva o comportamento padrão (traceback no terminal). A thread
    morre normalmente; o chat segue. Nunca levanta.
    Limite documentado (não coberto): o que mata o processo (os._exit,
    SIGKILL, segfault em C) e exceções na thread principal (essas vão p/
    sys.excepthook, não p/ cá).
    """
    global _hook_threads_ok, _orig_thread_hook
    try:
        if _hook_threads_ok:
            return True
        orig = threading.excepthook

        def _gancho(args):
            try:
                try:
                    tipo = args.exc_type.__name__
                except Exception:
                    tipo = "?"
                if not isinstance(tipo, str) or not _TIPO_RE.match(tipo):
                    tipo = "erro"
                try:
                    nome = _sanear_fio(args.thread.name
                                       if args.thread is not None else "?")
                except Exception:
                    nome = "thread"
                try:
                    print("[senderme] thread %s falhou (%s); o chat segue"
                          % (nome, tipo), flush=True)
                except Exception:
                    pass
                try:
                    registrar("thread_falha", fio=nome, motivo=tipo)
                except Exception:
                    pass
                try:
                    if orig is not None:
                        orig(args)
                except Exception:
                    pass
            except Exception:
                pass

        threading.excepthook = _gancho
        _orig_thread_hook = orig
        _hook_threads_ok = True
        return True
    except Exception:
        return False


def caminho_log():
    """Caminho atual do diário ou None (desligado/nunca iniciado)."""
    if _dir_atual is None:
        return None
    return os.path.join(_dir_atual, NOME_ARQ)


def encerrar():
    """Fecha handlers (isolamento de testes). Nunca levanta."""
    global _log, _dir_atual, _params, _mapa_peer, _prox_peer
    with _lck:
        try:
            if _log is not None:
                for h in list(_log.handlers):
                    try:
                        _log.removeHandler(h)
                        h.close()
                    except Exception:
                        pass
        except Exception:
            pass
        _log, _dir_atual, _params = None, None, (None, None)
        _mapa_peer = {}
        _prox_peer = 1
