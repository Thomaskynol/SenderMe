#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SenderMe v2 — chat P2P na rede local com interface de navegador.

- Sem servidor central: cada participante propaga mensagens (gossip).
- Python 3 puro, só biblioteca padrão.
- Rede P2P: TCP 13337 (conversa) + UDP 13338 (descoberta).
- Interface web local: HTTP 127.0.0.1:13336 (só nesta máquina).
- Arquivos até 20 MB (global + DM), teto 60 MB + retenção 24 h.
"""
import base64
import hashlib
import json
import mimetypes
import os
import secrets
import socket
import struct
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# ============================================================== constantes
PORTA_TCP = int(os.environ.get("SENDERME_PORTA", "13337"))
PORTA_UDP = int(os.environ.get("SENDERME_UDP_PORTA", "13338"))
PORTA_HTTP = int(os.environ.get("SENDERME_HTTP", "13336"))
FIXOS = [s.strip() for s in os.environ.get("SENDERME_FIXOS", "").split(",") if s.strip()]

RETENCAO = 24 * 3600
TIMEOUT_OFFLINE = 12
JANELA_ENTRADA = 90
JANELA_SAIDA = 60
INTERVALO_ANUNCIO = 3
INTERVALO_PURGA = 600
TIMEOUT_DIAL = 10
MAX_QUADRO = 8 * 1024 * 1024
MAX_TEXTO = 2000
MAX_SYNC = 1000
MAX_PENDENTES = 500
JANELA_HELLO = 60
MAX_ARQUIVO = 20 * 1024 * 1024      # 20 MB por arquivo
MAX_ARQUIVOS_TOTAL = 60 * 1024 * 1024  # 60 MB acumulados
CHUNK_ARQ = 512 * 1024              # 512 KB por chunk P2P
TIPOS_EVENTO = ("msg", "join", "leave", "nick", "dm", "file")
MAX_MIDS_INV = 5000                 # mids no inventário de sync
INTERVALO_PING = 5                  # s entre pings nas conexões
TIMEOUT_SOCK = 15                # s: recv e send nunca travam para sempre

VERSAO = os.environ.get("SENDERME_VERSAO", "1.2")
CHAVE_DONO_E = 65537
CHAVE_DONO_N = ("cfe2bc67e5d2ab9dd4532099ed1fa5fff0884a7fe8ba6c21447ddef5c943cb8f2bd03be95a159"
                "ae31b54d00fc7ab1e47465f3b998bcecec4cc0ecf9a7267045782347015e7eda1b890a6ac98a0a1f597d39"
                "432a526dcea33306efeff75805630bbabd28017d2d91826bf76583ced13c6a1146413820440ebfd03684b"
                "8a091ae74396eaf77c87e6be4486cc92eadb792d2f1e7c32530f2e5b278f9769c8831c4e941854aa9a50d8"
                "97004e32506baccd7efd0360bdb8f3a1bb6e7ba81e56d451e277adee2e7fc2945604305d0f1278b871998f"
                "0234faa11e5d8632234a2a15a212d445bbd3ae18d1ab79a9e31c39768e606fdb09290d04ba9a9f72950ee6"
                "c8927d")
ARQUIVOS_UPDATE = ["senderme.py", "bootstrap.min.css", "start.sh", "README.md",
                   "docs/01-produto.md", "docs/02-arquitetura.md", "docs/03-progresso.md"]

# ================================================================ estado
L = threading.RLock()
_log_lck = threading.Lock()

PASTA = os.environ.get("SENDERME_HOME") or os.path.dirname(os.path.abspath(__file__))
DADOS = os.path.join(PASTA, "dados")
DIR_ARQ = os.path.join(DADOS, "arquivos")
DIR_CODIGO = os.path.dirname(os.path.abspath(__file__))  # de onde estou rodando (/tmp em prod)

ident = {}
nick = ""
logado = False
conhecidos = {}
nick_de = {}
nick_ts = {}                     # id -> ts do último nick aplicado (fix bug nome)
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
montando = {}                    # mid -> {"total":int,"partes":{idx:bytes},"ts":float}
pedidos_arq = {}                 # mid -> ts do último file_req
sementes = set()                 # (ip,porta) aprendidos via peer exchange
peer_ver = {}                    # id -> versão anunciada
meta_enviada = set()             # (id, versão) que já receberam update_meta
update_montando = {}             # nome -> {"total":int,"partes":{},"ts":float}
update_manifest = None           # manifest em aplicação (verificado)
atualizando = False              # True durante aplicação de update
dm_retry = {}                    # id -> ts da última redelivery de DM
ciclo_manut = 0


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


# ========================================================== criptografia
_PEQUENOS = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53,
             59, 61, 67, 71, 73, 79, 83, 89, 97, 101, 103, 107, 109, 113)
_SHA256_DER = bytes.fromhex("3031300d060960864801650304020105000420")


def _miller_rabin(n, rodadas=24):
    if n < 2:
        return False
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(rodadas):
        a = secrets.randbelow(n - 3) + 2
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _primo(bits):
    while True:
        p = secrets.randbits(bits) | (1 << (bits - 1)) | (1 << (bits - 2)) | 1
        if any(p % q == 0 for q in _PEQUENOS):
            continue
        if _miller_rabin(p):
            return p


def _inv(a, m):
    g, x, old_g, old_x = m, 0, a, 1
    while g:
        q = old_g // g
        old_g, g = g, old_g - q * g
        old_x, x = x, old_x - q * x
    if old_g != 1:
        raise ValueError("não invertível")
    return old_x % m


def fingerprint(n, e):
    nb = n.to_bytes((n.bit_length() + 7) // 8, "big")
    eb = e.to_bytes(max(1, (e.bit_length() + 7) // 8), "big")
    return hashlib.sha256(nb + eb).hexdigest()[:40]


def gerar_chave():
    log("Gerando chave RSA-2048 (primeira execução, alguns segundos)...")
    while True:
        p, q = _primo(1024), _primo(1024)
        if p == q:
            continue
        n = p * q
        try:
            d = _inv(65537, (p - 1) * (q - 1))
        except ValueError:
            continue
        if p < q:
            p, q = q, p
        return {"n": n, "e": 65537, "d": d}


def assinar(dados, chave):
    k = (chave["n"].bit_length() + 7) // 8
    t = _SHA256_DER + hashlib.sha256(dados).digest()
    ps = b"\xff" * (k - 3 - len(t))
    em = b"\x00\x01" + ps + b"\x00" + t
    s = pow(int.from_bytes(em, "big"), chave["d"], chave["n"])
    return s.to_bytes(k, "big")


def conferir(dados, assinatura, n, e):
    k = (n.bit_length() + 7) // 8
    if len(assinatura) != k:
        return False
    s = int.from_bytes(assinatura, "big")
    if s >= n or s < 0:
        return False
    t = _SHA256_DER + hashlib.sha256(dados).digest()
    esperado = b"\x00\x01" + b"\xff" * (k - 3 - len(t)) + b"\x00" + t
    try:
        obtido = pow(s, e, n).to_bytes(k, "big")
    except (ValueError, OverflowError):
        return False
    return secrets.compare_digest(obtido, esperado)


# ======================================================== armazenamento
_disco = threading.Lock()


def _caminho(nome):
    return os.path.join(DADOS, nome)


def garantir_dados():
    try:
        os.makedirs(DADOS, exist_ok=True)
        os.makedirs(DIR_ARQ, exist_ok=True)
    except OSError:
        pass


def ler_json(nome, padrao):
    try:
        with open(_caminho(nome), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return padrao


def salvar_json(nome, obj):
    garantir_dados()
    with _disco:
        try:
            tmp = _caminho(nome) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False)
            os.replace(tmp, _caminho(nome))
        except Exception:
            pass


def anexar_historico(ev):
    garantir_dados()
    with _disco:
        try:
            with open(_caminho("historico.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        except Exception:
            pass


def anexar_lote(evs):
    """Grava vários eventos com uma única abertura de arquivo (sync em lote)."""
    if not evs:
        return
    garantir_dados()
    with _disco:
        try:
            with open(_caminho("historico.jsonl"), "a", encoding="utf-8") as f:
                f.write("".join(json.dumps(ev, ensure_ascii=False) + "\n"
                                for ev in evs))
        except Exception:
            pass


def reescrever_historico():
    garantir_dados()
    with _disco:
        try:
            tmp = _caminho("historico.jsonl") + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                for ev in historico:
                    f.write(json.dumps(ev, ensure_ascii=False) + "\n")
            os.replace(tmp, _caminho("historico.jsonl"))
        except Exception:
            pass


def salvar_conhecidos():
    saida = {}
    for idp, d in conhecidos.items():
        saida[idp] = {"n": format(d["n"], "x"), "e": d["e"], "nick": d.get("nick", "")}
    salvar_json("conhecidos.json", saida)


def salvar_calados():
    salvar_json("calados.json", sorted(calados))


def carregar_identidade():
    bruto = ler_json("identidade.json", None)
    if isinstance(bruto, dict) and bruto.get("n"):
        n, e = int(bruto["n"], 16), int(bruto["e"])
        d = int(bruto["d"], 16)
        idp = fingerprint(n, e)
        if bruto.get("id") and bruto["id"] != idp:
            raise SystemExit("identidade.json corrompido (id não confere).")
        return {"n": n, "e": e, "d": d, "id": idp}
    chave = gerar_chave()
    idp = fingerprint(chave["n"], chave["e"])
    salvar_json("identidade.json", {
        "n": format(chave["n"], "x"), "e": chave["e"],
        "d": format(chave["d"], "x"), "id": idp,
    })
    try:
        os.chmod(_caminho("identidade.json"), 0o600)
    except OSError:
        pass
    return {"n": chave["n"], "e": chave["e"], "d": chave["d"], "id": idp}


def carregar_conhecidos():
    bruto = ler_json("conhecidos.json", {})
    for idp, d in (bruto or {}).items():
        try:
            conhecidos[idp] = {"n": int(d["n"], 16), "e": int(d["e"]),
                               "nick": d.get("nick", "")}
            if d.get("nick"):
                aplicar_nick(idp, d["nick"], ts=0)
        except Exception:
            continue


def carregar_historico():
    bruto = []
    try:
        with open(_caminho("historico.jsonl"), encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    ev = json.loads(linha)
                except Exception:
                    continue
                if isinstance(ev, dict):
                    bruto.append(ev)
    except FileNotFoundError:
        return []
    limite = agora() - RETENCAO
    bruto = [e for e in bruto if e.get("ts", 0) >= limite]
    bruto.sort(key=lambda e: (e.get("ts", 0), e.get("mid", "")))
    return bruto


# ------------------------------------------------- arquivos em disco
def caminho_bin(mid):
    return os.path.join(DIR_ARQ, mid + ".bin")


def tem_arquivo(mid):
    try:
        return os.path.isfile(caminho_bin(mid))
    except Exception:
        return False


def salvar_bytes_arquivo(mid, dados):
    garantir_dados()
    with _disco:
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
        for nome in os.listdir(DIR_ARQ):
            if nome.endswith(".bin"):
                try:
                    tot += os.path.getsize(os.path.join(DIR_ARQ, nome))
                except OSError:
                    pass
    except FileNotFoundError:
        pass
    return tot


def evento_por_mid(mid):
    with L:
        for ev in historico:
            if ev.get("mid") == mid:
                return dict(ev)
    return None


def purgar_arquivos():
    """Aplica 24h + teto 60MB. Remove conteúdo, mantém metadados do evento."""
    garantir_dados()
    limite = agora() - RETENCAO
    with L:
        ts_por_mid = {e.get("mid"): e.get("ts", 0) for e in historico
                      if e.get("tipo") == "file" and e.get("mid")}
    try:
        nomes = [n for n in os.listdir(DIR_ARQ) if n.endswith(".bin")]
    except FileNotFoundError:
        return
    # 1) remove por idade
    for nome in nomes:
        mid = nome[:-4]
        ts = ts_por_mid.get(mid)
        if ts is None:
            # sem evento correspondente: usa mtime
            try:
                mt = os.path.getmtime(os.path.join(DIR_ARQ, nome))
                if mt < limite:
                    os.remove(os.path.join(DIR_ARQ, nome))
            except OSError:
                pass
        elif ts < limite:
            try:
                os.remove(os.path.join(DIR_ARQ, nome))
            except OSError:
                pass
    # 2) remove mais antigos até caber em 60MB
    def info():
        out = []
        for nome in os.listdir(DIR_ARQ):
            if not nome.endswith(".bin"):
                continue
            mid = nome[:-4]
            p = os.path.join(DIR_ARQ, nome)
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


# ============================================================= eventos
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
    ev = {"tipo": tipo, "de": ident["id"], "nick": nick,
          "ts": int(agora()), "txt": txt, "nonce": secrets.token_hex(8)}
    if para:
        ev["para"] = para
    campo = campo_assinatura(ev).encode("utf-8")
    ev["sig"] = assinar(campo, ident).hex()
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
    ev = {"tipo": "file", "de": ident["id"], "nick": nick,
          "ts": int(agora()), "txt": caption or "", "nonce": secrets.token_hex(8),
          "arq": {"nome": nome, "tamanho": int(tamanho), "sha256": sha256}}
    if para:
        ev["para"] = para
    campo = campo_assinatura(ev).encode("utf-8")
    ev["sig"] = assinar(campo, ident).hex()
    ev["mid"] = hashlib.sha256(campo).hexdigest()
    return ev


def conferir_evento(ev):
    if ev["de"] == ident.get("id"):
        pub = {"n": ident["n"], "e": ident["e"]}
    else:
        pub = conhecidos.get(ev["de"])
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


# ------------------------------------------------------- tabela de apelidos (com fix)
def aplicar_nick(idp, novo, antigo=None, ts=0):
    """Atualiza nick com last-write-wins por ts (fix: msg velha não reverte)."""
    novo = (novo or "").strip()
    if not novo or len(novo) > 24:
        return
    try:
        ts = int(ts or 0)
    except Exception:
        ts = 0
    if ts < nick_ts.get(idp, 0):
        return  # evento velho: ignora
    nick_ts[idp] = ts
    if antigo:
        k = antigo.strip().lower()
        if nick_dono.get(k) == idp:
            del nick_dono[k]
    nick_de[idp] = novo
    k = novo.lower()
    dono = nick_dono.get(k)
    if dono is None or dono == idp:
        nick_dono[k] = idp
    else:
        # posse transfere se o dono sumiu (zerou e voltou com o mesmo nome);
        # com dois online, o dono atual mantém e o outro exibe (2).
        try:
            dono_online = presente(dono)
        except Exception:
            dono_online = False
        if not dono_online:
            nick_dono[k] = idp
            if os.environ.get("SENDERME_DEBUG"):
                log("nick %r: posse %s -> %s" % (novo, id_curto(dono), id_curto(idp)))
        elif os.environ.get("SENDERME_DEBUG"):
            log("nick %r: mantido %s (online)" % (novo, id_curto(dono)))
    d = conhecidos.get(idp)
    if d is not None:
        d["nick"] = novo


def dono_do_apelido(nome):
    return nick_dono.get((nome or "").strip().lower())


def apelido_exibido(idp, nome):
    dono = nick_dono.get((nome or "").strip().lower())
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
    if idp == ident.get("id"):
        return nick
    return nick_de.get(idp, id_curto(idp))


def silenciado(idp):
    return idp in calados


def em_uso_online(nome, exceto=None):
    alvo = (nome or "").strip().lower()
    if not alvo:
        return None
    with L:
        for idp in list(visto_presenca) + [ident.get("id")]:
            if idp == exceto:
                continue
            if not presente(idp):
                continue
            if apelido_de(idp).strip().lower() == alvo:
                return idp
    return None


def presente(idp):
    if idp == ident.get("id"):
        return True
    if any(c in sockets_vivos for c in conns.get(idp, ())):
        return True
    if estado.get(idp) == "offline":
        return False  # saída anunciada: sem fantasma de 12 s
    return agora() - ultimo_contato.get(idp, 0) <= TIMEOUT_OFFLINE


def autor_silenciado(ev):
    if ev.get("tipo") == "leave":
        return silenciado(ev.get("txt", ""))
    return silenciado(ev.get("de", ""))


# ------------------------------------------------- processamento
def tem_conexao_minha():
    return bool(sockets_vivos)


def pode_exibir_saida(alvo):
    if alvo == ident.get("id"):
        return True
    est = estado.get(alvo)
    if est == "online":
        return True
    if est is None and alvo in visto_presenca:
        return True
    return False


def guardar_pendente(ev, origem):
    lista = pendentes.setdefault(ev["de"], [])
    if len(lista) < MAX_PENDENTES:
        lista.append((ev, origem))
    pedir_pub(ev["de"], origem)


def pedir_pub(idp, origem=None):
    t = agora()
    if t - pedidos_pub.get(idp, 0) < 60:
        return
    pedidos_pub[idp] = t
    msg = {"t": "pub_req", "id": idp}
    alvos = []
    if origem is not None:
        alvos = [c for c in conns.get(origem, ())]
    if not alvos:
        with L:
            for cs in conns.values():
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
    if idp == ident.get("id"):
        return None  # nunca registra a própria chave (auto-dial via seeds)
    if fingerprint(n, e) != idp:
        return None
    novo = False
    with L:
        d = conhecidos.get(idp)
        if d is None:
            conhecidos[idp] = {"n": n, "e": e, "nick": ""}
            novo = True
        elif d["n"] != n:
            return None
        lista = pendentes.pop(idp, [])
    if novo:
        salvar_conhecidos()
    if lista:
        for ev, origem in lista:
            processar(ev, origem=origem)
    return idp


def pedir_arquivo(mid, origem=None):
    t = agora()
    if t - pedidos_arq.get(mid, 0) < 30:
        return
    if tem_arquivo(mid):
        return
    pedidos_arq[mid] = t
    msg = {"t": "file_req", "mid": mid}
    alvos = []
    with L:
        if origem is not None:
            alvos = [c for c in conns.get(origem, ())]
        if not alvos:
            for cs in conns.values():
                alvos.extend(cs)
    for c in alvos[:4]:
        try:
            enviar(c, msg)
        except Exception:
            pass


def processar(ev, origem=None, gravar=True, disco=True):
    """disco=False adia a escrita (o chamador persiste o lote depois)."""
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

    with L:
        if ev["mid"] in vistos:
            return False
        if ev["ts"] < agora() - RETENCAO:
            vistos.add(ev["mid"])
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
    if ev.get("para") and ev["para"] != ident.get("id") and ev["de"] != ident.get("id"):
        return False

    corrigir = False
    with L:
        if ev["mid"] in vistos:
            return False
        vistos.add(ev["mid"])
        ts = int(ev.get("ts", 0))
        if tipo == "nick":
            aplicar_nick(ev["de"], ev["txt"], antigo=ev["nick"], ts=ts)
        else:
            aplicar_nick(ev["de"], ev["nick"], ts=ts)

        if tipo == "leave":
            alvo = ev["txt"]
            if alvo == ident.get("id") and tem_conexao_minha():
                if agora() - ultima_ajuste_eu > 30:
                    corrigir = True
            elif pode_exibir_saida(alvo):
                estado[alvo] = "offline"
        elif tipo == "join":
            if estado.get(ev["de"]) != "online":
                estado[ev["de"]] = "online"
                threading.Thread(target=tentar_entregar_dm, args=(ev["de"],), daemon=True).start()

        if gravar:
            historico.append(ev)
            if disco:
                anexar_historico(ev)

    # arquivo global: pede conteúdo se não tenho
    if tipo == "file" and not ev.get("para"):
        if not tem_arquivo(ev["mid"]):
            pedir_arquivo(ev["mid"], origem)
    if tipo != "dm" and not ev.get("para"):
        propagar(ev, origem)
    if corrigir:
        threading.Thread(target=anunciar_entrada, daemon=True).start()
    return True


def publicar(ev):
    processar(ev, origem=None, gravar=True)


def propagar(ev, origem=None):
    with L:
        alvos = [(idp, list(cs)) for idp, cs in conns.items() if idp != origem]
    for idp, cs in alvos:
        for c in cs:
            try:
                enviar(c, {"t": "ev", "ev": ev})
                break
            except Exception:
                fechar_socket(c, idp)


# =============================================================== TCP
envios_lck = {}


def enviar(sock, obj):
    b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    if len(b) > MAX_QUADRO:
        raise ValueError("quadro grande demais")
    with L:
        lck = envios_lck.get(sock)
        if lck is None:
            lck = threading.Lock()
            envios_lck[sock] = lck
    with lck:
        sock.sendall(struct.pack("!I", len(b)) + b)


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
    with L:
        sockets_vivos.discard(s)
        envios_lck.pop(s, None)
        if pid:
            cs = conns.get(pid)
            if cs is not None:
                cs.discard(s)
                if not cs:
                    conns.pop(pid, None)
    try:
        s.close()
    except Exception:
        pass


def msg_pub():
    return {"t": "pub", "id": ident["id"], "n": format(ident["n"], "x"),
            "e": ident["e"]}


def registrar_conexao(pid, sock, addr, dialado=None):
    with L:
        cs = conns.setdefault(pid, set())
        cs.add(sock)
        sockets_vivos.add(sock)
        cheia = len(cs) > 2
        p = peers.setdefault(pid, {})
        p.setdefault("ip", addr[0])
        if dialado:
            p["ip"], p["porta"] = dialado[0], dialado[1]
        visto_presenca[pid] = True
        ultimo_contato[pid] = agora()
    if cheia:
        fechar_socket(sock, pid)
        return False
    return True


def ler_loop(sock, addr, dialado=None):
    pid = None
    try:
        while rodando:
            try:
                q = ler_quadro(sock)
            except socket.timeout:
                continue  # ocioso: mantém a conexão, tenta de novo
            if not isinstance(q, dict):
                continue
            if pid is None:
                if q.get("t") != "pub":
                    raise ConnectionError("handshake inválido")
                novo = receber_pub(q)
                if not novo:
                    raise ConnectionError("chave inválida")
                if not registrar_conexao(novo, sock, addr, dialado):
                    return
                pid = novo
                try:
                    enviar(sock, {"t": "ver", "v": VERSAO})
                    enviar(sock, {"t": "peers_req"})
                    with L:
                        meus = [e.get("mid") for e in historico[-MAX_MIDS_INV:]
                                if e.get("mid")]
                    enviar(sock, {"t": "hist_req", "tem": meus})
                except Exception:
                    pass
                threading.Thread(target=tentar_entregar_dm, args=(pid,), daemon=True).start()
                continue
            ultimo_contato[pid] = agora()
            tratar_quadro(q, pid, sock)
    except Exception:
        pass
    finally:
        fechar_socket(sock, pid)


def tratar_quadro(q, pid, sock):
    t = q.get("t")
    if t == "ev":
        processar(q.get("ev"), origem=pid)
    elif t == "hist_req":
        tem = q.get("tem")
        with L:
            if isinstance(tem, list) and tem:
                falta = set(x for x in tem if isinstance(x, str))
                evs = [e for e in historico
                       if not e.get("para") and e.get("mid") not in falta][-MAX_SYNC:]
            else:
                evs = [e for e in historico if not e.get("para")][-MAX_SYNC:]
            pubs = []
            vistos_autores = set()
            for e in evs:
                a = e.get("de")
                if a in vistos_autores:
                    continue
                vistos_autores.add(a)
                d = conhecidos.get(a)
                if d:
                    pubs.append({"id": a, "n": format(d["n"], "x"), "e": d["e"]})
        try:
            enviar(sock, {"t": "hist", "evs": evs, "pubs": pubs})
        except Exception:
            pass
    elif t == "hist":
        tratar_hist(q.get("evs"), q.get("pubs"), pid)
    elif t == "pub_req":
        alvo = q.get("id")
        with L:
            d = conhecidos.get(alvo)
        if d:
            try:
                enviar(sock, {"t": "pub", "id": alvo, "n": format(d["n"], "x"), "e": d["e"]})
            except Exception:
                pass
    elif t == "pub":
        receber_pub(q)
    elif t == "file_req":
        mid = q.get("mid")
        if isinstance(mid, str) and len(mid) == 64:
            threading.Thread(target=servir_arquivo, args=(pid, mid), daemon=True).start()
    elif t == "file_chunk":
        receber_chunk(q)
    elif t == "ping":
        try:
            enviar(sock, {"t": "pong"})
        except Exception:
            pass
    elif t == "pong":
        pass  # ler_loop já atualizou ultimo_contato
    elif t == "peers_req":
        with L:
            pares = []
            for p in list(peers.values()) + [{"ip": ip, "porta": int(ps)}
                                             for (ip, ps) in list(sementes)][:40]:
                ip, porta = p.get("ip"), p.get("porta")
                if ip and porta:
                    try:
                        pares.append([ip, int(porta)])
                    except Exception:
                        pass
                if len(pares) >= 20:
                    break
        try:
            enviar(sock, {"t": "peers", "pares": pares})
        except Exception:
            pass
    elif t == "peers":
        for item in (q.get("pares") or [])[:20]:
            try:
                ip, porta = str(item[0]), int(item[1])
            except Exception:
                continue
            if not ip or not porta or porta < 1 or porta > 65535:
                continue
            with L:
                sementes.add((ip, porta))
    elif t == "ver":
        tratar_ver(pid, sock, q.get("v"))
    elif t == "update_meta":
        receber_update_meta(q)
    elif t == "update_get":
        servir_update(pid, sock, q)
    elif t == "update_chunk":
        receber_update_chunk(q)


def servir_arquivo(pid, mid):
    dados = ler_bytes_arquivo(mid)
    if dados is None:
        return
    total = (len(dados) + CHUNK_ARQ - 1) // CHUNK_ARQ or 1
    with L:
        cs = list(conns.get(pid, ()))
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
    with L:
        slot = montando.setdefault(mid, {"total": total, "partes": {}, "ts": agora()})
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
        with L:
            montando.pop(mid, None)
        return
    if hashlib.sha256(blob).hexdigest() != esperado:
        with L:
            montando.pop(mid, None)
        return
    if salvar_bytes_arquivo(mid, blob):
        purgar_arquivos()
    with L:
        montando.pop(mid, None)


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
    anexar_lote(novos)  # um open/write para o lote inteiro
    # puxa conteúdo dos arquivos anunciados que ainda não tenho
    with L:
        faltando = [e["mid"] for e in historico
                    if e.get("tipo") == "file" and not e.get("para")
                    and not tem_arquivo(e.get("mid", ""))]
    for mid in faltando[-20:]:
        pedir_arquivo(mid, pid)


# =========================================================== versões/update
def ver_tupla(v):
    try:
        return tuple(int(x) for x in str(v).strip().split("."))
    except Exception:
        return (0,)


def manifest_canonico(manifest):
    return json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def conferir_manifest(manifest, sig_hex):
    try:
        n = int(CHAVE_DONO_N, 16)
        sig = bytes.fromhex(sig_hex)
    except Exception:
        return False
    return conferir(manifest_canonico(manifest), sig, n, CHAVE_DONO_E)


def caminho_update_origem(nome):
    """De onde sirvo arquivos do update: código em execução, senão pendrive."""
    p1 = os.path.join(DIR_CODIGO, nome)
    if os.path.isfile(p1):
        return p1
    return os.path.join(PASTA, nome)


def tratar_ver(pid, sock, v):
    if not isinstance(v, str) or not v:
        return
    with L:
        peer_ver[pid] = v
    if ver_tupla(v) > ver_tupla(VERSAO):
        return  # ele é mais novo: ele vai me servir
    if ver_tupla(v) < ver_tupla(VERSAO):
        with L:
            if (pid, v) in meta_enviada:
                return
            meta_enviada.add((pid, v))
        log("peer %s na %s, servindo update %s" % (id_curto(pid), v, VERSAO))
        threading.Thread(target=empurrar_update, args=(pid,), daemon=True).start()


def ler_manifest_local():
    for cand in (os.path.join(DIR_CODIGO, "update-manifest.json"),
                 os.path.join(PASTA, "update-manifest.json")):
        try:
            with open(cand, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict) and isinstance(d.get("manifest"), dict):
                return d
        except Exception:
            continue
    return None


def empurrar_update(pid):
    d = ler_manifest_local()
    if not d:
        return
    with L:
        cs = list(conns.get(pid, ()))
    if not cs:
        return
    try:
        enviar(cs[0], {"t": "update_meta", "manifest": d["manifest"], "sig": d["sig"]})
    except Exception:
        pass


def receber_update_meta(q):
    global update_manifest, atualizando
    if atualizando:
        return
    manifest = q.get("manifest")
    sig = q.get("sig")
    if not isinstance(manifest, dict) or not isinstance(sig, str):
        return
    if ver_tupla(manifest.get("v")) <= ver_tupla(VERSAO):
        return  # sem downgrade / mesma versão
    if not conferir_manifest(manifest, sig):
        log("update com assinatura inválida (ignorado)")
        return
    arqs = manifest.get("arquivos")
    if not isinstance(arqs, list) or not arqs:
        return
    for a in arqs:
        if not isinstance(a, dict) or not nome_update_ok(a.get("nome", "")):
            log("update com nome inválido (ignorado)")
            return
    log("update v%s recebido, baixando %d arquivos..." % (manifest.get("v"), len(arqs)))
    with L:
        update_manifest = manifest
        atualizando = True
        update_montando.clear()
    threading.Thread(target=baixar_update, daemon=True).start()


def baixar_update():
    with L:
        manifest = dict(update_manifest or {})
    arqs = manifest.get("arquivos", []) if isinstance(manifest, dict) else []
    for a in arqs:
        try:
            nome = str(a["nome"])
            total = (int(a["tamanho"]) + CHUNK_ARQ - 1) // CHUNK_ARQ or 1
        except Exception:
            continue
        for idx in range(total):
            with L:
                if not atualizando:
                    return
                slot = update_montando.get(nome)
                if slot and idx in slot.get("partes", {}):
                    continue
                alvos = []
                for cs in conns.values():
                    alvos.extend(cs)
            ok = False
            for c in alvos[:4]:
                try:
                    enviar(c, {"t": "update_get", "nome": nome, "idx": idx})
                    ok = True
                    break
                except Exception:
                    pass
            if not ok:
                time.sleep(1.0)
        # espera o arquivo completar (até 60 s por arquivo)
        for _ in range(600):
            with L:
                slot = update_montando.get(nome)
                if slot and len(slot.get("partes", {})) >= slot.get("total", 1):
                    break
            time.sleep(0.1)
        else:
            if os.environ.get("SENDERME_DEBUG"):
                with L:
                    slot = update_montando.get(nome)
                    got = len(slot.get("partes", {})) if slot else 0
                log("update %s incompleto (%s/%s), segue" % (nome, got, total))
    finalizar_update()


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
    if not any(nome == a for a in ARQUIVOS_UPDATE):
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
    with L:
        if not atualizando or not isinstance(update_manifest, dict):
            return
        esperado = None
        for a in update_manifest.get("arquivos", []):
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
        slot = update_montando.setdefault(nome, {"total": total, "partes": {}, "ts": agora()})
        if slot["total"] != total:
            return
        slot["partes"][idx] = dados
        slot["ts"] = agora()


def finalizar_update():
    with L:
        manifest = update_manifest
        mont = {k: dict(v) for k, v in update_montando.items()}
    if not isinstance(manifest, dict):
        with L:
            atualizando = False
        return
    blobs = {}
    for a in manifest.get("arquivos", []):
        try:
            nome = str(a["nome"])
            slot = mont.get(nome)
            total = (int(a["tamanho"]) + CHUNK_ARQ - 1) // CHUNK_ARQ or 1
            if not slot or len(slot.get("partes", {})) < total:
                log("update incompleto (%s), abortado" % nome)
                with L:
                    atualizando = False
                    update_montando.clear()
                return
            blob = b"".join(slot["partes"][i] for i in range(total))
            if len(blob) != int(a["tamanho"]):
                raise ValueError("tamanho")
            if hashlib.sha256(blob).hexdigest() != a["sha256"]:
                raise ValueError("hash")
            blobs[nome] = blob
        except Exception:
            log("update corrompido (%s), abortado" % a)
            with L:
                atualizando = False
                update_montando.clear()
            return
    try:
        for nome, blob in blobs.items():
            if not nome_update_ok(nome):
                raise ValueError("nome")
            dest = os.path.join(PASTA, nome)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            tmp = dest + ".upd-tmp"
            with open(tmp, "wb") as f:
                f.write(blob)
            os.replace(tmp, dest)
    except Exception as e:
        log("falha ao gravar update: %r" % (e,))
        with L:
            atualizando = False
        return
    log("update %s aplicado, reiniciando..." % manifest.get("v"))
    time.sleep(0.5)
    os._exit(42)


# =========================================================== DM para offline
def dms_pendentes_para(para):
    """DMs (texto+arquivo) recentes para este destino, vindas de mim."""
    with L:
        out = [e for e in historico
               if e.get("para") == para and e.get("de") == ident.get("id")
               and e.get("ts", 0) >= agora() - RETENCAO]
    out.sort(key=lambda e: e.get("ts", 0))
    return out[-20:]


def tentar_entregar_dm(pid):
    """Reenvia DMs recentes direto ao destino quando ele volta. Sem gossip."""
    dbg = bool(os.environ.get("SENDERME_DEBUG"))
    if pid == ident.get("id"):
        return
    with L:
        css = [c for c in conns.get(pid, ()) if c in sockets_vivos]
    if not css:
        if dbg:
            log("redelivery %s: sem conn" % id_curto(pid))
        return  # sem conexão: não queima o throttle
    pend = dms_pendentes_para(pid)
    if not pend:
        return  # nada a fazer: também não queima o throttle
    if agora() - dm_retry.get(pid, 0) < 120:
        if dbg:
            log("redelivery %s: throttle" % id_curto(pid))
        return
    dm_retry[pid] = agora()
    if os.environ.get("SENDERME_DEBUG"):
        log("redelivery: %d p/ %s" % (len(pend), id_curto(pid)))
    for sock in css:
        try:
            for ev in pend:
                enviar(sock, {"t": "ev", "ev": ev})
                if ev.get("tipo") == "file":
                    blob = ler_bytes_arquivo(ev.get("mid", ""))
                    if blob is None:
                        continue
                    total = (len(blob) + CHUNK_ARQ - 1) // CHUNK_ARQ or 1
                    for idx in range(total):
                        enviar(sock, {"t": "file_chunk", "mid": ev["mid"], "idx": idx,
                                       "total": total,
                                       "dados": base64.b64encode(blob[idx * CHUNK_ARQ:(idx + 1) * CHUNK_ARQ]).decode()})
            log("DMs pendentes entregues p/ %s (%d)" % (id_curto(pid), len(pend)))
            return
        except Exception as e:
            fechar_socket(sock, pid)
            log("falha redelivery p/ %s: %r" % (id_curto(pid), e))
    return


def dialar(ip, porta, pid=None):
    try:
        s = socket.create_connection((ip, porta), timeout=4)
    except Exception:
        return
    preparar_socket(s)
    with L:
        sockets_vivos.add(s)
    try:
        enviar(s, msg_pub())
    except Exception:
        fechar_socket(s)
        return
    ler_loop(s, (ip, porta), dialado=(ip, porta))


def abrir_servidor():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("", PORTA_TCP))
        s.listen(64)
        return s
    except OSError as e:
        log("Não consegui abrir TCP %d (%s)." % (PORTA_TCP, e))
        return None


def loop_aceitar(s):
    while rodando:
        try:
            c, addr = s.accept()
        except OSError:
            break
        preparar_socket(c)
        with L:
            sockets_vivos.add(c)
        threading.Thread(target=_aceitar, args=(c, addr), daemon=True).start()
    try:
        s.close()
    except Exception:
        pass


def _aceitar(c, addr):
    try:
        enviar(c, msg_pub())
    except Exception:
        fechar_socket(c)
        return
    ler_loop(c, addr)


# =============================================================== UDP
ultimo_dial = {}
tinha_conexao = False


def campo_hello(idp, nome, porta, udp, ts, nonce):
    return "hello|%s|%s|%d|%d|%d|%s" % (idp, nome, porta, udp, ts, nonce)


def montar_hello():
    ts = int(agora())
    nonce = secrets.token_hex(8)
    campo = campo_hello(ident["id"], nick, PORTA_TCP, PORTA_UDP, ts, nonce)
    return {"t": "hello", "id": ident["id"], "n": format(ident["n"], "x"),
            "e": ident["e"], "nick": nick, "porta": PORTA_TCP,
            "udp": PORTA_UDP, "ts": ts, "nonce": nonce,
            "sig": assinar(campo.encode("utf-8"), ident).hex()}


def tratar_hello(dados, addr):
    try:
        m = json.loads(dados.decode("utf-8"))
    except Exception:
        return
    if not isinstance(m, dict) or m.get("t") != "hello":
        return
    try:
        n = int(m["n"], 16)
        e = int(m["e"])
        idp = m["id"]
        nome = str(m["nick"])
        porta = int(m["porta"])
        udp = int(m["udp"])
        ts = int(m["ts"])
        nonce = str(m["nonce"])
        sig = bytes.fromhex(m["sig"])
    except Exception:
        return
    if idp == ident.get("id"):
        return
    if abs(agora() - ts) > JANELA_HELLO:
        return
    if fingerprint(n, e) != idp:
        return
    campo = campo_hello(idp, nome, porta, udp, ts, nonce)
    if not conferir(campo.encode("utf-8"), sig, n, e):
        return
    novo = False
    with L:
        d = conhecidos.get(idp)
        if d is None:
            conhecidos[idp] = {"n": n, "e": e, "nick": nome}
            novo = True
        elif d["n"] != n:
            return
        p = peers.setdefault(idp, {})
        p["ip"], p["porta"], p["udp"] = addr[0], porta, udp
        p["ultimo_hello"] = agora()
        ultimo_contato[idp] = agora()
        visto_presenca[idp] = True
        if nome:
            aplicar_nick(idp, nome, ts=ts)
    if novo:
        salvar_conhecidos()
    threading.Thread(target=tentar_entregar_dm, args=(idp,), daemon=True).start()


def thread_udp():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.bind(("", PORTA_UDP))
    except OSError as e:
        log("UDP %d indisponível (%s)." % (PORTA_UDP, e))
        try:
            s.close()
        except Exception:
            pass
        return
    s.settimeout(1.0)
    ciclo = 0
    proximo = agora()
    while rodando:
        if agora() >= proximo:
            proximo = agora() + INTERVALO_ANUNCIO
            ciclo += 1
            if nick and logado:
                try:
                    b = json.dumps(montar_hello(), ensure_ascii=False).encode("utf-8")
                    s.sendto(b, ("255.255.255.255", PORTA_UDP))
                    if ciclo % 3 == 0:
                        with L:
                            alvos = [(p.get("ip"), p.get("udp")) for p in peers.values()
                                     if p.get("ip") and p.get("udp")]
                        for ip, udp in alvos:
                            try:
                                s.sendto(b, (ip, udp))
                            except Exception:
                                pass
                except Exception:
                    pass
        try:
            dados, addr = s.recvfrom(65535)
        except socket.timeout:
            continue
        except OSError:
            break
        tratar_hello(dados, addr)
    try:
        s.close()
    except Exception:
        pass


# ======================================================== manutenção
def _alvo_eu(ip, porta):
    try:
        if int(porta) != PORTA_TCP:
            return False
    except Exception:
        return False
    try:
        return ip in ("127.0.0.1", "localhost", ip_local())
    except Exception:
        return ip == "127.0.0.1"


def alvos_de_discagem():
    t = agora()
    with L:
        alvos = []
        vistos_chave = set()
        def agendar(ip, porta, pid):
            try:
                porta = int(porta)
            except Exception:
                return
            if not ip or porta < 1 or porta > 65535:
                return
            if _alvo_eu(ip, porta):
                return  # nunca disca para si mesmo
            chave = "%s:%d" % (ip, porta)
            if chave in vistos_chave:
                return
            vistos_chave.add(chave)
            if pid is not None and any(c in sockets_vivos for c in conns.get(pid, ())):
                return
            if t - ultimo_dial.get(chave, 0) < TIMEOUT_DIAL:
                return
            ultimo_dial[chave] = t
            alvos.append((ip, porta, pid))
        for pid, p in list(peers.items()):
            agendar(p.get("ip"), p.get("porta"), pid)
        for fx in FIXOS:
            ip, _, ps = fx.partition(":")
            try:
                porta = int(ps)
            except ValueError:
                continue
            agendar(ip, porta, _id_do_alvo(ip, porta))
        for (ip, porta) in list(sementes):
            agendar(ip, porta, _id_do_alvo(ip, porta))
    return alvos


def _id_do_alvo(ip, porta):
    for idp, p in peers.items():
        if p.get("ip") == ip and p.get("porta") == porta:
            return idp
    return None


def anunciar_entrada():
    global ultima_join_eu
    t = agora()
    with L:
        if not logado or not nick:
            return
        if t - ultima_join_eu < JANELA_ENTRADA and ultima_leave_eu <= ultima_join_eu:
            return
        ultima_join_eu = t
    publicar(criar_evento("join", ""))


def anunciar_saida(pid):
    with L:
        if not pode_exibir_saida(pid):
            return
        if agora() - ultima_leave.get(pid, 0) < JANELA_SAIDA:
            return
        ultima_leave[pid] = agora()
    publicar(criar_evento("leave", pid))


def ausentes():
    t = agora()
    with L:
        alvos = []
        for pid in list(peers):
            if pid == ident.get("id"):
                continue
            ultimo = ultimo_contato.get(pid, 0)
            if ultimo == 0 or t - ultimo <= TIMEOUT_OFFLINE:
                continue
            if any(c in sockets_vivos for c in conns.get(pid, ())):
                continue
            if not pode_exibir_saida(pid):
                continue
            if t - ultima_leave.get(pid, 0) < JANELA_SAIDA:
                continue
            alvos.append(pid)
    return alvos


def manutencao():
    global tinha_conexao, ciclo_manut
    ciclo_manut += 1
    with L:
        ncon = len(sockets_vivos)
        ok = bool(logado and nick)
        # limpa cadáveres: sockets mortos que ficaram em conns
        for pid in list(conns):
            cs = conns[pid]
            vivas = {c for c in cs if c in sockets_vivos}
            if vivas != cs:
                if vivas:
                    conns[pid] = vivas
                else:
                    conns.pop(pid, None)
        for s in list(envios_lck):
            if s not in sockets_vivos:
                envios_lck.pop(s, None)
    if ncon == 0:
        tinha_conexao = False
    elif ok and not tinha_conexao:
        anunciar_entrada()
        tinha_conexao = True
    if ciclo_manut % INTERVALO_PING == 0:
        with L:
            todos = [c for cs in conns.values() for c in cs if c in sockets_vivos]
        for c in todos:
            try:
                enviar(c, {"t": "ping"})
            except Exception:
                pass
    # varredura: puxa até 2 conteúdos de arquivo faltantes por ciclo
    try:
        with L:
            falt = [e["mid"] for e in historico
                    if e.get("tipo") == "file" and not e.get("para")
                    and not tem_arquivo(e.get("mid", ""))][:4]
        for mid in falt[:2]:
            pedir_arquivo(mid)
    except Exception:
        pass
    # varredura: redelivery de DM (cobre qualquer gatilho perdido)
    if ciclo_manut % 10 == 0:
        try:
            with L:
                dests = {e.get("para") for e in historico
                         if e.get("para") and e.get("de") == ident.get("id")
                         and e.get("ts", 0) >= agora() - RETENCAO}
            for d in dests:
                if d != ident.get("id") and presente(d):
                    threading.Thread(target=tentar_entregar_dm, args=(d,), daemon=True).start()
        except Exception:
            pass
    alvos = alvos_de_discagem()
    for alvo in alvos:
        threading.Thread(target=dialar, args=alvo, daemon=True).start()
    for pid in ausentes():
        anunciar_saida(pid)
    t = agora()
    with L:
        for idp in list(pendentes):
            lista = pendentes[idp]
            pendentes[idp] = [x for x in lista if t - x[0].get("ts", 0) < 120]
            if not pendentes[idp]:
                pendentes.pop(idp, None)
        for idp in [k for k, v in pedidos_pub.items() if t - v > 300]:
            pedidos_pub.pop(idp, None)
        for mid in [k for k, v in montando.items() if t - v.get("ts", 0) > 600]:
            montando.pop(mid, None)
        for mid in [k for k, v in pedidos_arq.items() if t - v > 300]:
            pedidos_arq.pop(mid, None)


def thread_manutencao():
    while rodando:
        time.sleep(1.0)
        if not rodando:
            return
        try:
            manutencao()
        except Exception as e:
            log("erro na manutenção: %r" % (e,))


def purgar():
    global historico, vistos
    with L:
        limite = agora() - RETENCAO
        historico = [e for e in historico if e.get("ts", 0) >= limite]
        vistos = {e["mid"] for e in historico if e.get("mid")}
        reescrever_historico()
    try:
        purgar_arquivos()
    except Exception:
        pass


def thread_purga():
    while rodando:
        time.sleep(INTERVALO_PURGA)
        if not rodando:
            return
        try:
            purgar()
        except Exception:
            pass


# =========================================================== comandos (web)
def reconstruir(ev):
    if not isinstance(ev, dict):
        return
    tipo = ev.get("tipo")
    if tipo not in TIPOS_EVENTO:
        return
    if ev.get("mid") in vistos:
        return
    if ev.get("ts", 0) < agora() - RETENCAO:
        return
    if conferir_evento(ev) is not True:
        return
    if ev.get("para") and ev.get("para") != ident.get("id") and ev.get("de") != ident.get("id"):
        return
    with L:
        vistos.add(ev["mid"])
        ts = int(ev.get("ts", 0))
        if tipo == "nick":
            aplicar_nick(ev["de"], ev["txt"], antigo=ev["nick"], ts=ts)
        else:
            aplicar_nick(ev["de"], ev["nick"], ts=ts)
        if tipo == "join":
            estado[ev["de"]] = "online"
        elif tipo == "leave" and ev.get("txt") != ident.get("id"):
            estado[ev["txt"]] = "offline"
        historico.append(ev)


def achar_id(nome):
    alvo = (nome or "").strip().lstrip("@").lower()
    if not alvo:
        return None
    with L:
        candidatos = set(nick_de) | set(conhecidos)
        achados = [i for i in candidatos
                   if i != ident.get("id")
                   and nick_de.get(i, conhecidos.get(i, {}).get("nick", ""))
                   .strip().lower() == alvo]
        for i in achados:
            if presente(i):
                return i
        return achados[0] if achados else None


def lista_presentes():
    with L:
        ids = [ident["id"]]
        for i in set(list(visto_presenca) + list(peers) + list(conns)):
            if i != ident["id"] and presente(i):
                ids.append(i)
        out = []
        for i in ids:
            out.append({"id": i, "nick": apelido_de(i), "curto": id_curto(i),
                        "eu": i == ident["id"]})
    out.sort(key=lambda d: (not d["eu"], d["nick"].lower()))
    return out


def texto_quem():
    lst = lista_presentes()
    linhas = ["Presentes (%d):" % len(lst)]
    for d in lst:
        marca = "você" if d["eu"] else "     "
        linhas.append("  %s %-24s %s" % (marca, d["nick"], d["curto"]))
    return "\n".join(linhas)


def texto_rede():
    linhas = ["Você está em %s (TCP %d / UDP %d / HTTP %d)"
             % (ip_local(), PORTA_TCP, PORTA_UDP, PORTA_HTTP)]
    with L:
        for fx in FIXOS:
            linhas.append("  fixo  %s" % fx)
        for i, cs in conns.items():
            p = peers.get(i, {})
            ip, porta = p.get("ip", "?"), p.get("porta", "?")
            linhas.append("  %s:%s  %s  (%d conexão(ões))" % (ip, porta, id_curto(i), len(cs)))
    return "\n".join(linhas)


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
    global nick, logado
    novo, err = validar_nick(novo)
    if err:
        return False, err
    conflito = em_uso_online(novo, exceto=ident["id"])
    if conflito:
        return False, "O apelido %r já está em uso por %s — escolha outro." % (novo, apelido_de(conflito))
    with L:
        nick = novo
        aplicar_nick(ident["id"], novo, ts=int(agora()))
        logado = True
    try:
        garantir_dados()
        with open(_caminho("apelido.txt"), "w", encoding="utf-8") as f:
            f.write(novo)
    except Exception:
        pass
    threading.Thread(target=anunciar_entrada, daemon=True).start()
    return True, "Você é %s." % novo


def trocar_apelido(novo):
    global nick
    if not logado:
        return False, "Faça login primeiro."
    novo, err = validar_nick(novo)
    if err:
        return False, err
    with L:
        if novo.lower() == nick.lower():
            return False, "Este já é o seu apelido."
    conflito = em_uso_online(novo, exceto=ident["id"])
    if conflito:
        return False, "O apelido %r já está em uso por %s — escolha outro." % (novo, apelido_de(conflito))
    with L:
        antigo = nick
    ev = criar_evento("nick", novo)
    with L:
        nick = novo
        aplicar_nick(ident["id"], novo, antigo=antigo, ts=int(agora()))
    try:
        garantir_dados()
        with open(_caminho("apelido.txt"), "w", encoding="utf-8") as f:
            f.write(novo)
    except Exception:
        pass
    publicar(ev)
    return True, "Agora você é %s." % novo


def toggle_calar(nome):
    nome = (nome or "").strip().lstrip("@")
    if not nome:
        return False, "Uso: /calar @apelido"
    idp = achar_id(nome)
    if not idp:
        return False, "Não encontrei ninguém chamado %r." % nome
    with L:
        if idp in calados:
            calados.discard(idp)
            msg = "%s voltou a aparecer na sua tela." % apelido_de(idp)
        else:
            calados.add(idp)
            msg = "Você não vai ver mais %s (a rede continua guardando)." % apelido_de(idp)
    salvar_calados()
    return True, msg


def enviar_dm_para(alvo_nome, texto):
    partes_nome = (alvo_nome or "").strip()
    if not partes_nome.startswith("@"):
        return False, "Uso: /dm @apelido mensagem"
    alvo = achar_id(partes_nome)
    texto = (texto or "").strip()
    if not alvo:
        return False, "Não encontrei %r." % partes_nome
    if not texto:
        return False, "Mensagem vazia."
    if len(texto) > MAX_TEXTO:
        texto = texto[:MAX_TEXTO]
    with L:
        cs = list(conns.get(alvo, ()))
    ev = criar_evento("dm", texto, para=alvo)
    with L:
        vistos.add(ev["mid"])
        historico.append(ev)
        anexar_historico(ev)
    if not cs:
        return False, "Sem conexão com %s agora (guardada; entrego quando voltar)." % apelido_de(alvo)
    ok = False
    for c in cs:
        try:
            enviar(c, {"t": "ev", "ev": ev})
            ok = True
            break
        except Exception:
            fechar_socket(c, alvo)
    if not ok:
        return False, "Não consegui enviar para %s (guardada; entrego quando voltar)." % apelido_de(alvo)
    return True, ""


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
    with L:
        cs = list(conns.get(alvo, ()))
    if not cs:
        with L:
            vistos.add(ev["mid"])
            historico.append(ev)
            anexar_historico(ev)
        return False, "Sem conexão com %s agora (arquivo salvo local)." % apelido_de(alvo)
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
        for c in list(conns.get(alvo, ())):
            try:
                for idx in range(total):
                    ped = blob[idx * CHUNK_ARQ:(idx + 1) * CHUNK_ARQ]
                    enviar(c, {"t": "file_chunk", "mid": ev["mid"], "idx": idx,
                               "total": total, "dados": base64.b64encode(ped).decode()})
                break
            except Exception:
                fechar_socket(c, alvo)
    with L:
        vistos.add(ev["mid"])
        historico.append(ev)
        anexar_historico(ev)
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


def tratar_comando_web(texto):
    """Retorna (ok, resposta_para_exibir). Mensagem normal retorna (True, '')."""
    if not logado:
        return False, "Faça login primeiro."
    linha = (texto or "").replace("\r\n", "\n")
    if not linha.strip():
        return False, ""
    if not linha.lstrip().startswith("/"):
        msg = linha.strip(" \t")
        # preserva quebras internas, remove linhas vazias nas bordas
        msg = msg.strip("\n")
        if not msg.strip():
            return False, ""
        if len(msg) > MAX_TEXTO:
            msg = msg[:MAX_TEXTO]
        publicar(criar_evento("msg", msg))
        return True, ""
    cmd, _, resto = linha.strip().partition(" ")
    cmd = cmd.lower()
    if cmd == "/ajuda":
        return True, AJUDA_TXT
    if cmd == "/quem":
        return True, texto_quem()
    if cmd == "/rede":
        return True, texto_rede()
    if cmd == "/apelido":
        return trocar_apelido(resto)
    if cmd == "/calar":
        return toggle_calar(resto)
    if cmd == "/dm":
        partes = resto.split(None, 1)
        if len(partes) < 2:
            return False, "Uso: /dm @apelido mensagem"
        return enviar_dm_para(partes[0], partes[1])
    if cmd in ("/sair", "/limpar"):
        return False, "Comando removido na versão navegador. Para sair, Ctrl+C no terminal do servidor."
    return False, "Comando desconhecido %r — digite /ajuda." % cmd


# ------------------------------------------------- formatação p/ web
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
    proprio = (de == ident.get("id"))
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
    with L:
        if not historico:
            return [], lista_presentes()
        if depois_mid:
            ini = None
            for i, e in enumerate(historico):
                if e.get("mid") == depois_mid:
                    ini = i + 1
                    break
            if ini is None:
                janela = historico[-50:]
            else:
                janela = historico[ini:ini + limite]
        else:
            janela = historico[-50:]
        out = []
        for ev in janela:
            if autor_silenciado(ev):
                continue
            d = evento_para_api(ev)
            if d:
                out.append(d)
        presentes = lista_presentes()
    return out, presentes


# =========================================================== HTTP
PAGINA = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SenderMe</title>
<link rel="stylesheet" href="/bootstrap.min.css">
<style>
body{background:#f1f3f5}
#msgs{height:60vh;overflow-y:auto;background:#fff;border:1px solid #dee2e6;border-radius:.5rem;padding:.75rem}
.msg{margin-bottom:.6rem;max-width:85%}
.balao{background:#e9ecef;border-radius:.6rem;padding:.45rem .7rem;white-space:pre-wrap;word-break:break-word}
.eu .balao{background:#d1e7dd}
.dm .balao{border:1px dashed #a370c9}
.sys{color:#6c757d;font-style:italic;font-size:.9rem;white-space:pre-wrap}
.hora{color:#868e96;font-size:.75rem}
textarea{resize:none}
.login-wrap{min-height:100vh;display:flex;align-items:center;justify-content:center}
</style>
</head>
<body>
<div class="container py-3" id="app" style="display:none">
<ul class="nav nav-tabs mb-3">
<li class="nav-item"><button class="nav-link active" id="tab-chat" onclick="mostrar('chat')">Chat</button></li>
<li class="nav-item"><button class="nav-link" id="tab-configs" onclick="mostrar('configs')">Configs</button></li>
<li class="nav-item ms-auto"><span class="navbar-text" id="eu"></span> <span id="status" class="badge bg-success">online</span></li>
</ul>
<div id="upd" class="alert alert-warning" style="display:none"></div>
<div id="pane-chat">
<div class="row">
<div class="col-md-3 mb-3">
<div class="card"><div class="card-header">Presentes (<span id="npres">0</span>)</div>
<ul class="list-group list-group-flush" id="presentes"></ul></div>
</div>
<div class="col-md-9">
<div id="msgs"></div>
<div id="sys" class="sys mt-2"></div>
<form id="form" class="mt-2">
<textarea id="texto" class="form-control mb-2" rows="3" placeholder="Mensagem (Enter envia, Shift+Enter quebra linha). /ajuda lista comandos."></textarea>
<div class="d-flex gap-2">
<input type="file" id="arq" class="form-control" style="max-width:60%">
<input type="text" id="para" class="form-control" placeholder="@alvo (DM opcional)" style="max-width:25%">
<button class="btn btn-primary" type="submit">Enviar</button>
</div>
<div class="form-text">Arquivos até 20 MB, qualquer tipo. 60 MB acumulados + 24 h, depois apaga os mais antigos.</div>
</form>
</div>
</div>
</div>
<div id="pane-configs" style="display:none">
<div class="card mb-3"><div class="card-body">
<h5>Apelido</h5>
<div class="d-flex gap-2"><input id="novonick" class="form-control" maxlength="24"><button class="btn btn-secondary" onclick="trocarNick()">Trocar</button></div>
<div class="form-text">Histórico mantém o nome da época.</div>
<h5 class="mt-3">Meu ID</h5><code id="meuid"></code>
<h5 class="mt-3">Rede</h5><pre id="rede" style="white-space:pre-wrap"></pre>
<h5 class="mt-3">Silenciados</h5><ul id="calados" class="list-group"></ul>
<h5 class="mt-3">Ajuda</h5><pre id="ajuda" style="white-space:pre-wrap"></pre>
</div></div>
</div>
</div>
<div class="login-wrap" id="login">
<div class="card p-4" style="min-width:320px"><h4>SenderMe</h4>
<p class="text-muted">Escolha seu apelido para entrar.</p>
<div class="d-flex gap-2"><input id="nick" class="form-control" maxlength="24" placeholder="apelido">
<button class="btn btn-primary" onclick="login()">Entrar</button></div>
<div id="loginerr" class="text-danger mt-2"></div>
</div>
</div>
<script>
let lastMid="", ME="", MINHAV="", enviando=false, falhas=0;
function esc(s){return (s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")}
async function api(p,o){
 try{
  let ctl=new AbortController();
  let to=setTimeout(function(){ctl.abort()},15000);
  let opt=o||{}; opt.signal=ctl.signal;
  let r=await fetch(p,opt); clearTimeout(to);
  let t=await r.text(); try{return JSON.parse(t)}catch(e){return {ok:false,msg:t}}
 }catch(e){return {ok:false,msg:"sem conexao com o servidor",rede:false}}
}
function banner(t){let u=document.getElementById("upd");if(!t){u.style.display="none";return}u.textContent=t;u.style.display="block"}
function selo(ok){
 let s=document.getElementById("status");if(!s)return;
 if(ok){falhas=0;s.textContent="online";s.className="badge bg-success"}
 else{falhas++;s.textContent=falhas>2?"servidor fora?":"tentando...";s.className="badge bg-danger"}
}
async function estado(){
 try{
  let e=await api("/api/eu"); selo(e.ok!==false&&e.rede!==false);
  if(e.atualizando){banner("Nova versao recebida, aplicando e reiniciando...")}
  else if(e.versao&&MINHAV&&e.versao!==MINHAV){location.reload();return}
  else{banner(null)}
  if(e.versao)MINHAV=e.versao;
  if(!e.logado){document.getElementById("login").style.display="flex";document.getElementById("app").style.display="none"}
  else{document.getElementById("login").style.display="none";document.getElementById("app").style.display="block";
   ME=e.id;document.getElementById("eu").textContent=e.nick+" ("+e.id.slice(0,8)+") v"+(e.versao||"?");
   document.getElementById("meuid").textContent=e.id;poll();configs()}
 }catch(err){selo(false)}
}
async function login(){
 try{
  let n=document.getElementById("nick").value;
  let r=await api("/api/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({nick:n})});
  if(r.ok){estado()}else{document.getElementById("loginerr").textContent=r.msg||"erro"}
 }catch(err){document.getElementById("loginerr").textContent="falha de rede"}
}
async function trocarNick(){
 try{
  let n=document.getElementById("novonick").value;
  let r=await api("/api/nick",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({nick:n})});
  alert(r.ok?r.msg:(r.msg||"erro"));estado();
 }catch(err){alert("falha de rede")}
}
function mostrar(q){
 document.getElementById("pane-chat").style.display=q=="chat"?"block":"none";
 document.getElementById("pane-configs").style.display=q=="configs"?"block":"none";
 document.getElementById("tab-chat").classList.toggle("active",q=="chat");
 document.getElementById("tab-configs").classList.toggle("active",q=="configs");
 if(q=="configs")configs();
}
function bolha(m){
 let d=document.createElement("div");d.className="msg"+(m.proprio?" eu":"")+(m.dm?" dm":"");
 if(m.tipo=="join"||m.tipo=="leave"||m.tipo=="nick"){d.innerHTML='<div class="sys">'+esc(m.hora)+" "+esc(m.txt)+"</div>";return d}
 let h='<span class="hora">'+esc(m.hora)+"</span> <b>"+esc(m.nick)+"</b>"+(m.dm?' <span class="badge bg-secondary">dm</span>':"");
 h+='<div class="balao">'+esc(m.txt||"");
 if(m.tipo=="file"&&m.arq){
  let kb=(m.arq.tamanho/1024).toFixed(1);
  h+="<br><b>📎 "+esc(m.arq.nome)+" ("+kb+" KB)</b><br>";
  if(m.arq.pronto){h+='<a href="/api/arquivo/'+m.mid+'" target="_blank">baixar</a>';}
  else{h+="<i>baixando/expirado…</i>"}
  let nm=(m.arq.nome||"").toLowerCase();
  if(m.arq.pronto&&(nm.endsWith(".png")||nm.endsWith(".jpg")||nm.endsWith(".jpeg")||nm.endsWith(".gif")||nm.endsWith(".webp"))){
   h+='<br><img src="/api/arquivo/'+m.mid+'" style="max-width:220px;max-height:160px" class="img-thumbnail">';}
 }
 h+="</div>";d.innerHTML=h;return d;
}
function dmPara(n){document.getElementById("para").value="@"+n;document.getElementById("texto").focus()}
async function descalar(n){
 try{await api("/api/calar",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({alvo:n})});configs();poll()}
 catch(err){}
}
async function poll(){
 try{
  let r=await api("/api/mensagens?depois="+encodeURIComponent(lastMid));
  selo(r.eventos!==undefined);
  if(r.eventos){let box=document.getElementById("msgs");
   for(let m of r.eventos){box.appendChild(bolha(m));lastMid=m.mid}
   box.scrollTop=box.scrollHeight;
   let ul=document.getElementById("presentes");ul.innerHTML="";
   document.getElementById("npres").textContent=(r.presentes||[]).length;
   for(let p of (r.presentes||[])){let li=document.createElement("li");li.className="list-group-item d-flex justify-content-between";
    li.innerHTML="<span>"+esc(p.nick)+(p.eu?" (você)":"")+"</span><small class='text-muted'>"+esc(p.curto)+"</small>";
    let b=document.createElement("button");b.className="btn btn-sm btn-outline-secondary ms-2";b.textContent=p.eu?"-":"DM";
    if(!p.eu){b.dataset.n=p.nick;b.onclick=function(){dmPara(this.dataset.n)}}
    li.appendChild(b);ul.appendChild(li);}
  }
 }catch(err){selo(false)}
}
setInterval(function(){if(document.getElementById("app").style.display!=="none")poll()},700);
document.addEventListener("visibilitychange",function(){if(!document.hidden)poll()});
document.getElementById("form").addEventListener("submit",async e=>{
 e.preventDefault();
 if(enviando)return; enviando=true;
 try{
  let f=document.getElementById("arq").files[0];
  let para=document.getElementById("para").value.trim();
  let txt=document.getElementById("texto").value;
  if(f){
   if(f.size>20*1024*1024){sysMsg("Arquivo > 20 MB");return}
   let fd=new FormData();fd.append("file",f);fd.append("texto",txt);fd.append("para",para);
   sysMsg("Enviando arquivo...");
   let r=await fetch("/api/upload",{method:"POST",body:fd});let j=await r.json();
   if(!j.ok){sysMsg("Falha no upload: "+(j.msg||"erro")+" (texto mantido)");return}
   document.getElementById("arq").value="";document.getElementById("texto").value="";sysMsg(null);poll();return;
  }
  let r=await api("/api/enviar",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({texto:txt,para:para})});
  if(r.rede===false){sysMsg("Sem conexao: mensagem mantida, tente de novo");return}
  if(r.resposta){sysMsg(r.resposta)}
  else if(!r.ok){sysMsg("Erro: "+(r.msg||"erro")+" (texto mantido)");return}
  else{sysMsg(null)}
  document.getElementById("texto").value="";poll();
 }catch(err){sysMsg("Falha de rede (texto mantido)")}
 finally{enviando=false}
});
function sysMsg(t){let s=document.getElementById("sys");if(t){s.textContent=t}else{s.textContent=""}}
document.getElementById("texto").addEventListener("keydown",e=>{
 if(e.key=="Enter"&&!e.shiftKey){e.preventDefault();document.getElementById("form").requestSubmit()}
});
async function configs(){
 try{
  let r=await api("/api/rede");document.getElementById("rede").textContent=(r.linhas||[]).join("\\n");
  let a=await api("/api/ajuda");document.getElementById("ajuda").textContent=a.texto||"";
  let c=await api("/api/calados");let ul=document.getElementById("calados");ul.innerHTML="";
  for(let x of (c.lista||[])){let li=document.createElement("li");li.className="list-group-item d-flex justify-content-between";
   li.innerHTML="<span>"+esc(x.nick)+" <small class='text-muted'>"+esc(x.curto)+"</small></span>";
   let b=document.createElement("button");b.className="btn btn-sm btn-outline-primary";b.textContent="descalar";
   b.dataset.n=x.nick;b.onclick=function(){descalar(this.dataset.n)};
   li.appendChild(b);ul.appendChild(li);}
 }catch(err){}
}
estado();
</script>
</body>
</html>
"""


