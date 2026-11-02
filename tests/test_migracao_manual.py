"""Migracao manual <=1.2 -> atual com envelope completo + P2P (R4).

Fixture antiga (NAO e' release historica autentica, so simula o layout que
importa para o boot + envelope): `update-manifest.json` do git `24176fa`
(v1.2, assinado oficial) + cada arquivo listado nele (senderme.py, start.sh,
bootstrap.min.css, README, docs/*), todos via `git show 24176fa:<arquivo>`.
`dados/` sintetico: identidade de teste (RSA rapido) + `apelido.txt`; o
`historico.jsonl` e' gerado pelo proprio app antigo via POST /api/enviar
(boot <=1.2 quebra com historico artesanal fora do formato assinado).
Nunca `dados/` real, nunca `dono/privada.json` (so chave publica embutida
para conferir + chave SINTETICA para o envelope P2P, ver abaixo).

Sequencia EXATA reproduzida (espelha docs/04-migracao.md):
 1. montar a instalacao antiga (com seu manifesto 1.2) e dar boot com o
    start.sh ANTIGO; conferir que o manifesto antigo verifica (sig + hashes
    dos 7 arquivos) - prova que a fixture tem envelope coerente;
 2. confirmar /api/eu logado na versao antiga ("1.2") e publicar uma
    mensagem (historico genuino);
 3. fotografar os bytes de dados/ (antes);
 4. PARAR o processo antigo (SIGTERM no grupo + wait - o loop antigo nao
    pode ser reaproveitado: continua copiando so senderme.py+css);
 5. copiar o CONJUNTO COMPLETO da release nova, sem tocar em dados/,
    NESTA ORDEM (lista montada dinamicamente de
    `senderme_app/meta.py:ARQUIVOS_UPDATE` + `update-manifest.json`; nunca
    hardcode - outra lane pode acrescentar arquivos como preboot.py):
    a. todos os ARQUIVOS_UPDATE exceto `start.sh`;
    b. `update-manifest.json` da release nova;
    c. POR ULTIMO `start.sh` NOVO (so depois do runtime estar completo; o
       launcher novo aborta se faltar arquivo);
 6. CONFERIR assinatura (chave publica real embutida) + versao (manifesto
    == codigo) + completude (todo ARQUIVOS_UPDATE presente) + hashes de
    cada arquivo do manifesto contra o disco. Tolerancia a drift: se um
    arquivo difere do manifesto mas e' byte-igual a' fonte (RAIZ), e'
    drift de outra lane (manifesto aguarda re-assinatura oficial) - registra
    e segue; se difere de ambos, e' adulteracao e falha. R4 em vermelho:
    sem o passo 5b o manifesto permanece 1.2 (versao difere do codigo) e o
    hash de senderme.py nao confere com o codigo novo;
 7. executar o novo `start.sh` na mesma copia (mesmos dados/, mesmas portas);
 8. confirmar /api/eu logado, mesmo nick/id, versao nova, historico visivel
    em /api/mensagens, e que identidade/apelido sao byte-iguais;
 9. P2P: o peer migrado atualiza OUTRO peer antigo (segunda fixture 1.2).
    Como o manifesto real esta em drift (outra lane, sem re-assinatura),
    o envelope P2P e' SINTETICO mas coerente com os arquivos reais do
    migrado: mesma versao vigente (meta.VERSAO), hashes calculados do disco do migrado
    (inclui a reescrita minima de meta.py para a chave sintetica), sig
    sintetica; o cliente 1.2 tem seu CHAVE_DONO reescrito para a sintetica
    antes do boot (so na fixture tmp). O cliente verifica sig+hashes,
    aplica, e apos o restart falho conhecido do launcher antigo (exit 0
    mascarado) completa-se com o manifesto sintetico + boot novo,
    conferindo versao vigente, envelope coerente (sig+hashes com a sintetica),
    identidade propria preservada e /api/mensagens funcional. Isso prova
    que o migrado retransmite a release; o envelope real aguarda
    re-assinatura oficial (drift documentado, teste nao re-assina).

Subprocessos bounded (poll com teto + killpg de limpeza); portas livres via
bind; limpeza total com addCleanup (rmtree). Sem pendrive fisico.
"""
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "tests"))
sys.path.insert(0, RAIZ)
from test_dist_boot import porta_livre, identidade_rapida  # noqa: E402

