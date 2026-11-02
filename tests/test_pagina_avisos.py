"""UI avisos (item 2): login ok+aviso exibe; falha real preserva; guardada limpa.

Escopo @designer: cobre pagina.py (HTML/JS embutido) sem editar backend.
Contrato consumido: /api/login -> {ok,msg}; /api/enviar -> {ok,msg,resposta,estado}.
estado in {entregue,guardada,somente_memoria,erro} quando presente (backend novo):
entregue/guardada limpam, somente_memoria/erro preservam. Quando ausente
(backend antigo), vale o fallback legado por texto, documentado abaixo.
JS verificado via node --check no JS servido + sondas Node com DOM simulado
+ browser isolado (chromium headless, perfil tmp) ou limitacao registrada.
"""
import json
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from pathlib import Path

import pagina
import senderme as sm
from suporte import CasoIsolado, definir_eu, definir_par


def extrair_js():
    m = re.search(r"<script[^>]*>(.*?)</script>", pagina.PAGINA, re.S | re.I)
    assert m, "PAGINA sem <script>"
    return m.group(1)


def fatiar(js):
    ini_login = js.index("async function login(){")
    fim_login = js.index("async function trocarNick(){")
    ini_submit = js.index('document.getElementById("form").addEventListener("submit"')
    fim_submit = js.index('document.getElementById("texto").addEventListener("keydown"')
    login = js[ini_login:fim_login]
    submit = js[ini_submit:fim_submit]
    return login, submit


NODE_OK = shutil.which("node") is not None
CHROME = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")


def rodar_node(prefixo, login, submit, sufixo, timeout=15):
    with tempfile.TemporaryDirectory(prefix="sm-ui-") as td:
        p = Path(td) / "sonda.js"
        p.write_text(prefixo + login + submit + sufixo, encoding="utf-8")
        r = subprocess.run(["node", str(p)], capture_output=True, text=True, timeout=timeout)
        return r


PREFIXO_BASE = """let handler=null; let enviando=false; let estadoChamado=false; let alerts=[]; let pollChamado=false; let ouvintes={};
const nodes={nick:{value:"alice"},loginerr:{textContent:""},form:{addEventListener:(t,f)=>{if(t==="submit")handler=f;}},arq:{files:[],value:""},para:{value:"",addEventListener:(t,f)=>{ouvintes["para:"+t]=f;}},texto:{value:"mensagem-sintetica",addEventListener:(t,f)=>{ouvintes["texto:"+t]=f;}},sys:{textContent:""},btnEnviar:{disabled:false}};
const document={getElementById:(id)=>nodes[id]||{textContent:"",value:"",style:{}}};
function poll(){pollChamado=true;}
function alert(x){alerts.push(String(x));}
function digitar(id,v){nodes[id].value=v; const f=ouvintes[id+":input"]; if(f)f({target:nodes[id]});}
"""


@unittest.skipUnless(NODE_OK, "sem node no PATH")
class SintaxeJS(unittest.TestCase):
    def test_node_check_no_js_servido(self):
        js = extrair_js()
        with tempfile.TemporaryDirectory(prefix="sm-jscheck-") as td:
            p = Path(td) / "pagina.js"
            p.write_text(js, encoding="utf-8")
            r = subprocess.run(["node", "--check", str(p)], capture_output=True, text=True, timeout=15)
            self.assertEqual(r.returncode, 0, "node --check falhou: %s" % (r.stderr or r.stdout))


