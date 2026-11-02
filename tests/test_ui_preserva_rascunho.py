"""UI preserva rascunho digitado durante o envio (1.22, @designer).

Escopo: pagina.py apenas. Nao toca backend/build/manifesto/docs.
Contrato /api/enviar intacto (estado/transmitida/nivel; transmitida+
somente_memoria avisa+bobeia; nunca alega recebido/lido).

Bug (existia na 1.20): enviar A; digitar B antes da resposta; resposta de
A com sucesso APAGAVA B. Tambem: digitar durante o envio reabilitava o
botao (visual) embora `enviando` bloqueasse o submit (real). Upload:
trocar o arquivo durante o upload tinha a nova selecao apagada no fim.

Correcao: snapshot do envio (txt/para/arquivo); limpa cada campo somente
se o valor atual ainda for o enviado; `atualizarBloqueio()` mantem o
botao desabilitado enquanto `enviando`; sem reenvio automatico.

Harness: resposta controladamente atrasada (stub com resolver manual) em
DOM simulado (node) + Chromium headless isolado (perfil tmp) com
interacao real. Tmp/sinteticos/loopback/NO_BROADCAST; exits verdadeiros.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pagina
import senderme as sm
from suporte import CasoIsolado, definir_eu

os.environ["SENDERME_NO_BROADCAST"] = "1"

NODE_OK = shutil.which("node") is not None
CHROME = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")


def extrair_js(html=None):
    src = html if html is not None else pagina.PAGINA
    m = re.search(r"<script[^>]*>(.*?)</script>", src, re.S | re.I)
    assert m, "sem <script>"
    return m.group(1)


def fatiar(js):
    ini_login = js.index("async function login(){")
    fim_login = js.index("async function trocarNick(){")
    ini_submit = js.index('document.getElementById("form").addEventListener("submit"')
    fim_submit = js.index('document.getElementById("texto").addEventListener("keydown"')
    return js[ini_login:fim_login], js[ini_submit:fim_submit]


def rodar_node(prefixo, login, submit, sufixo, timeout=15):
    with tempfile.TemporaryDirectory(prefix="sm-ui122-") as td:
        p = Path(td) / "sonda.js"
        p.write_text(prefixo + login + submit + sufixo, encoding="utf-8")
        r = subprocess.run(["node", str(p)], capture_output=True, text=True, timeout=timeout)
        return r


PREFIXO_TEXTO = """let handler=null; let enviando=false; let estadoChamado=false; let alerts=[]; let pollChamado=false; let ouvintes={};
let _resolveApi=null; let chamadas=0;
const nodes={nick:{value:"alice"},loginerr:{textContent:""},contador:{textContent:"0/2000"},"arq-nome":{textContent:""},form:{addEventListener:(t,f)=>{if(t==="submit")handler=f;}},arq:{files:[],value:"",addEventListener:(t,f)=>{ouvintes["arq:"+t]=f;}},para:{value:"",addEventListener:(t,f)=>{ouvintes["para:"+t]=f;}},texto:{value:"",addEventListener:(t,f)=>{ouvintes["texto:"+t]=f;}},sys:{textContent:""},btnEnviar:{disabled:false,textContent:"Enviar",setAttribute(){},removeAttribute(){}}};
const document={getElementById:(id)=>nodes[id]||{textContent:"",value:"",style:{},addEventListener(){}}};
function poll(){pollChamado=true;}
function alert(x){alerts.push(String(x));}
function digitar(id,v){nodes[id].value=v; const f=ouvintes[id+":input"]; if(f)f({target:nodes[id]});}
"""

PREFIXO_UPLOAD = """let handler=null; let enviando=false; let estadoChamado=false; let alerts=[]; let pollChamado=false; let ouvintes={};
let _resolveUp=null; let chamadasUp=0;
const nodes={nick:{value:"alice"},loginerr:{textContent:""},contador:{textContent:"0/2000"},"arq-nome":{textContent:""},form:{addEventListener:(t,f)=>{if(t==="submit")handler=f;}},arq:{files:[{name:"a.txt",size:100,lastModified:1}],value:"C:\\\\fakepath\\\\a.txt",addEventListener:(t,f)=>{ouvintes["arq:"+t]=f;}},para:{value:"",addEventListener:(t,f)=>{ouvintes["para:"+t]=f;}},texto:{value:"",addEventListener:(t,f)=>{ouvintes["texto:"+t]=f;}},sys:{textContent:""},btnEnviar:{disabled:false,textContent:"Enviar",setAttribute(){},removeAttribute(){}}};
const document={getElementById:(id)=>nodes[id]||{textContent:"",value:"",style:{},addEventListener(){}}};
function poll(){pollChamado=true;}
function alert(x){alerts.push(String(x));}
function digitar(id,v){nodes[id].value=v; const f=ouvintes[id+":input"]; if(f)f({target:nodes[id]});}
class FormData{constructor(){this.d={}} append(k,v){this.d[k]=v}}
"""


@unittest.skipUnless(NODE_OK, "sem node no PATH")
class JsServidoValido122(unittest.TestCase):
    def test_node_check_js_local(self):
        js = extrair_js()
        with tempfile.TemporaryDirectory(prefix="sm-122-js-") as td:
            p = Path(td) / "pagina.js"
            p.write_text(js, encoding="utf-8")
            r = subprocess.run(["node", "--check", str(p)], capture_output=True, text=True, timeout=15)
            self.assertEqual(r.returncode, 0, "node --check: %s" % (r.stderr or r.stdout))

    def test_node_check_js_servido_via_http_real(self):
        definir_eu("alice")
        # Loopback efemero, sem broadcast; serve a pagina real de producao.
        import senderme_app.http as H  # noqa: F401 (garante Handler atual)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), sm.Handler)
        porta = srv.server_address[1]
        fio = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        fio.start()
        self.addCleanup(srv.shutdown)
        self.addCleanup(srv.server_close)
        with urllib.request.urlopen("http://127.0.0.1:%d/" % porta, timeout=10) as rh:
            html = rh.read().decode("utf-8")
        js = extrair_js(html)
        with tempfile.TemporaryDirectory(prefix="sm-122-http-") as td:
            p = Path(td) / "servido.js"
            p.write_text(js, encoding="utf-8")
            r = subprocess.run(["node", "--check", str(p)], capture_output=True, text=True, timeout=15)
            self.assertEqual(r.returncode, 0, "node --check servido: %s" % (r.stderr or r.stdout))


@unittest.skipUnless(NODE_OK, "sem node no PATH")
class PreservaRascunhoTexto(unittest.TestCase):
    """Resposta atrasada de proposito: B digitado durante o envio de A."""

    def _fluxo(self, resposta_js, texto_a="A", para_a="", texto_b=None, para_b=None):
        js = extrair_js()
        login, submit = fatiar(js)
        api = ('async function api(p,o){ if(p==="/api/enviar"){chamadas++;'
               ' return new Promise(res=>{ _resolveApi=()=>res(%s); }); }'
               ' return {ok:true}; }\nfunction estado(){}\n' % resposta_js)
        # edicoes durante a espera (None = nao mexe)
        passos = []
        if texto_b is not None:
            passos.append('digitar("texto",%s);' % json.dumps(texto_b))
        if para_b is not None:
            passos.append('nodes.para.value=%s; const _fp=ouvintes["para:input"]; if(_fp)_fp({});' % json.dumps(para_b))
        edicao = " ".join(passos)
        sufixo = ('(async()=>{ nodes.texto.value=%s; nodes.para.value=%s;'
                   ' let p=handler({preventDefault(){}});'
                   ' await new Promise(r=>setTimeout(r,50));'
                   ' const btnDurante=nodes.btnEnviar.disabled;'
                   ' %s'
                   ' const btnAposDigitar=nodes.btnEnviar.disabled;'
                   ' let p2=handler({preventDefault(){}});'
                   ' await new Promise(r=>setTimeout(r,20));'
                   ' const chamadasDurante=chamadas;'
                   ' _resolveApi(); await p; await p2;'
                   ' await new Promise(r=>setTimeout(r,20));'
                   ' console.log(JSON.stringify({after:nodes.texto.value,paraDepois:nodes.para.value,'
                   ' sys:nodes.sys.textContent,btnDurante,btnAposDigitar,'
                   ' btnDepois:nodes.btnEnviar.disabled,chamadas,chamadasDurante,contador:nodes.contador.textContent}));'
                   ' })().catch(e=>{console.error(String(e&&e.stack||e));process.exitCode=1;});'
                   % (json.dumps(texto_a), json.dumps(para_a), edicao))
        r = rodar_node(PREFIXO_TEXTO + api, login, submit, sufixo)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_publica_sucesso_preserva_b(self):
        obs = self._fluxo('{ok:true,msg:"",resposta:"",estado:"entregue",transmitida:true,nivel:"local",confirmado:false,peers:0}',
                          texto_a="A", para_a="", texto_b="B")
        self.assertEqual(obs["after"], "B", "sucesso de A apagou B (perda nao recuperavel)")
        self.assertIn("publicada localmente", obs["sys"].lower())
        self.assertEqual(obs["chamadas"], 1, "nao pode reenviar sozinho (duplo envio)")
        self.assertEqual(obs["chamadasDurante"], 1, "submit durante enviando nao pode chamar API")
        self.assertEqual(obs["contador"], "1/2000", "contador deve refletir B, nao zero")

    def test_publica_sucesso_sem_edicao_limpa(self):
        obs = self._fluxo('{ok:true,msg:"",resposta:"",estado:"entregue",transmitida:true,nivel:"local",confirmado:false,peers:0}',
                          texto_a="A", para_a="")
        self.assertEqual(obs["after"], "", "sem edicao, sucesso deve limpar (evitar duplicata)")
        self.assertFalse(obs["btnDepois"], "botao habilitado apos sucesso normal")

    def test_dm_sucesso_preserva_b(self):
        obs = self._fluxo('{ok:true,msg:"",resposta:"",estado:"entregue",transmitida:true,nivel:"socket",confirmado:false,peers:1}',
                          texto_a="segredo-A", para_a="@bob", texto_b="segredo-B")
        self.assertEqual(obs["after"], "segredo-B", "DM: sucesso de A apagou B")
        self.assertIn("sem confirma", obs["sys"].lower())
        self.assertEqual(obs["chamadas"], 1)

    def test_dm_barra_preserva_b(self):
        obs = self._fluxo('{ok:true,msg:"",resposta:"",estado:"entregue",transmitida:true,nivel:"socket",confirmado:false,peers:1}',
                          texto_a="/dm @bob A", para_a="", texto_b="/dm @bob B")
        self.assertEqual(obs["after"], "/dm @bob B", "/dm: sucesso apagou edicao")

    def test_troca_destino_tambem_preserva(self):
        obs = self._fluxo('{ok:true,msg:"",resposta:"",estado:"entregue",transmitida:true,nivel:"local",confirmado:false,peers:0}',
                          texto_a="A", para_a="", texto_b="A", para_b="@alice")
        # texto igual mas destino mudou: usuario prepara proximo envio, nao apaga
        self.assertEqual(obs["after"], "A")
        self.assertEqual(obs["paraDepois"], "@alice")

    def test_falha_preserva_b(self):
        obs = self._fluxo('{ok:false,msg:"X",resposta:"Nao encontrei \'@fulano\'.",estado:"erro"}',
                          texto_a="A", para_a="@fulano", texto_b="B")
        self.assertEqual(obs["after"], "B", "falha deve manter o texto atual (B), nao A")
        self.assertEqual(obs["chamadas"], 1)

    def test_somente_memoria_transmitida_preserva_b_sem_bloquear(self):
        obs = self._fluxo('{ok:true,resposta:"Enviada (aviso: nao salvou).",estado:"somente_memoria",transmitida:true}',
                          texto_a="A", para_a="@bob", texto_b="B")
        self.assertEqual(obs["after"], "B")
        self.assertFalse(obs["btnDepois"], "B != A: nao pode bloquear o proximo envio")

    def test_somente_memoria_sem_edicao_mantem_e_bloqueia(self):
        obs = self._fluxo('{ok:true,resposta:"Enviada (aviso: nao salvou).",estado:"somente_memoria",transmitida:true}',
                          texto_a="oi", para_a="@bob")
        self.assertEqual(obs["after"], "oi", "copia recuperavel perdida")
        self.assertTrue(obs["btnDepois"], "texto identico deve bloquear reenvio")

    def test_botao_fica_desabilitado_ao_digitar_durante(self):
        obs = self._fluxo('{ok:true,msg:"",resposta:"",estado:"entregue",transmitida:true,nivel:"local",confirmado:false,peers:0}',
                          texto_a="A", para_a="", texto_b="B")
        self.assertTrue(obs["btnDurante"], "botao deveria desabilitar no inicio do envio")
        self.assertTrue(obs["btnAposDigitar"], "digitar durante nao pode reabilitar (visual != real)")
        self.assertFalse(obs["btnDepois"], "apos resposta ok, botao volta a habilitar")


@unittest.skipUnless(NODE_OK, "sem node no PATH")
class PreservaAnexo(unittest.TestCase):
    def _fluxo_up(self, ok=True, trocar=True, legenda_nova="legenda-B", falha=False):
        js = extrair_js()
        login, submit = fatiar(js)
        resp = '{ok:false,msg:"disco cheio"}' if falha else ('{ok:true,msg:"up ok"}' if ok else '{ok:false,msg:"x"}')
        api = 'async function api(p,o){ return {ok:true}; }\nfunction estado(){}\n'
        api += ('async function fetch(u,o){ chamadasUp++;'
                ' return new Promise(res=>{ _resolveUp=()=>res({json:async()=>(' + resp + ')}); }); }\n')
        troca = ""
        if trocar:
            troca = ('nodes.arq.files=[{name:"b.txt",size:200,lastModified:2}];'
                     ' nodes.arq.value="C:\\\\fakepath\\\\b.txt";'
                     ' digitar("texto",%s);' % json.dumps(legenda_nova))
        sufixo = ('(async()=>{ nodes.texto.value="legenda-A"; nodes.para.value="";'
                   ' let p=handler({preventDefault(){}});'
                   ' await new Promise(r=>setTimeout(r,50));'
                   ' const btnDurante=nodes.btnEnviar.disabled;'
                   ' %s'
                   ' const btnApos=nodes.btnEnviar.disabled;'
                   ' _resolveUp(); await p;'
                   ' await new Promise(r=>setTimeout(r,20));'
                   ' console.log(JSON.stringify({texto:nodes.texto.value,arqValue:nodes.arq.value,'
                   ' arqNome:(nodes.arq.files[0]||{}).name||"",sys:nodes.sys.textContent,'
                   ' btnDurante,btnApos,btnDepois:nodes.btnEnviar.disabled,chamadasUp}));'
                   ' })().catch(e=>{console.error(String(e&&e.stack||e));process.exitCode=1;});' % troca)
        r = rodar_node(PREFIXO_UPLOAD + api, login, submit, sufixo)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_upload_sucesso_preserva_nova_selecao(self):
        obs = self._fluxo_up(ok=True, trocar=True)
        self.assertEqual(obs["texto"], "legenda-B", "legenda nova apagada pelo fim do upload anterior")
        self.assertIn("b.txt", obs["arqValue"] + obs["arqNome"], "nova selecao apagada: %r" % obs)
        self.assertTrue(obs["btnDurante"] and obs["btnApos"], "botao deve ficar desabilitado durante upload")
        self.assertEqual(obs["chamadasUp"], 1)

    def test_upload_sucesso_sem_troca_limpa(self):
        obs = self._fluxo_up(ok=True, trocar=False)
        self.assertEqual(obs["texto"], "", "sem troca, upload ok deve limpar legenda")
        self.assertEqual(obs["arqValue"], "", "sem troca, upload ok deve limpar selecao")

    def test_upload_falha_preserva(self):
        obs = self._fluxo_up(falha=True, trocar=True)
        self.assertEqual(obs["texto"], "legenda-B")
        self.assertIn("b.txt", obs["arqValue"] + obs["arqNome"])


@unittest.skipUnless(CHROME, "sem chromium no PATH")
class NavegadorPreserva(CasoIsolado):
    """Blink isolado: digitacao real durante envio atrasado, perfil tmp."""

    def _servir(self):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), sm.Handler)
        porta = srv.server_address[1]
        fio = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        fio.start()
        self.addCleanup(srv.shutdown)
        self.addCleanup(srv.server_close)
        return porta

    def _rodar(self, sonda_js, budget="9000"):
        import html as html_mod
        definir_eu("alice")
        autopilot = "<script>(async()=>{const out={erro:\"\"};try{%s}catch(e){out.erro=String(e&&e.stack||e)}" % sonda_js
        autopilot += 'const pre=document.createElement("pre");pre.id="r122";pre.textContent=JSON.stringify(out);document.body.appendChild(pre);})();</script>'
        import senderme_app.http as H
        orig = H.PAGINA
        H.PAGINA = pagina.PAGINA.replace("</body>", autopilot + "</body>")
        self.addCleanup(setattr, H, "PAGINA", orig)
        porta = self._servir()
        with tempfile.TemporaryDirectory(prefix="sm-122-chrome-") as prof:
            cmd = [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
                   "--user-data-dir=%s" % prof, "--virtual-time-budget=%s" % budget,
                   "--dump-dom", "http://127.0.0.1:%d/" % porta]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            except subprocess.TimeoutExpired:
                self.fail("chromium travou (timeout 60s)")
            self.assertEqual(r.returncode, 0, "chromium %s: %s" % (r.returncode, (r.stderr or "")[-2000:]))
            m = re.search(r'<pre id="r122">(.*?)</pre>', r.stdout, re.S)
            self.assertIsNotNone(m, "autopilot nao escreveu no DOM isolado")
            return json.loads(html_mod.unescape(m.group(1)))

    def test_blink_texto_preserva_e_botao_coerente(self):
        sonda = """
 l=document.getElementById("texto"),pa=document.getElementById("para"),bt=document.getElementById("btnEnviar");
 const _api=api; let n=0; let _res=null;
 api=async function(p,o){ if(p==="/api/enviar"){n++; return new Promise(r=>{_res=()=>r({ok:true,msg:"",resposta:"",estado:"entregue",transmitida:true,nivel:"local",confirmado:false,peers:0});});} return _api(p,o); };
 l.value="A"; pa.value="";
 document.getElementById("form").requestSubmit();
 await new Promise(r=>setTimeout(r,400));
 out.btnDurante=bt.disabled;
 l.value="B"; l.dispatchEvent(new Event("input",{bubbles:true}));
 out.btnAposDigitar=bt.disabled;
 let p2=(function(){let c=n; document.getElementById("form").requestSubmit(); return c;})();
 out.chamadasDurante=n;
 _res();
 await new Promise(r=>setTimeout(r,400));
 out.after=l.value; out.btnDepois=bt.disabled; out.sys=document.getElementById("sys").textContent||"";
 out.chamadas=n; out.segundoSubmitIgnorado=(p2===1&&n===1);
