"""Apoio aos testes de caracterização (Lane C).

Isola o estado global de `senderme` por teste e usa `SENDERME_HOME` temporário.
Chaves RSA de teste em ~512 bits: mesmo código `assinar/conferir`, sem o custo
do RSA-2048 real (shortcut: 1 teste com chave real seria lento; documentado).
"""
import hashlib
import json
import struct
import tempfile
import unittest

import senderme as sm

_DICTS = ["conhecidos", "nick_de", "nick_ts", "nick_dono", "peers",
          "pendentes", "pedidos_pub", "ultimo_contato", "visto_presenca",
          "estado", "ultima_leave", "montando", "pedidos_arq", "peer_ver",
          "dm_retry", "update_montando", "envios_lck", "ultimo_dial"]
_SETS = ["vistos", "calados", "sockets_vivos", "sementes", "meta_enviada"]
_SIMPLES = ["nick", "logado", "atualizando", "ciclo_manut", "ultima_join_eu",
            "ultima_leave_eu", "ultima_ajuste_eu", "tinha_conexao",
            "update_manifest", "update_envelope"]


def chave_teste(bits=512):
    """Par RSA rápido só para exercício do código (não é identidade real)."""
    while True:
        p, q = sm._primo(bits // 2), sm._primo(bits // 2)
        if p == q:
            continue
        try:
            d = sm._inv(65537, (p - 1) * (q - 1))
        except ValueError:
            continue
        return {"n": p * q, "e": 65537, "d": d}


def identidade_de(chave):
    return {"n": chave["n"], "e": chave["e"], "d": chave["d"],
            "id": sm.fingerprint(chave["n"], chave["e"])}


def guardar():
    g = {"_ident": dict(sm.ident), "_historico": list(sm.historico),
         "_PASTA": sm.PASTA, "_DADOS": sm.DADOS, "_DIR_ARQ": sm.DIR_ARQ,
         "_conns": {k: set(v) for k, v in sm.conns.items()}}
    for nome in _DICTS:
        g[nome] = dict(getattr(sm, nome))
    for nome in _SETS:
        g[nome] = set(getattr(sm, nome))
    for nome in _SIMPLES:
        g[nome] = getattr(sm, nome)
    return g


def restaurar(g):
    sm.ident.clear()
    sm.ident.update(g["_ident"])
    sm.historico[:] = g["_historico"]
    for nome in _DICTS:
        getattr(sm, nome).clear()
        getattr(sm, nome).update(g[nome])
    for nome in _SETS:
        getattr(sm, nome).clear()
        getattr(sm, nome).update(g[nome])
    sm.conns.clear()
    sm.conns.update({k: set(v) for k, v in g["_conns"].items()})
    for nome in _SIMPLES:
        setattr(sm, nome, g[nome])
    sm.PASTA, sm.DADOS, sm.DIR_ARQ = g["_PASTA"], g["_DADOS"], g["_DIR_ARQ"]


def isolar(tmp):
    dados = __import__("os").path.join(tmp, "dados")
    sm.PASTA, sm.DADOS = tmp, dados
    sm.DIR_ARQ = __import__("os").path.join(dados, "arquivos")
    sm.historico[:] = []
    for nome in _DICTS:
        getattr(sm, nome).clear()
    for nome in _SETS:
        getattr(sm, nome).clear()
    sm.conns.clear()
    sm.ident.clear()
    sm.nick, sm.logado = "", False
    sm.atualizando, sm.ciclo_manut = False, 0
    sm.update_envelope = None
    sm.ultima_join_eu = sm.ultima_leave_eu = sm.ultima_ajuste_eu = 0.0
    sm.tinha_conexao = False
    sm.update_manifest = None


class CasoIsolado(unittest.TestCase):
    def setUp(self):
        self._g = guardar()
        self._tmp = tempfile.TemporaryDirectory()
        isolar(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()
        restaurar(self._g)


def definir_eu(nick="alice", chave=None):
    chave = chave or chave_teste()
    idt = identidade_de(chave)
    sm.ident.clear()
    sm.ident.update(idt)
    sm.nick = nick
    return idt, chave


def definir_par(nick="bob", presente=False):
    """Cria par com chave própria e registra em conhecidos; opcionalmente online."""
    chave = chave_teste()
    idt = identidade_de(chave)
    sm.conhecidos[idt["id"]] = {"n": chave["n"], "e": chave["e"], "nick": nick}
    sm.nick_de[idt["id"]] = nick
    if presente:
        sm.visto_presenca[idt["id"]] = True
        sm.ultimo_contato[idt["id"]] = sm.agora()
    return idt, chave


def criar_como(idt, nick_nome, tipo, txt, para=None, arq=None):
    """Assina um evento como outro par (troca ident/nick, restaura depois)."""
    velho_id, velho_nick = dict(sm.ident), sm.nick
    try:
        sm.ident.clear()
        sm.ident.update(idt)
        sm.nick = nick_nome
        if arq is None:
            return sm.criar_evento(tipo, txt, para=para)
        return sm.criar_evento_file(txt, arq["nome"], arq["tamanho"],
                                    arq["sha256"], para=para)
    finally:
        sm.ident.clear()
        sm.ident.update(velho_id)
        sm.nick = velho_nick


def reassinar(ev, chave):
    campo = sm.campo_assinatura(ev).encode("utf-8")
    ev["sig"] = sm.assinar(campo, chave).hex()
    ev["mid"] = hashlib.sha256(campo).hexdigest()
    return ev


class FakeSock:
    def __init__(self):
        self.buf = bytearray()

    def sendall(self, b):
        self.buf.extend(bytes(b))

    def close(self):
        pass


def quadros(sock):
    out, buf, i = [], bytes(sock.buf), 0
    while i + 4 <= len(buf):
        (n,) = struct.unpack("!I", buf[i:i + 4])
        out.append(json.loads(buf[i + 4:i + 4 + n].decode("utf-8")))
        i += 4 + n
    return out