@unittest.skipUnless(NODE_OK, "sem node no PATH")
class ComportamentoJS(unittest.TestCase):
    def test_login_ok_com_aviso_exibe(self):
        """(a) login ok:true + msg de aviso tem de chegar a interface."""
        js = extrair_js()
        login, submit = fatiar(js)
        api = 'async function api(p,o){ if(p==="/api/login") return {ok:true,msg:"Voce e alice. (aviso: apelido.txt nao foi salvo)"}; return {ok:true}; }\nfunction estado(){estadoChamado=true;return Promise.resolve();}\n'
        sufixo = ('(async()=>{ await login(); const w=nodes.loginerr.textContent+"|"+nodes.sys.textContent+"|"+alerts.join("|");'
                  ' console.log(JSON.stringify({w,estadoChamado})); })().catch(e=>{console.error(String(e));process.exitCode=1;});')
        r = rodar_node(PREFIXO_BASE + api, login, submit, sufixo)
        self.assertEqual(r.returncode, 0, r.stderr)
        obs = json.loads(r.stdout)
        self.assertTrue(obs["estadoChamado"], "login ok deveria chamar estado()")
        self.assertIn("aviso", obs["w"].lower(), "aviso do login bem-sucedido nao chegou a interface")

    def test_envio_falha_real_preserva_texto(self):
        """(b) ok:false + resposta de persistencia: mostra aviso e MANTEM texto."""
        js = extrair_js()
        login, submit = fatiar(js)
        api = ('async function api(p,o){ if(p==="/api/enviar") return {ok:false,msg:"X",resposta:"Sem conexao com bob agora (AVISO: nao consegui salvar em historico.jsonl)"};'
               ' return {ok:true}; }\nfunction estado(){}\n')
        sufixo = ('(async()=>{ nodes.texto.value="mensagem-sintetica"; nodes.para.value=""; await handler({preventDefault(){}});'
                  ' console.log(JSON.stringify({after:nodes.texto.value,sys:nodes.sys.textContent})); })().catch(e=>{console.error(String(e));process.exitCode=1;});')
        r = rodar_node(PREFIXO_BASE + api, login, submit, sufixo)
        self.assertEqual(r.returncode, 0, r.stderr)
        obs = json.loads(r.stdout)
        self.assertIn("AVISO", obs["sys"], "resposta de falha deveria aparecer em #sys")
        self.assertEqual(obs["after"], "mensagem-sintetica", "texto foi apagado apos falha real (perda nao recuperavel)")

    def test_envio_guardada_limpa_sem_duplicata(self):
        """ok:false + (guardada) foi salva: pode limpar para nao induzir reenvio."""
        js = extrair_js()
        login, submit = fatiar(js)
        api = ('async function api(p,o){ if(p==="/api/enviar") return {ok:false,msg:"X",resposta:"Sem conexao com bob agora (guardada; entrego quando voltar)."};'
               ' return {ok:true}; }\nfunction estado(){}\n')
        sufixo = ('(async()=>{ nodes.texto.value="mensagem-sintetica"; await handler({preventDefault(){}});'
                  ' console.log(JSON.stringify({after:nodes.texto.value,sys:nodes.sys.textContent})); })().catch(e=>{console.error(String(e));process.exitCode=1;});')
        r = rodar_node(PREFIXO_BASE + api, login, submit, sufixo)
        self.assertEqual(r.returncode, 0, r.stderr)
        obs = json.loads(r.stdout)
        self.assertIn("guardada", obs["sys"].lower(), "aviso de guardada deveria aparecer")
        self.assertEqual(obs["after"], "", "mensagem guardada deveria limpar (evitar duplicata)")

    def test_envio_ok_limpa(self):
        js = extrair_js()
        login, submit = fatiar(js)
        api = 'async function api(p,o){ return {ok:true,msg:"",resposta:""}; }\nfunction estado(){}\n'
        sufixo = ('(async()=>{ nodes.texto.value="mensagem-sintetica"; await handler({preventDefault(){}});'
                  ' console.log(JSON.stringify({after:nodes.texto.value,sys:nodes.sys.textContent})); })().catch(e=>{console.error(String(e));process.exitCode=1;});')
        r = rodar_node(PREFIXO_BASE + api, login, submit, sufixo)
        self.assertEqual(r.returncode, 0, r.stderr)
        obs = json.loads(r.stdout)
        self.assertEqual(obs["after"], "", "envio ok deveria limpar")
        self.assertEqual(obs["sys"], "", "envio ok sem resposta deveria limpar #sys")