"""
        obs = self._rodar(sonda)
        self.assertEqual(obs.get("erro", ""), "", obs.get("erro"))
        self.assertEqual(obs.get("after"), "B", "Blink apagou B ao fim de A: %r" % obs)
        self.assertTrue(obs.get("btnDurante"), "botao devia desabilitar no envio: %r" % obs)
        self.assertTrue(obs.get("btnAposDigitar"), "digitar reabilitou no Blink (visual != real): %r" % obs)
        self.assertFalse(obs.get("btnDepois"), "botao devia reabilitar apos ok: %r" % obs)
        self.assertEqual(obs.get("chamadas"), 1, "duplo envio no Blink: %r" % obs)
        self.assertIn("publicada localmente", (obs.get("sys") or "").lower())

    def test_blink_upload_preserva_nova_selecao(self):
        sonda = """
 l=document.getElementById("texto"),aq=document.getElementById("arq"),bt=document.getElementById("btnEnviar");
 let _res=null;
 const _fetch=window.fetch.bind(window);
 window.fetch=async function(u,o){ if((u||"").indexOf("/api/upload")>=0){ return new Promise(r=>{_res=()=>r({ok:true,json:async()=>({ok:true,msg:"up ok"})});}); } return _fetch(u,o); };
 let dt1=new DataTransfer(); dt1.items.add(new File(["a"],"a.txt",{type:"text/plain"})); aq.files=dt1.files;
 l.value="legenda-A";
 document.getElementById("form").requestSubmit();
 await new Promise(r=>setTimeout(r,400));
 out.btnDurante=bt.disabled;
 let dt2=new DataTransfer(); dt2.items.add(new File(["bb"],"b.txt",{type:"text/plain"})); aq.files=dt2.files;
 l.value="legenda-B"; l.dispatchEvent(new Event("input",{bubbles:true}));
 out.btnApos=bt.disabled;
 _res();
 await new Promise(r=>setTimeout(r,600));
 out.texto=l.value; out.arqNome=(aq.files&&aq.files[0]&&aq.files[0].name)||""; out.btnDepois=bt.disabled;
"""
        obs = self._rodar(sonda)
        self.assertEqual(obs.get("erro", ""), "", obs.get("erro"))
        self.assertEqual(obs.get("texto"), "legenda-B", "Blink apagou legenda nova: %r" % obs)
        self.assertEqual(obs.get("arqNome"), "b.txt", "Blink apagou nova selecao: %r" % obs)
        self.assertTrue(obs.get("btnDurante") and obs.get("btnApos"), "botao incoerente no upload: %r" % obs)


if __name__ == "__main__":
    unittest.main()