REV_ANTIGA = "24176fa"
VERSAO_ANTIGA = "1.2"
MANIFESTO = "update-manifest.json"
TETO_BOOT = 60
TETO_P2P = 240


def arquivo_git(rev, nome):
    r = subprocess.run(["git", "-C", RAIZ, "show", "%s:%s" % (rev, nome)],
                       capture_output=True, timeout=30)
    if r.returncode != 0:
        return None
    return r.stdout


def foto_dados(dados):
    foto = {}
    for nome in ("identidade.json", "apelido.txt", "historico.jsonl"):
        caminho = os.path.join(dados, nome)
        if os.path.isfile(caminho):
            with open(caminho, "rb") as f:
                foto[nome] = f.read()
    return foto


def esperar_api_eu(http, proc, teto_s=TETO_BOOT):
    base = "http://127.0.0.1:%d" % http
    fim = time.time() + teto_s
    while time.time() < fim:
        try:
            with urllib.request.urlopen(base + "/api/eu", timeout=3) as rr:
                return json.loads(rr.read().decode())
        except Exception:
            if proc.poll() is not None:
                raise AssertionError(
                    "start.sh morreu antes do HTTP subir: %s" % proc.returncode)
            time.sleep(0.25)
    raise AssertionError("/api/eu nao respondeu em %ss" % teto_s)


def post_json(base, caminho, obj, teto_s=10):
    req = urllib.request.Request(
        base + caminho, data=json.dumps(obj).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=teto_s) as rr:
        return json.loads(rr.read().decode())


def get_texto(base, caminho, teto_s=10):
    with urllib.request.urlopen(base + caminho, timeout=teto_s) as rr:
        return rr.read().decode("utf-8")


def encerrar(proc):
    """SIGTERM no grupo + wait bounded; devolve o returncode."""
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        return proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        return proc.wait(timeout=15)