@unittest.skipUnless(NODE_OK, "sem node no PATH")
class ComportamentoEstado(unittest.TestCase):
    """Contrato novo: r.estado decide; texto nao decide.

    Matriz: entregue/guardada -> LIMPA; somente_memoria/erro -> PRESERVA.
    Sem estado (backend antigo): fallback legado por texto, mantido p/
    compatibilidade e coberto em test_sem_estado_usa_fallback_legado.
    """

    def _enviar(self, resposta_js):
        js = extrair_js()
        login, submit = fatiar(js)
        api = ('async function api(p,o){ if(p==="/api/enviar") return %s;'
               ' return {ok:true}; }\nfunction estado(){}\n' % resposta_js)
        sufixo = ('(async()=>{ nodes.texto.value="mensagem-sintetica"; nodes.para.value=""; await handler({preventDefault(){}});'
                  ' console.log(JSON.stringify({after:nodes.texto.value,sys:nodes.sys.textContent})); })().catch(e=>{console.error(String(e));process.exitCode=1;});')
        r = rodar_node(PREFIXO_BASE + api, login, submit, sufixo)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_estado_guardada_com_aviso_no_apelido_limpa(self):
        """DM guardada p/ @aviso: texto tem 'aviso' mas estado manda limpar."""
        obs = self._enviar('{ok:false,msg:"X",resposta:"Sem conexao com aviso agora (guardada; entrego quando voltar).",estado:"guardada"}')
        self.assertIn("guardada", obs["sys"].lower(), "aviso de guardada deveria aparecer")
        self.assertEqual(obs["after"], "", "estado guardada deveria limpar mesmo com 'aviso' no texto")

    def test_estado_erro_com_guardada_no_nome_preserva(self):
        """Destino inexistente @guardada: texto tem 'guardada' mas estado manda preservar."""
        obs = self._enviar('{ok:false,msg:"X",resposta:"Nao encontrei \'@guardada\'.",estado:"erro"}')
        self.assertIn("guardada", obs["sys"].lower(), "erro deveria aparecer em #sys")
        self.assertEqual(obs["after"], "mensagem-sintetica", "estado erro deveria preservar mesmo com 'guardada' no texto")

    def test_estado_somente_memoria_preserva_mesmo_com_texto_de_guardada(self):
        """Mesmo texto de guardada, mas estado diz que ficou so em memoria: preserva."""
        obs = self._enviar('{ok:false,msg:"X",resposta:"Sem conexao com bob agora (guardada; entrego quando voltar).",estado:"somente_memoria"}')
        self.assertIn("guardada", obs["sys"].lower(), "resposta deveria aparecer em #sys")
        self.assertEqual(obs["after"], "mensagem-sintetica", "estado somente_memoria deveria preservar")

    def test_estado_entregue_limpa(self):
        obs = self._enviar('{ok:true,msg:"",resposta:"Entregue para aviso.",estado:"entregue"}')
        self.assertIn("aviso", obs["sys"].lower(), "resposta deveria aparecer em #sys")
        self.assertEqual(obs["after"], "", "estado entregue deveria limpar")

    def test_sem_estado_usa_fallback_legado(self):
        """Sem estado (backend antigo): fallback por texto, sem mudar legado."""
        obs = self._enviar('{ok:false,msg:"X",resposta:"Nao encontrei \'@fulano\'."}')
        self.assertEqual(obs["after"], "mensagem-sintetica", "fallback: erro sem palavra de guardada preserva")
        obs2 = self._enviar('{ok:false,msg:"X",resposta:"Sem conexao com bob agora (guardada; entrego quando voltar)."}')
        self.assertEqual(obs2["after"], "", "fallback: guardada sem aviso limpa (legado)")


