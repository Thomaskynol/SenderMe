#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SenderMe — http (extraído de senderme.py sem mudar lógica)."""
import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from . import estado as S
from . import diario as D
from .estado import log, id_curto
from .comandos import (fazer_login, trocar_apelido, enviar_dm_para, tratar_comando_web, toggle_calar, enviar_dm_arquivo, publicar_arquivo_global, mensagens_para_api, texto_rede, AJUDA_TXT)
from .presenca import apelido_de
from .arquivos import ler_bytes_arquivo, evento_por_mid
from pagina import PAGINA
from config import PORTA_HTTP, MAX_ARQUIVO


_LOOPBACKS = ("127.0.0.1", "localhost", "::1")


def _npeers():
    """Nº de peers com socket vivo (p/ honestidade da pública)."""
    try:
        with S.L:
            return sum(1 for cs in S.conns.values() if cs)
    except Exception:
        return 0


def _eh_dm_barra(texto):
    """True se `texto` é comando /dm (mesma partição de tratar_comando_web)."""
    try:
        t = (texto or "").lstrip()
        if not t.startswith("/"):
            return False
        cmd, _, _ = t.partition(" ")
        return cmd.lower() == "/dm"
    except Exception:
        return False


def _parse_host_cabecalho(raw):
    """`Host` -> `(host, porta)` ou `None` se inválido. Porta ausente vale 80."""
    if not raw:
        return None
    raw = raw.strip()
    if not raw or "@" in raw or "/" in raw or "\\" in raw or " " in raw:
        return None
    if raw.count(":") > 1 and not raw.startswith("["):
        return None  # IPv6 sem colchetes é inválido em Host
    try:
        u = urlparse("//" + raw)
    except Exception:
        return None
    host = (u.hostname or "").lower()
    if not host:
        return None
    try:
        porta = u.port
    except ValueError:
        return None  # porta inválida/fora de faixa
    return (host, 80 if porta is None else porta)


def _origem_ok(handler):
    """Host/CSRF: POST mutante e leitura (GET/HEAD) fora da origem são 403.

    Origem = esquema+host+porta (Achado D: `::1` NÃO equivale a `127.0.0.1`):
    - `Host` presente tem de ser loopback + porta efetiva do servidor
      (`handler.server.server_address[1]`). Trava DNS-rebinding; curl
      legítimo manda o Host certo por padrão. Ausente: relevado (HTTP/1.0).
    - `Origin`/`Referer`: cada um presente tem de ser `http` (o servidor
      só serve http; `https` é outra origem) + MESMO host do `Host` +
      MESMA porta. Os dois são conferidos de forma independente:
      inconsistência entre eles rejeita. Porta ausente vale 80 (nunca a
      do servidor) → 403. `null` (file://, sandbox), esquema estranho,
      URL malformada, porta inválida e userinfo (`evil.com@127.0.0.1`)
      → 403.
    - Sem `Origin`/`Referer` (curl local, scripts): liberado — o servidor
      só escuta em 127.0.0.1 e cliente local não é navegador.
    - `Host` ausente + sem `Origin`/`Referer`: liberado (cliente local).
    Limite conhecido: sem token/sessão, não autentica o cliente; script
    local (sem Origin) e clique coagido passam de todo jeito. Só impede
    que página de outra origem use o navegador como ponte."""
    try:
        porta_serv = handler.server.server_address[1]
    except Exception:
        return False
    host = None
    cru = handler.headers.get("Host")
    if cru is not None:
        par = _parse_host_cabecalho(cru)
        if par is None:
            return False
        host, porta_host = par
        if host not in _LOOPBACKS or porta_host != porta_serv:
            return False
    origem = handler.headers.get("Origin") or ""
    referer = handler.headers.get("Referer") or ""
    if not origem.strip() and not referer.strip():
        return True
    for valor in (v for v in (origem, referer) if v.strip()):
        try:
            u = urlparse(valor.strip())
            if u.scheme != "http":
                return False
            if "@" in u.netloc or u.username or u.password:
                return False  # userinfo: hostname aparente não é o host real
            oh = (u.hostname or "").lower()
            if oh not in _LOOPBACKS:
                return False
            try:
                po = u.port
            except ValueError:
                return False  # porta inválida/fora de faixa
            if po is None:
                po = 80
            if po != porta_serv:
                return False
            if host is not None and oh != host:
                return False  # alias cruzado (::1 vs 127.0.0.1) é outra origem
        except Exception:
            return False
    return True