def _json(handler, obj, cod=200):
    b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    handler.send_response(cod)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(b)))
    handler.end_headers()
    handler.wfile.write(b)


def _parse_multipart(body, ctype):
    """Retorna (campos_texto, arquivos). arquivos: nome_campo -> (filename, bytes)."""
    campos, arqs = {}, {}
    if "boundary=" not in ctype:
        return campos, arqs
    bnd = ctype.split("boundary=")[-1].strip().strip('"').encode()
    partes = body.split(b"--" + bnd)
    for p in partes:
        if not p or p in (b"--", b"--\r\n", b"\r\n"):
            continue
        if b"\r\n\r\n" not in p:
            continue
        cab, _, dado = p.partition(b"\r\n\r\n")
        if dado.endswith(b"\r\n"):
            dado = dado[:-2]
        try:
            cab_s = cab.decode("utf-8", "replace")
        except Exception:
            continue
        nome = None
        filename = None
        for linha in cab_s.split("\r\n"):
            ll = linha.lower()
            if "content-disposition" in ll:
                for seg in linha.split(";"):
                    seg = seg.strip()
                    if seg.startswith("name="):
                        nome = seg[5:].strip().strip('"')
                    if seg.startswith("filename="):
                        filename = seg[9:].strip().strip('"')
                        filename = os.path.basename(filename)
        if not nome:
            continue
        if filename:
            arqs[nome] = (filename, dado)
        else:
            try:
                campos[nome] = dado.decode("utf-8", "replace")
            except Exception:
                campos[nome] = ""
    return campos, arqs


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _corpo(self, limite=26 * 1024 * 1024):
        try:
            n = int(self.headers.get("Content-Length", "0") or 0)
        except Exception:
            n = 0
        if n <= 0:
            return b""
        if n > limite:
            return None
        try:
            return self.rfile.read(n)
        except Exception:
            return b""

    def do_GET(self):
        u = urlparse(self.path)
        p = u.path
        try:
            if p in ("/", "/index.html"):
                b = PAGINA.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)
                return
            if p == "/bootstrap.min.css":
                for cand in (os.path.join(os.path.dirname(os.path.abspath(__file__)), "bootstrap.min.css"),
                             os.path.join(PASTA, "bootstrap.min.css")):
                    if os.path.isfile(cand):
                        with open(cand, "rb") as f:
                            b = f.read()
                        self.send_response(200)
                        self.send_header("Content-Type", "text/css")
                        self.send_header("Content-Length", str(len(b)))
                        self.end_headers()
                        self.wfile.write(b)
                        return
                self.send_response(404)
                self.end_headers()
                return
            if p == "/api/eu":
                with L:
                    _json(self, {"id": ident.get("id", ""), "nick": nick,
                                 "logado": logado, "precisa_login": not logado,
                                 "versao": VERSAO, "atualizando": atualizando,
                                 "ciclo": ciclo_manut, "nconns": len(sockets_vivos)})
                return
            if p == "/api/mensagens":
                qs = parse_qs(u.query)
                depois = (qs.get("depois") or [""])[0]
                evs, pres = mensagens_para_api(depois)
                _json(self, {"eventos": evs, "presentes": pres})
                return
            if p == "/api/rede":
                _json(self, {"linhas": texto_rede().split("\n")})
                return
            if p == "/api/ajuda":
                _json(self, {"texto": AJUDA_TXT})
                return
            if p == "/api/calados":
                with L:
                    lst = [{"id": i, "nick": apelido_de(i), "curto": id_curto(i)} for i in calados]
                _json(self, {"lista": lst})
                return
            if p.startswith("/api/arquivo/"):
                mid = p.rsplit("/", 1)[-1]
                if len(mid) != 64 or any(c not in "0123456789abcdef" for c in mid):
                    self.send_response(400)
                    self.end_headers()
                    return
                ev = evento_por_mid(mid)
                if not ev or ev.get("tipo") != "file":
                    self.send_response(404)
                    self.end_headers()
                    return
                blob = ler_bytes_arquivo(mid)
                if blob is None:
                    self.send_response(404)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.end_headers()
                    self.wfile.write("arquivo expirado ou ainda baixando".encode())
                    return
                nome = (ev.get("arq") or {}).get("nome", "arquivo")
                mime, _ = mimetypes.guess_type(nome)
                self.send_response(200)
                self.send_header("Content-Type", mime or "application/octet-stream")
                self.send_header("Content-Length", str(len(blob)))
                self.send_header("Content-Disposition", "attachment; filename=%s" % json.dumps(nome))
                self.end_headers()
                self.wfile.write(blob)
                return
            self.send_response(404)
            self.end_headers()
            return
        except BrokenPipeError:
            return
        except Exception as e:
            try:
                _json(self, {"ok": False, "msg": str(e)}, 500)
            except Exception:
                pass

    def do_POST(self):
        u = urlparse(self.path)
        p = u.path
        try:
            if p == "/api/login":
                b = self._corpo()
                try:
                    d = json.loads((b or b"{}").decode("utf-8"))
                except Exception:
                    d = {}
                novo = (d.get("nick") or "").strip()
                with L:
                    ja = logado
                    atual = nick
                if ja and novo.lower() == atual.lower():
                    _json(self, {"ok": True, "msg": "Você é %s." % atual})
                    return
                if ja:
                    ok, msg = trocar_apelido(novo)
                else:
                    ok, msg = fazer_login(novo)
                _json(self, {"ok": ok, "msg": msg}, 200 if ok else 400)
                return
            if p == "/api/nick":
                b = self._corpo()
                try:
                    d = json.loads((b or b"{}").decode("utf-8"))
                except Exception:
                    d = {}
                ok, msg = trocar_apelido(d.get("nick", ""))
                _json(self, {"ok": ok, "msg": msg}, 200 if ok else 400)
                return
            if p == "/api/enviar":
                b = self._corpo()
                try:
                    d = json.loads((b or b"{}").decode("utf-8"))
                except Exception:
                    d = {}
                texto = d.get("texto", "")
                para = (d.get("para") or "").strip()
                # DM via campo separado: transforma em /dm
                if para and not texto.lstrip().startswith("/"):
                    ok, resp = enviar_dm_para(para, texto)
                    _json(self, {"ok": ok, "msg": resp, "resposta": resp})
                    return
                ok, resp = tratar_comando_web(texto)
                _json(self, {"ok": ok, "msg": resp, "resposta": resp})
                return
            if p == "/api/calar":
                b = self._corpo()
                try:
                    d = json.loads((b or b"{}").decode("utf-8"))
                except Exception:
                    d = {}
                ok, msg = toggle_calar(d.get("alvo", ""))
                _json(self, {"ok": ok, "msg": msg}, 200 if ok else 400)
                return
            if p == "/api/upload":
                ctype = self.headers.get("Content-Type", "")
                b = self._corpo(limite=26 * 1024 * 1024)
                if b is None:
                    _json(self, {"ok": False, "msg": "Arquivo grande demais (máx. 20 MB)."}, 413)
                    return
                campos, arqs = _parse_multipart(b, ctype)
                if "file" not in arqs:
                    _json(self, {"ok": False, "msg": "Nenhum arquivo enviado."}, 400)
                    return
                filename, blob = arqs["file"]
                if len(blob) > MAX_ARQUIVO:
                    _json(self, {"ok": False, "msg": "Arquivo grande demais (máx. 20 MB)."}, 413)
                    return
                if len(blob) == 0:
                    _json(self, {"ok": False, "msg": "Arquivo vazio."}, 400)
                    return
                caption = campos.get("texto", "")
                para = (campos.get("para") or "").strip()
                if para:
                    ok, msg = enviar_dm_arquivo(para, caption, filename or "arquivo", blob)
                else:
                    ok, msg = publicar_arquivo_global(caption, filename or "arquivo", blob)
                _json(self, {"ok": ok, "msg": msg}, 200 if ok else 400)
                return
        except BrokenPipeError:
            return
        except Exception as e:
            try:
                _json(self, {"ok": False, "msg": str(e)}, 500)
            except Exception:
                pass