@unittest.skipUnless(NODE_OK, "sem node no PATH")
class TransmitidaNaoSalva(unittest.TestCase):
    """Item 2 (rodada 1.10): r.transmitida separa transmissao de persistencia.

    Matriz (resposta -> aviso/texto/botao):
      transmitida=true + somente_memoria -> aviso canonico ("transmitida,
        mas NAO salva no historico", sem alegar recebimento/leitura),
        MANTEM o texto como copia recuperavel e BLOQUEIA o reenvio do
        conteudo identico (botao desabilitado + submit ignora); editar
        libera novo envio.
      transmitida=false ou ausente (backend antigo) -> legado inalterado
        (preserva texto, permite retry; besluta por r.estado/texto).
    O observado na sonda (2 cliques -> 2 mids) continua documentado:
    sem `transmitida` o reenvio segue permitido; com `transmitida=true`
    o segundo clique identico nao chama mais a API.
    """

    def _duplo_clique(self, resposta_js, texto="oi", para="@bob", editar=None):
        js = extrair_js()
        login, submit = fatiar(js)
        api = ('let chamadas=0;\nasync function api(p,o){ if(p==="/api/enviar"){chamadas++; return %s;}'
               ' return {ok:true}; }\nfunction estado(){}\n' % resposta_js)
        passo_edicao = ('digitar("texto",%s); ' % json.dumps(editar)) if editar is not None else ''
        sufixo = ('(async()=>{ nodes.texto.value=%s; nodes.para.value=%s;'
                   ' await handler({preventDefault(){}});'
                   ' const a={sys:nodes.sys.textContent,after:nodes.texto.value,btn:nodes.btnEnviar.disabled,c:chamadas};'
                   ' %sawait handler({preventDefault(){}});'
                   ' const b={sys:nodes.sys.textContent,after:nodes.texto.value,btn:nodes.btnEnviar.disabled,c:chamadas};'
                   ' console.log(JSON.stringify({a,b})); })().catch(e=>{console.error(String(e));process.exitCode=1;});'
                   % (json.dumps(texto), json.dumps(para), passo_edicao))
        r = rodar_node(PREFIXO_BASE + api, login, submit, sufixo)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_transmitida_nao_salva_avisa_mantem_e_bloqueia(self):
        obs = self._duplo_clique('{ok:true,resposta:"Enviada para bob (aviso: nao consegui salvar em historico.jsonl).",'
                                 'estado:"somente_memoria",transmitida:true}')
        a, b = obs["a"], obs["b"]
        sysbaixo = a["sys"].lower()
        self.assertIn("transmitida", sysbaixo, "aviso canonico ausente: %r" % a["sys"])
        self.assertIn("n\u00e3o salva", sysbaixo, "aviso deve dizer que NAO salvou: %r" % a["sys"])
        self.assertIn("hist\u00f3rico", sysbaixo, "aviso deve citar o historico: %r" % a["sys"])
        self.assertNotIn("recebid", sysbaixo, "sem alegar recebimento: %r" % a["sys"])
        self.assertNotIn("leitura", sysbaixo, "sem alegar leitura: %r" % a["sys"])
        self.assertNotIn("lida", sysbaixo, "sem alegar leitura: %r" % a["sys"])
        self.assertEqual(a["after"], "oi", "texto deve ficar como copia recuperavel")
        self.assertTrue(a["btn"], "envio deveria desabilitar apos transmitida-nao-salva")
        self.assertEqual(a["c"], 1)
        self.assertEqual(b["c"], 1, "segundo clique identico nao pode reenviar (duplicata)")
        self.assertEqual(b["after"], "oi", "copia recuperavel perdida no 2o clique")
        self.assertTrue(b["btn"], "bloqueio deveria persistir com texto igual")

    def test_editar_libera_novo_envio(self):
        obs = self._duplo_clique('{ok:true,resposta:"Enviada para bob (aviso: nao consegui salvar).",'
                                 'estado:"somente_memoria",transmitida:true}',
                                 texto="oi", editar="oi!")
        b = obs["b"]
        self.assertEqual(b["c"], 2, "texto editado deveria liberar novo envio")
        self.assertEqual(b["after"], "oi!", "nova copia mantida (tambem nao salva)")

    def test_transmitida_false_permite_retry(self):
        """Offline de verdade (nao transmitiu): legado, retry permitido."""
        obs = self._duplo_clique('{ok:false,resposta:"Sem conexao com bob agora (AVISO: nao consegui salvar em historico.jsonl).",'
                                 'estado:"somente_memoria",transmitida:false}')
        a, b = obs["a"], obs["b"]
        self.assertEqual(a["after"], "oi", "legado: texto mantido")
        self.assertFalse(a["btn"], "legado: botao segue habilitado sem transmissao")
        self.assertEqual(b["c"], 2, "legado: retry de nao-transmitida segue permitido")

    def test_sem_transmitida_legado_inalterado(self):
        """Backend antigo (sem campo): comportamento atual preservado."""
        obs = self._duplo_clique('{ok:true,resposta:"Enviada para bob (aviso: nao consegui salvar em historico.jsonl).",'
                                 'estado:"somente_memoria"}')
        a, b = obs["a"], obs["b"]
        self.assertEqual(a["after"], "oi", "legado: texto mantido")
        self.assertFalse(a["btn"], "legado: sem transmitida, sem bloqueio")
        self.assertEqual(b["c"], 2, "legado: sem transmitida, reenvio segue como antes")

    def test_transmitida_true_entregue_limpa(self):
        obs = self._duplo_clique('{ok:true,resposta:"",estado:"entregue",transmitida:true}')
        a = obs["a"]
        self.assertEqual(a["after"], "", "entregue deveria limpar")
        self.assertFalse(a["btn"], "botao habilitado apos envio normal")