def _negar_origem(handler):
    _json(handler, {"ok": False,
                    "msg": "origem externa rejeitada (CSRF)"}, 403)


def _json(handler, obj, cod=200):
    b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    handler.send_response(cod)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(b)))
    handler.end_headers()
    # HEAD nunca leva corpo (Achado 3): mantém status+headers e
    # Content-Length do que o GET retornaria, sem escrever bytes.
    if getattr(handler, "command", "") != "HEAD":
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

    def send_error(self, code, message=None, explain=None):
        # Endurecimento Host (item 4): verbo não implementado com Host/
        # origem externa recebe 403, não 501 (sem oráculo nem vazamento).
        try:
            if not _origem_ok(self):
                try:
                    _negar_origem(self)
                except Exception:
                    pass
                return
        except Exception:
            pass
        super().send_error(code, message, explain)

    def do_HEAD(self):
        try:
            if not _origem_ok(self):
                _negar_origem(self)
                return
            # HEAD não é usado pela interface; preserva 501 sem vazar corpo.
            self.send_error(501)
        except BrokenPipeError:
            return
        except Exception:
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
            if not _origem_ok(self):
                _negar_origem(self)
                return
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
                             os.path.join(S.PASTA, "bootstrap.min.css")):
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
                with S.L:
                    _json(self, {"id": S.ident.get("id", ""), "nick": S.nick,
                                 "logado": S.logado, "precisa_login": not S.logado,
                                 "versao": S.VERSAO, "atualizando": S.atualizando,
                                 "ciclo": S.ciclo_manut, "nconns": len(S.sockets_vivos)})
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
                with S.L:
                    lst = [{"id": i, "nick": apelido_de(i), "curto": id_curto(i)} for i in S.calados]
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
            if not _origem_ok(self):
                _negar_origem(self)
                return
            if p == "/api/login":
                b = self._corpo()
                try:
                    d = json.loads((b or b"{}").decode("utf-8"))
                except Exception:
                    d = {}
                novo = (d.get("nick") or "").strip()
                with S.L:
                    ja = S.logado
                    atual = S.nick
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
                    ok, resp, estado, transmitida = enviar_dm_para(para, texto, com_estado=True)
                    # Item 3: nivel/socket/local + confirmado/peers explicitos;
                    # antigos intactos (compat: novos opcionais, ausentes=legado).
                    # DM: transmitida=true = bytes ao socket (nunca recebimento).
                    _json(self, {"ok": ok, "msg": resp, "resposta": resp,
                                 "estado": estado, "transmitida": transmitida,
                                 "nivel": "socket" if transmitida else "local",
                                 "confirmado": False, "peers": _npeers()})
                    return
                ok, resp, estado, transmitida = tratar_comando_web(texto, com_estado=True)
                # Item 3: só /dm com bytes no socket é nivel socket; o resto
                # (pública/comandos locais) é aceitação local. confirmado nunca.
                _json(self, {"ok": ok, "msg": resp, "resposta": resp,
                             "estado": estado, "transmitida": transmitida,
                             "nivel": "socket" if (_eh_dm_barra(texto) and transmitida) else "local",
                             "confirmado": False, "peers": _npeers()})
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
            self._corpo()  # drena corpo p/ manter keep-alive antes do 404
            _json(self, {"ok": False, "msg": "rota desconhecida"}, 404)
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
        D.registrar("rede_http_falha", porta=PORTA_HTTP, motivo=type(e).__name__)
        return
    log("Web em http://127.0.0.1:%d" % PORTA_HTTP)
    D.registrar("rede_http_ok", porta=PORTA_HTTP)
    srv.daemon_threads = True
    while S.rodando:
        try:
            srv.handle_request()
        except Exception as e:
            D.registrar("http_erro", motivo=type(e).__name__)