def thread_http():
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORTA_HTTP), Handler)
    except OSError as e:
        log("Não consegui abrir HTTP 127.0.0.1:%d (%s)." % (PORTA_HTTP, e))
        return
    log("Web em http://127.0.0.1:%d" % PORTA_HTTP)
    srv.daemon_threads = True
    while rodando:
        try:
            srv.handle_request()
        except Exception:
            pass


# =============================================================== main
def main():
    global nick, logado
    garantir_dados()
    ident.update(carregar_identidade())
    log("seu id: %s" % ident["id"])
    carregar_conhecidos()
    with L:
        calados.update(x for x in ler_json("calados.json", []) if isinstance(x, str))
    for ev in carregar_historico():
        reconstruir(ev)
    with L:
        if historico:
            log("histórico local: %d eventos das últimas 24h" % len(historico))
    # login persistente: apelido.txt
    salvo = ""
    try:
        with open(_caminho("apelido.txt"), encoding="utf-8") as f:
            salvo = f.read().strip()[:24]
    except Exception:
        salvo = ""
    if salvo:
        with L:
            nick = salvo
            aplicar_nick(ident["id"], nick, ts=int(agora()))
            logado = True
        log("logado como %s (apelido salvo)" % nick)
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
        while rodando:
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    desligar()


def desligar():
    global rodando
    if not rodando:
        return
    rodando = False
    try:
        if logado and nick:
            ev = criar_evento("leave", ident["id"])
            publicar(ev)
            time.sleep(0.6)
    except Exception:
        pass
    for c in list(sockets_vivos):
        fechar_socket(c)
    log("Até logo!")
    os._exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        desligar()