@unittest.skipUnless(NODE_OK, "sem node no PATH")
class NivelPublicaHonesta(unittest.TestCase):
    """Item 3 (1.11): publica aceita localmente nao induz difusao/entrega.

    Matriz (resposta -> #sys/texto):
      publica nivel=local peers=0 resposta="" -> limpa +
        "Publicada localmente, sem peers conectados" (sem implicar difusao).
      publica nivel=local peers=2 -> limpa +
        "Publicada localmente para 2 peer(s)" + "sem confirmação".
      DM nivel=socket entregue resposta="" -> limpa +
        "Enviada" + "sem confirmação" (sem afirmar recebimento/leitura).
      legado sem nivel (backend antigo) -> silencio como antes (compat).
    Nenhum texto novo afirma recebimento/leitura: todos trazem
    "sem confirmação de recebimento ou leitura" quando falam de envio.
    """

    def _enviar(self, resposta_js, texto="mensagem-sintetica", para=""):
        js = extrair_js()
        login, submit = fatiar(js)
        api = ('async function api(p,o){ if(p==="/api/enviar") return %s;'
               ' return {ok:true}; }\nfunction estado(){}\n' % resposta_js)
        sufixo = ('(async()=>{ nodes.texto.value=%s; nodes.para.value=%s;'
                   ' await handler({preventDefault(){}});'
                   ' console.log(JSON.stringify({after:nodes.texto.value,sys:nodes.sys.textContent,btn:nodes.btnEnviar.disabled}));'
                   ' })().catch(e=>{console.error(String(e));process.exitCode=1;});'
                   % (json.dumps(texto), json.dumps(para)))
        r = rodar_node(PREFIXO_BASE + api, login, submit, sufixo)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_publica_sem_peers_diz_local(self):
        obs = self._enviar('{ok:true,msg:"",resposta:"",estado:"entregue",transmitida:true,nivel:"local",confirmado:false,peers:0}',
                           texto="oi publica", para="")
        self.assertEqual(obs["after"], "", "publica aceita deveria limpar")
        sysbaixo = obs["sys"].lower()
        self.assertIn("publicada localmente", sysbaixo)
        self.assertIn("sem peers", sysbaixo)
        self.assertNotIn("difund", sysbaixo)
        self.assertNotIn("entregue para", sysbaixo)

    def test_publica_com_peers_diz_contagem_sem_confirmacao(self):
        obs = self._enviar('{ok:true,msg:"",resposta:"",estado:"entregue",transmitida:true,nivel:"local",confirmado:false,peers:2}',
                           texto="oi publica", para="")
        self.assertEqual(obs["after"], "")
        sysbaixo = obs["sys"].lower()
        self.assertIn("publicada localmente", sysbaixo)
        self.assertIn("2 peer", sysbaixo)
        self.assertIn("sem confirma", sysbaixo)
        self.assertIn("recebimento", sysbaixo)

    def test_dm_socket_diz_enviada_sem_confirmacao(self):
        obs = self._enviar('{ok:true,msg:"",resposta:"",estado:"entregue",transmitida:true,nivel:"socket",confirmado:false,peers:1}',
                           texto="segredo", para="@bob")
        self.assertEqual(obs["after"], "", "DM socket deveria limpar")
        sysbaixo = obs["sys"].lower()
        self.assertIn("enviada", sysbaixo)
        self.assertIn("sem confirma", sysbaixo)
        self.assertIn("recebimento", sysbaixo)
        for afirma in ("recebido", "recebida", " lida", "foi entregue", "entregue para", "leitura confirmada"):
            self.assertNotIn(afirma, sysbaixo, "texto afirma entrega: %r" % obs["sys"])

    def test_legado_sem_nivel_mantem_silencio(self):
        obs = self._enviar('{ok:true,msg:"",resposta:""}',
                           texto="oi publica", para="")
        self.assertEqual(obs["after"], "", "legado ok limpa")
        self.assertEqual(obs["sys"], "", "legado sem nivel mantem silencio (compat)")

    def test_nunca_afirma_recebimento_nos_novos(self):
        # 0 peers: honestidade = "sem peers + só você" (sem implicar difusão);
        # com peers/DM socket: honestidade = "sem confirmação" explícita.
        obs0 = self._enviar('{ok:true,msg:"",resposta:"",estado:"entregue",transmitida:true,nivel:"local",confirmado:false,peers:0}',
                            texto="oi", para="")
        sys0 = obs0["sys"].lower()
        self.assertIn("sem peers", sys0)
        for afirma in ("recebido", "recebida", " lida", "foi entregue", "entregue para"):
            self.assertNotIn(afirma, sys0, "afirmacao indevida: %r" % obs0["sys"])
        for resp, txt, par in (
            ('{ok:true,msg:"",resposta:"",estado:"entregue",transmitida:true,nivel:"local",confirmado:false,peers:2}', "oi", ""),
            ('{ok:true,msg:"",resposta:"",estado:"entregue",transmitida:true,nivel:"socket",confirmado:false,peers:1}', "segredo", "@bob"),
        ):
            obs = self._enviar(resp, texto=txt, para=par)
            sysbaixo = obs["sys"].lower()
            self.assertIn("sem confirma", sysbaixo, "novo texto deve negar confirmacao: %r" % obs["sys"])
            for afirma in ("recebido", "recebida", " lida", "foi entregue", "entregue para"):
                self.assertNotIn(afirma, sysbaixo, "afirmacao indevida: %r" % obs["sys"])