def iniciar(inst, tcp, udp, http, fixos="", log_path=None):
    env = {k: v for k, v in os.environ.items()
           if k not in ("SENDERME_HOME", "SENDERME_VERSAO", "SENDERME_FIXOS")}
    env.update({"SENDERME_PORTA": str(tcp),
                "SENDERME_UDP_PORTA": str(udp),
                "SENDERME_HTTP": str(http),
                "SENDERME_FIXOS": fixos})
    if log_path is None:
        proc = subprocess.Popen(
            ["bash", "start.sh"], cwd=inst, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
        return proc, None
    log = open(log_path, "ab")
    proc = subprocess.Popen(
        ["bash", "start.sh"], cwd=inst, env=env,
        stdout=log, stderr=subprocess.STDOUT,
        start_new_session=True)
    return proc, log


def conferir_envelope(manifest, sig_hex, n_hex, e):
    from senderme_app.update import manifest_canonico
    from crypto import conferir
    try:
        sig = bytes.fromhex(sig_hex)
        n = int(n_hex, 16)
    except Exception:
        return False
    return conferir(manifest_canonico(manifest), sig, n, e)


def montar_fixture_antiga(inst):
    """Fixture 1.2 com seu manifesto: manifesto do git + cada arquivo dele.

    Retorna o envelope antigo. Lista dinamica do manifesto (sem hardcode
    dos 7 nomes); pula fora via skipTest se o git nao tem a revisao.
    """
    bl_man = arquivo_git(REV_ANTIGA, MANIFESTO)
    if bl_man is None:
        return None
    with open(os.path.join(inst, MANIFESTO), "wb") as f:
        f.write(bl_man)
    env_antigo = json.loads(bl_man.decode("utf-8"))
    for a in env_antigo["manifest"]["arquivos"]:
        nome = a["nome"]
        blob = arquivo_git(REV_ANTIGA, nome)
        if blob is None:
            return None
        dst = os.path.join(inst, nome)
        os.makedirs(os.path.dirname(dst) or inst, exist_ok=True)
        with open(dst, "wb") as f:
            f.write(blob)
    return env_antigo


class MigracaoManual(unittest.TestCase):
    def test_antiga_para_nova_preserva_dados_e_envelope_coerente(self):
        import senderme_app.meta as meta
        # 1) instalacao antiga simulada (COM seu manifesto) + dados/ de TESTE
        inst = tempfile.mkdtemp(prefix="sm-migman-")
        self.addCleanup(shutil.rmtree, inst, True)
        env_antigo = montar_fixture_antiga(inst)
        if env_antigo is None:
            self.skipTest("sem git/%s disponivel" % REV_ANTIGA)
        antigo_sh = open(os.path.join(inst, "start.sh"),
                         encoding="utf-8").read()
        self.assertIn('cp "$APP_DIR/senderme.py" "$RUN_DIR/senderme.py"',
                      antigo_sh)  # sanidade: e' mesmo o launcher limitado
        # prova que a fixture tem envelope antigo coerente (sig real + hashes)
        self.assertEqual(env_antigo["manifest"]["v"], VERSAO_ANTIGA)
        self.assertTrue(
            conferir_envelope(env_antigo["manifest"], env_antigo["sig"],
                              meta.CHAVE_DONO_N, meta.CHAVE_DONO_E),
            "manifesto 1.2 historico nao confere (fixture corrompida?)")
        for a in env_antigo["manifest"]["arquivos"]:
            blob = open(os.path.join(inst, a["nome"]), "rb").read()
            self.assertEqual(len(blob), a["tamanho"], a["nome"])
            self.assertEqual(hashlib.sha256(blob).hexdigest(), a["sha256"],
                             a["nome"])
        dados = os.path.join(inst, "dados")
        identidade_rapida(dados)

        tcp, udp, http = porta_livre(), porta_livre(), porta_livre()
        base = "http://127.0.0.1:%d" % http

        # 2) boot com o launcher ANTIGO -> versao antiga, logado
        velho, _lg = iniciar(inst, tcp, udp, http)
        try:
            eu_velho = esperar_api_eu(http, velho)
        except Exception:
            encerrar(velho)
            raise
        self.assertTrue(eu_velho["logado"])
        self.assertEqual(eu_velho["nick"], "bot-teste")
        self.assertEqual(eu_velho["versao"], VERSAO_ANTIGA)
        texto_hist = "mensagem historica pre-migracao"
        try:
            r_env = post_json(base, "/api/enviar", {"texto": texto_hist})
        except Exception:
            encerrar(velho)
            raise
        self.assertTrue(r_env.get("ok"), r_env)
        # 3) fotografia de dados/ (antes)
        antes = foto_dados(dados)
        self.assertIn("historico.jsonl", antes)
        self.assertIn(texto_hist, antes["historico.jsonl"].decode("utf-8"))
        id_antes = eu_velho["id"]
        hash_antes = {k: hashlib.sha256(v).hexdigest()
                      for k, v in antes.items()}

        # 4) fechar o app antigo (Ctrl+C equivale a SIGTERM no grupo)
        rc_velho = encerrar(velho)
        self.assertNotEqual(rc_velho, 42)

        # 5) conjunto COMPLETO da release nova, nesta ordem, sem tocar dados/
        #    (dinamico de ARQUIVOS_UPDATE + manifesto; start.sh por ultimo)
        lista = list(meta.ARQUIVOS_UPDATE)  # nunca hardcode
        self.assertIn("senderme_app/app.py", lista)
        copiados = []
        for f in sorted(f for f in lista if f != "start.sh"):
            src = os.path.join(RAIZ, f)
            self.assertTrue(os.path.isfile(src), "fonte sumiu: %s" % f)
            dst = os.path.join(inst, f)
            os.makedirs(os.path.dirname(dst) or inst, exist_ok=True)
            shutil.copy2(src, dst)
            copiados.append(f)
        shutil.copy2(os.path.join(RAIZ, MANIFESTO),
                     os.path.join(inst, MANIFESTO))
        shutil.copy2(os.path.join(RAIZ, "start.sh"),
                     os.path.join(inst, "start.sh"))
        with open(os.path.join(inst, "start.sh"), encoding="utf-8") as f:
            self.assertIn("senderme_app/meta.py", f.read())  # launcher novo
        self.assertTrue(os.path.isfile(os.path.join(inst, "senderme_app",
                                                    "__init__.py")))

        # 6) confere assinatura+versao+completude+hashes (R4 em vermelho sem 5b:
        #    manifesto ficaria 1.2 e o hash de senderme.py nao bateria)
        env_novo = json.load(open(os.path.join(inst, MANIFESTO),
                                  encoding="utf-8"))
        self.assertTrue(
            conferir_envelope(env_novo["manifest"], env_novo["sig"],
                              meta.CHAVE_DONO_N, meta.CHAVE_DONO_E),
            "assinatura da release nova nao confere")
        self.assertEqual(env_novo["manifest"]["v"], meta.VERSAO)
        self.assertNotEqual(env_novo["manifest"]["v"], VERSAO_ANTIGA)
        for f in lista:
            self.assertTrue(os.path.isfile(os.path.join(inst, f)),
                            "release incompleta, falta: %s" % f)
        drift, adulterado = [], []
        for a in env_novo["manifest"]["arquivos"]:
            blob = open(os.path.join(inst, a["nome"]), "rb").read()
            if (len(blob) == a["tamanho"] and hashlib.sha256(blob).hexdigest()
                    == a["sha256"]):
                continue
            fonte = os.path.join(RAIZ, a["nome"])
            if (os.path.isfile(fonte)
                    and open(fonte, "rb").read() == blob):
                drift.append(a["nome"])  # manifesto desatualizado, copia fiel
            else:
                adulterado.append(a["nome"])
        self.assertEqual(adulterado, [],
                         "arquivos adulterados/divergentes: %s" % adulterado)
        # senderme.py (nucleo do R4) tem que estar coerente, nunca em drift
        self.assertNotIn("senderme.py", drift,
                         "senderme.py em drift: re-assine a release")
        if drift:
            print("\n[migracao-manual] drift conhecido (outra lane, sem "
                  "re-assinar): %s" % sorted(drift))

        # 7) boot com o launcher NOVO na mesma copia
        novo, _lg2 = iniciar(inst, tcp, udp, http)
        try:
            eu_novo = esperar_api_eu(http, novo)
        except Exception:
            encerrar(novo)
            raise
        try:
            # 8) app funcional + identidade preservada + versao nova
            self.assertTrue(eu_novo["logado"])
            self.assertEqual(eu_novo["nick"], "bot-teste")
            self.assertEqual(eu_novo["id"], id_antes)
            self.assertEqual(eu_novo["versao"], meta.VERSAO)
            self.assertNotEqual(eu_novo["versao"], VERSAO_ANTIGA)
            depois = foto_dados(dados)
            self.assertEqual(depois.get("identidade.json"),
                             antes.get("identidade.json"))
            self.assertEqual(depois.get("apelido.txt"),
                             antes.get("apelido.txt"))
            self.assertIn("historico.jsonl", depois)
            self.assertIn(texto_hist,
                          depois["historico.jsonl"].decode("utf-8"))
            self.assertIn(texto_hist, get_texto(base, "/api/mensagens"))
            self.assertIn("eventos",
                          get_texto(base, "/api/mensagens"))
            self.assertIsNone(novo.poll())  # segue rodando ate a fase P2P
            self.assertEqual(
                {k: hashlib.sha256(v).hexdigest()
                 for k, v in depois.items()
                 if k in ("identidade.json", "apelido.txt")},
                {k: hash_antes[k]
                 for k in ("identidade.json", "apelido.txt")})

            # 9) P2P: o migrado atualiza OUTRO peer antigo (envelope
            #    sintetico coerente com os arquivos reais - ver docstring)
            self._fase_p2p(inst, novo, tcp, meta, env_novo)
        finally:
            rc_novo = encerrar(novo)
        self.assertNotEqual(rc_novo, 42)  # sem restart espurio

    def _fase_p2p(self, migrado, proc_migrado, tcp_migrado, meta, env_novo):
        import sys as _sys
        _sys.path.insert(0, os.path.join(RAIZ, "tests"))
        import suporte
        from crypto import assinar as crypto_assinar
        from senderme_app.update import manifest_canonico

        chave_sint = suporte.chave_teste()
        n_hex_sint = format(chave_sint["n"], "x")
        # O servidor serve arquivos do RUN_DIR (/tmp, copiado no boot) e o
        # manifesto do disco; reescrever o meta DEPOIS do boot deixaria o
        # RUN_DIR com o meta real e o manifesto com o hash do sintetico.
        # Por isso PARA-SE o migrado, reescreve-se e REINICIA-SE: o RUN_DIR
        # novo sai coerente com o envelope servido.
        encerrar(proc_migrado)
        # reescrita minima do meta do migrado p/ a chave sintetica (so no
        # disco tmp; versao preservada). Servir nao confere, so o cliente.
        p_meta = os.path.join(migrado, "senderme_app", "meta.py")
        src_meta = open(p_meta, encoding="utf-8").read()
        novo_meta, n = re.subn(
            r'CHAVE_DONO_N\s*=\s*\(.*?\)',
            'CHAVE_DONO_N = "%s"' % n_hex_sint,
            src_meta, count=1, flags=re.S)
        self.assertEqual(n, 1, "padrao CHAVE_DONO_N nao achado em meta.py")
        with open(p_meta, "w", encoding="utf-8") as f:
            f.write(novo_meta)
        # envelope sintetico coerente com o que o migrado realmente serve
        conteudo = {}
        for nome in meta.ARQUIVOS_UPDATE:
            p = os.path.join(migrado, nome)
            self.assertTrue(os.path.isfile(p), "migrado sem %s" % nome)
            with open(p, "rb") as f:
                conteudo[nome] = f.read()
        manifest_sint = {"v": meta.VERSAO, "arquivos": [
            {"nome": n_, "tamanho": len(conteudo[n_]),
             "sha256": hashlib.sha256(conteudo[n_]).hexdigest()}
            for n_ in meta.ARQUIVOS_UPDATE]}
        sig_sint = crypto_assinar(manifest_canonico(manifest_sint),
                                  chave_sint).hex()
        env_sint = {"manifest": manifest_sint, "sig": sig_sint}
        with open(os.path.join(migrado, MANIFESTO), "w",
                  encoding="utf-8") as f:
            json.dump(env_sint, f, ensure_ascii=False)
        # reinicia o migrado para o RUN_DIR sair com o meta sintetico
        tcp_s, udp_s, http_s = porta_livre(), porta_livre(), porta_livre()
        serv, _lgs = iniciar(migrado, tcp_s, udp_s, http_s)
        try:
            eu_s = esperar_api_eu(http_s, serv)
        except Exception:
            encerrar(serv)
            raise
        self.assertEqual(eu_s["versao"], meta.VERSAO)
        try:
            self._p2p_cliente(serv=serv, tcp_s=tcp_s,
                              meta=meta, chave_sint=chave_sint,
                              n_hex_sint=n_hex_sint, env_sint=env_sint,
                              manifest_sint=manifest_sint)
        finally:
            encerrar(serv)

    def _p2p_cliente(self, serv, tcp_s, meta, chave_sint,
                     n_hex_sint, env_sint, manifest_sint):
        # segundo peer antigo (1.2 com manifesto) confiando na sintetica
        inst2 = tempfile.mkdtemp(prefix="sm-migp2p-")
        self.addCleanup(shutil.rmtree, inst2, True)
        env2 = montar_fixture_antiga(inst2)
        if env2 is None:
            self.skipTest("sem git/%s disponivel" % REV_ANTIGA)
        p_old = os.path.join(inst2, "senderme.py")
        src_old = open(p_old, encoding="utf-8").read()
        novo_old, n2 = re.subn(
            r'CHAVE_DONO_N\s*=\s*\(.*?\)',
            'CHAVE_DONO_N = ("%s")' % n_hex_sint,
            src_old, count=1, flags=re.S)
        self.assertEqual(n2, 1, "padrao CHAVE_DONO_N nao achado no 1.2")
        with open(p_old, "w", encoding="utf-8") as f:
            f.write(novo_old)
        dados2 = os.path.join(inst2, "dados")
        identidade_rapida(dados2)
        with open(os.path.join(dados2, "apelido.txt"), "w",
                  encoding="utf-8") as f:
            f.write("bot2")
        foto2_antes = foto_dados(dados2)
        tcp2, udp2, http2 = porta_livre(), porta_livre(), porta_livre()
        log2 = os.path.join(inst2, "launcher-p2p.log")
        c2, fh2 = iniciar(inst2, tcp2, udp2, http2,
                          fixos="127.0.0.1:%d" % tcp_s, log_path=log2)
        self.addCleanup(lambda: fh2.close() if fh2 else None)
        try:
            base2 = "http://127.0.0.1:%d" % http2
            # cliente antigo sobe em 1.2 antes do update
            eu2_0 = esperar_api_eu(http2, c2)
            self.assertEqual(eu2_0["versao"], VERSAO_ANTIGA)
            # aguarda o update completo: o launcher antigo termina (42 ->
            # restart falho conhecido -> exit 0 mascarado). Nao exige 42.
            fim = time.time() + TETO_P2P
            while time.time() < fim:
                if c2.poll() is not None:
                    break
                time.sleep(1.0)
            if c2.poll() is None:
                try:
                    cauda0 = open(log2, encoding="utf-8",
                                  errors="replace").read()[-2000:]
                except OSError:
                    cauda0 = ""
                try:
                    shutil.copy2(log2, "/tmp/opencode/migman-p2p-fail.log")
                except OSError:
                    pass
                self.fail("peer antigo nao aplicou o update via P2P em %ss; "
                          "log:\n%s" % (TETO_P2P, cauda0))
            try:
                cauda = open(log2, encoding="utf-8",
                             errors="replace").read()[-4000:]
            except OSError:
                cauda = ""
            self.assertIn("aplicado, reiniciando", cauda,
                          "sem evidencia de apply no log do cliente:\n%s"
                          % cauda[-2000:])
            # arquivos recebidos batem com o envelope servido (hashes)
            for a in manifest_sint["arquivos"]:
                blob = open(os.path.join(inst2, a["nome"]), "rb").read()
                self.assertEqual(len(blob), a["tamanho"], a["nome"])
                self.assertEqual(hashlib.sha256(blob).hexdigest(),
                                 a["sha256"], a["nome"])
            # completacao honesta da limitacao 1.2: o codigo antigo nao
            # persiste o envelope; copia-se o sintetico servido (ja
            # verificado acima) e boota-se com o start.sh NOVO que o P2P
            # trouxe; o start.sh no disco ja e' o novo (parte do pacote)
            with open(os.path.join(inst2, "start.sh"),
                       encoding="utf-8") as f:
                self.assertIn("senderme_app/meta.py", f.read())
            with open(os.path.join(inst2, MANIFESTO), "w",
                      encoding="utf-8") as f:
                json.dump(env_sint, f, ensure_ascii=False)
            tcp2b, udp2b, http2b = porta_livre(), porta_livre(), porta_livre()
            c2b, _lg = iniciar(inst2, tcp2b, udp2b, http2b)
            try:
                eu2_1 = esperar_api_eu(http2b, c2b)
            except Exception:
                encerrar(c2b)
                raise
            try:
                self.assertTrue(eu2_1["logado"])
                self.assertEqual(eu2_1["nick"], "bot2")
                self.assertEqual(eu2_1["versao"], meta.VERSAO)
                foto2_depois = foto_dados(dados2)
                self.assertEqual(foto2_depois.get("identidade.json"),
                                 foto2_antes.get("identidade.json"))
                self.assertEqual(foto2_depois.get("apelido.txt"),
                                 foto2_antes.get("apelido.txt"))
                # envelope coerente no cliente atualizado (sintetica)
                env_cli = json.load(open(os.path.join(inst2, MANIFESTO),
                                         encoding="utf-8"))
                self.assertEqual(env_cli["manifest"]["v"], meta.VERSAO)
                self.assertTrue(conferir_envelope(
                    env_cli["manifest"], env_cli["sig"], n_hex_sint,
                    chave_sint["e"]))
                for a in env_cli["manifest"]["arquivos"]:
                    blob = open(os.path.join(inst2, a["nome"]),
                                "rb").read()
                    self.assertEqual(hashlib.sha256(blob).hexdigest(),
                                     a["sha256"], a["nome"])
                self.assertIn("eventos", get_texto(
                    "http://127.0.0.1:%d" % http2b, "/api/mensagens"))
            finally:
                encerrar(c2b)
        finally:
            if c2.poll() is None:
                encerrar(c2)


if __name__ == "__main__":
    unittest.main()
