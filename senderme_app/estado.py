#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SenderMe — estado compartilhado: dono único das variáveis mutáveis.

Regras (ver AGENTS.md):
- Todos os módulos acessam via `from . import estado as S` e usam `S.<nome>`.
  Nunca `from .estado import <variavel-mutavel>`: rebind quebraria o alias.
- Mutação in-place de listas/sets quando outro módulo pode guardar referência
  (ex.: `historico[:] = ...`, nunca `historico = ...` fora daqui).
- Ordem de locks: S.L -> S._disco -> lock de socket. Nunca inverter.
"""
import os
import socket
import threading
import time

from .meta import VERSAO, CHAVE_DONO_E, CHAVE_DONO_N, ARQUIVOS_UPDATE

L = threading.RLock()
_log_lck = threading.Lock()

PASTA = os.environ.get("SENDERME_HOME") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(PASTA, "dados")
DIR_ARQ = os.path.join(DADOS, "arquivos")
DIR_CODIGO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ident = {}
nick = ""
logado = False
conhecidos = {}
nick_de = {}
nick_ts = {}
nick_dono = {}
calados = set()
vistos = set()
historico = []
conns = {}
sockets_vivos = set()
peers = {}
pendentes = {}
pedidos_pub = {}
ultimo_contato = {}
visto_presenca = {}
estado = {}
ultima_leave = {}
ultima_join_eu = 0.0
ultima_leave_eu = 0.0
ultima_ajuste_eu = 0.0
rodando = True
montando = {}
pedidos_arq = {}
sementes = set()
peer_ver = {}
meta_enviada = set()
update_montando = {}
update_manifest = None
update_envelope = None
atualizando = False
dm_retry = {}
ciclo_manut = 0

_disco = threading.Lock()
envios_lck = {}
ultimo_dial = {}
tinha_conexao = False


def agora():
    return time.time()


def log(txt):
    with _log_lck:
        print("[senderme] %s" % txt, flush=True)


def id_curto(idp):
    return (idp or "?")[:8]


def ip_local():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()