class ContratoHttp(CasoIsolado):
    """API<->UI real: shapes que a pagina consome, em HTTP 127.0.0.1 efemero."""

    def _subir(self):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), sm.Handler)
        porta = srv.server_address[1]
        fio = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        fio.start()
        self.addCleanup(srv.shutdown)
        self.addCleanup(srv.server_close)
        return porta

    def _post(self, porta, rota, obj):
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (porta, rota),
                                     data=json.dumps(obj).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    def test_login_e_enviar_shapes(self):
        definir_eu("alice")
        porta = self._subir()
        cod, d = self._post(porta, "/api/login", {"nick": "alice2"})
        self.assertEqual(cod, 200)
        self.assertTrue(d["ok"], d)
        self.assertIn("msg", d, "UI le r.msg no login")
        # envio normal publica e volta ok:true + resposta
        cod2, d2 = self._post(porta, "/api/enviar", {"texto": "oi http", "para": ""})
        self.assertEqual(cod2, 200)
        self.assertIn("ok", d2)
        self.assertIn("resposta", d2, "UI le r.resposta no enviar")
        self.assertTrue(d2["ok"])
        # DM para desconhecido: ok:false + resposta explicativa (nada guardado)
        _, d3 = self._post(porta, "/api/enviar", {"texto": "psst", "para": "@ninguem-xyz"})
        self.assertFalse(d3["ok"])
        self.assertTrue(d3.get("resposta") or d3.get("msg"))

    def test_pagina_servida_tem_ganchos(self):
        definir_eu("alice")
        porta = self._subir()
        with urllib.request.urlopen("http://127.0.0.1:%d/" % porta, timeout=10) as r:
            html = r.read().decode("utf-8")
        for gancho in ('id="sys"', 'id="texto"', 'id="loginerr"', 'id="form"', "/api/login", "/api/enviar"):
            self.assertIn(gancho, html, "gancho ausente no HTML servido: %s" % gancho)

    def test_pagina_servida_tem_ganchos_transmitida(self):
        """Ganchos do item 2 no HTML servido via HTTP real."""
        definir_eu("alice")
        porta = self._subir()
        with urllib.request.urlopen("http://127.0.0.1:%d/" % porta, timeout=10) as r:
            html = r.read().decode("utf-8")
        for gancho in ('id="btnEnviar"', "AVISO_NAO_SALVO", "atualizarBloqueio",
                       "ultimoNaoSalvo", "transmitida"):
            self.assertIn(gancho, html, "gancho ausente no HTML servido: %s" % gancho)

    @unittest.skipUnless(NODE_OK, "sem node no PATH")
    def test_js_servido_http_check_e_transmitida(self):
        """JS extraido do HTTP real: node --check + cenario transmitida em DOM simulado."""
        definir_eu("alice")
        porta = self._subir()
        with urllib.request.urlopen("http://127.0.0.1:%d/" % porta, timeout=10) as r:
            html = r.read().decode("utf-8")
        m = re.search(r"<script[^>]*>(.*?)</script>", html, re.S | re.I)
        self.assertIsNotNone(m, "HTTP / sem <script>")
        js = m.group(1)
        with tempfile.TemporaryDirectory(prefix="sm-jshttp-") as td:
            p = Path(td) / "servido.js"
            p.write_text(js, encoding="utf-8")
            r = subprocess.run(["node", "--check", str(p)], capture_output=True,
                               text=True, timeout=15)
            self.assertEqual(r.returncode, 0, "node --check no JS servido falhou: %s"
                             % (r.stderr or r.stdout))
        login, submit = fatiar(js)
        api = ('let chamadas=0;\nasync function api(p,o){ if(p==="/api/enviar"){chamadas++;'
               ' return {ok:true,resposta:"Enviada para bob (aviso: nao salvou).",'
               'estado:"somente_memoria",transmitida:true};}'
               ' return {ok:true}; }\nfunction estado(){}\n')
        sufixo = ('(async()=>{ nodes.texto.value="oi-http"; nodes.para.value="@bob";'
                   ' await handler({preventDefault(){}});'
                   ' const a={sys:nodes.sys.textContent,after:nodes.texto.value,btn:nodes.btnEnviar.disabled,c:chamadas};'
                   ' await handler({preventDefault(){}});'
                   ' const b={btn:nodes.btnEnviar.disabled,c:chamadas,after:nodes.texto.value};'
                   ' console.log(JSON.stringify({a,b})); })().catch(e=>{console.error(String(e));process.exitCode=1;});')
        r = rodar_node(PREFIXO_BASE + api, login, submit, sufixo)
        self.assertEqual(r.returncode, 0, r.stderr)
        obs = json.loads(r.stdout)
        self.assertIn("transmitida", obs["a"]["sys"].lower())
        self.assertEqual(obs["a"]["after"], "oi-http")
        self.assertTrue(obs["a"]["btn"])
        self.assertEqual(obs["b"]["c"], 1, "JS servido: 2o clique identico nao reenvia")


@unittest.skipUnless(CHROME, "sem chromium no PATH")
class NavegadorIsolado(CasoIsolado):
    """Browser isolado: perfil/dir tmp, sem abas pessoais. Carga + fluxo reais."""

    def _servir(self):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), sm.Handler)
        porta = srv.server_address[1]
        fio = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        fio.start()
        self.addCleanup(srv.shutdown)
        self.addCleanup(srv.server_close)
        return porta

    def test_carga_isolada_renderiza_login(self):
        definir_eu("alice")
        porta = self._servir()
        with tempfile.TemporaryDirectory(prefix="sm-chrome-") as prof:
            exe = CHROME
            url = "http://127.0.0.1:%d/" % porta
            cmd = [exe, "--headless=new", "--no-sandbox", "--disable-gpu",
                   "--user-data-dir=%s" % prof, "--virtual-time-budget=3000",
                   "--dump-dom", url]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
            except subprocess.TimeoutExpired:
                self.fail("chromium travou (timeout 40s)")
            self.assertEqual(r.returncode, 0, "chromium saiu %s: %s" % (r.returncode, (r.stderr or "")[-2000:]))
            dom = r.stdout
            self.assertIn("Escolha seu apelido", dom, "tela de login nao renderizou no browser isolado")
            self.assertIn('id="texto"', dom)

    def test_fluxo_login_aviso_e_envio_falho_preserva(self):
        """Cliques reais no Blink isolado contra API real: login mostra aviso,
        DM para desconhecido exibe erro e mantem o texto."""
        import html as html_mod
        import os
        definir_eu("alice")
        # forca aviso real de persistencia no login (mesma tecnica de test_persist_falhas)
        ap = os.path.join(sm.DADOS, "apelido.txt")
        os.makedirs(sm.DADOS, exist_ok=True)
        if os.path.isfile(ap):
            os.remove(ap)
        os.makedirs(ap, exist_ok=True)
        autopilot = """<script>
(async()=>{
 const out={loginSys:"",appVisivel:false,afterSend:"?",sysAposEnvio:"",erro:""};
 try{
  document.getElementById("nick").value="alice-browser";
  await login();
  await new Promise(r=>setTimeout(r,1200));
  out.loginSys=document.getElementById("sys").textContent||"";
  out.appVisivel=document.getElementById("app").style.display!=="none";
  document.getElementById("texto").value="mensagem-browser";
  document.getElementById("para").value="@ninguem-que-nao-existe-xyz";
  document.getElementById("form").requestSubmit();
  await new Promise(r=>setTimeout(r,1200));
  out.afterSend=document.getElementById("texto").value;
  out.sysAposEnvio=document.getElementById("sys").textContent||"";
 }catch(e){out.erro=String(e&&e.stack||e)}
 const pre=document.createElement("pre"); pre.id="autopilot-result"; pre.textContent=JSON.stringify(out);
 document.body.appendChild(pre);
})();
</script>"""
        import senderme_app.http as H
        orig = H.PAGINA
        H.PAGINA = pagina.PAGINA.replace("</body>", autopilot + "</body>")
        self.addCleanup(setattr, H, "PAGINA", orig)
        porta = self._servir()
        with tempfile.TemporaryDirectory(prefix="sm-chrome-") as prof:
            cmd = [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
                   "--user-data-dir=%s" % prof, "--virtual-time-budget=6000",
                   "--dump-dom", "http://127.0.0.1:%d/" % porta]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            except subprocess.TimeoutExpired:
                self.fail("chromium travou (timeout 60s)")
            self.assertEqual(r.returncode, 0, "chromium saiu %s: %s" % (r.returncode, (r.stderr or "")[-2000:]))
            m = re.search(r'<pre id="autopilot-result">(.*?)</pre>', r.stdout, re.S)
            self.assertIsNotNone(m, "autopilot nao escreveu resultado no DOM isolado")
            obs = json.loads(html_mod.unescape(m.group(1)))
            self.assertEqual(obs.get("erro", ""), "", "erro no autopilot: %s" % obs.get("erro"))
            self.assertTrue(obs.get("appVisivel"), "app deveria aparecer apos login")
            self.assertIn("aviso", (obs.get("loginSys") or "").lower(),
                          "aviso de login nao apareceu no browser isolado: %r" % obs.get("loginSys"))
            self.assertIn("encontr", (obs.get("sysAposEnvio") or "").lower(),
                          "erro de envio nao apareceu: %r" % obs.get("sysAposEnvio"))
            self.assertEqual(obs.get("afterSend"), "mensagem-browser",
                             "browser isolado apagou texto apos falha real")

    def test_transmitida_bloqueia_reenvio_no_blink(self):
        """Blink isolado + handler de producao: transmitida-nao-salva mantem a
        copia, desabilita o botao real, ignora o 2o clique e libera ao editar.

        Stub apenas na fronteira `api()` p/ /api/enviar, no formato do
        contrato novo (backend em outro lane): {ok, resposta,
        estado:"somente_memoria", transmitida:true}. O resto (DOM, handler,
        eventos) e producao real."""
        import html as html_mod
        definir_eu("alice")
        autopilot = """<script>
(async()=>{
 const out={erro:"",sys1:"",after1:"?",btn1:null,chamadas1:-1,btn2:null,chamadas2:-1,after2:"?",btnEdit:null,chamadas3:-1};
 try{
  const _api=api; let n=0;
  api=async function(p,o){ if(p==="/api/enviar"){n++; return {ok:true,resposta:"Enviada (aviso: nao salvou).",estado:"somente_memoria",transmitida:true};} return _api(p,o); };
  const espera=()=>new Promise(r=>setTimeout(r,400));
  document.getElementById("texto").value="oi-browser";
  document.getElementById("para").value="@bob";
  document.getElementById("form").requestSubmit();
  await espera();
  out.sys1=document.getElementById("sys").textContent||"";
  out.after1=document.getElementById("texto").value;
  out.btn1=document.getElementById("btnEnviar").disabled;
  out.chamadas1=n;
  document.getElementById("form").requestSubmit();
  await espera();
  out.btn2=document.getElementById("btnEnviar").disabled;
  out.chamadas2=n;
  out.after2=document.getElementById("texto").value;
  const tx=document.getElementById("texto");
  tx.value="oi-browser-editada";
  tx.dispatchEvent(new Event("input",{bubbles:true}));
  out.btnEdit=document.getElementById("btnEnviar").disabled;
  document.getElementById("form").requestSubmit();
  await espera();
  out.chamadas3=n;
 }catch(e){out.erro=String(e&&e.stack||e)}
 const pre=document.createElement("pre"); pre.id="autopilot-result"; pre.textContent=JSON.stringify(out);
 document.body.appendChild(pre);
})();
</script>"""
        import senderme_app.http as H
        orig = H.PAGINA
        H.PAGINA = pagina.PAGINA.replace("</body>", autopilot + "</body>")
        self.addCleanup(setattr, H, "PAGINA", orig)
        porta = self._servir()
        with tempfile.TemporaryDirectory(prefix="sm-chrome-") as prof:
            cmd = [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
                   "--user-data-dir=%s" % prof, "--virtual-time-budget=9000",
                   "--dump-dom", "http://127.0.0.1:%d/" % porta]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            except subprocess.TimeoutExpired:
                self.fail("chromium travou (timeout 60s)")
            self.assertEqual(r.returncode, 0, "chromium saiu %s: %s" % (r.returncode, (r.stderr or "")[-2000:]))
            m = re.search(r'<pre id="autopilot-result">(.*?)</pre>', r.stdout, re.S)
            self.assertIsNotNone(m, "autopilot nao escreveu resultado no DOM isolado")
            obs = json.loads(html_mod.unescape(m.group(1)))
            self.assertEqual(obs.get("erro", ""), "", "erro no autopilot: %s" % obs.get("erro"))
            sys1 = (obs.get("sys1") or "").lower()
            self.assertIn("transmitida", sys1, "aviso canonico ausente no Blink: %r" % obs.get("sys1"))
            self.assertIn("salva", sys1)
            self.assertIn("hist\u00f3rico", sys1)
            self.assertEqual(obs.get("after1"), "oi-browser", "Blink: copia nao mantida")
            self.assertTrue(obs.get("btn1"), "Blink: botao deveria desabilitar")
            self.assertEqual(obs.get("chamadas1"), 1)
            self.assertEqual(obs.get("chamadas2"), 1, "Blink: 2o clique identico reenviou")
            self.assertEqual(obs.get("after2"), "oi-browser", "Blink: 2o clique perdeu a copia")
            self.assertTrue(obs.get("btn2"), "Blink: bloqueio nao persistiu")
            self.assertFalse(obs.get("btnEdit"), "Blink: editar deveria liberar")
            self.assertEqual(obs.get("chamadas3"), 2, "Blink: texto editado deveria enviar")


if __name__ == "__main__":
    unittest.main()
