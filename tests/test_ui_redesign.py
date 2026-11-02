"""Redesign UI SenderMe (@designer): hierarquia, a11y, responsivo, estados.

Escopo: pagina.py apenas. Nao toca backend. Contrato /api/enviar preservado
(entregue/guardada limpam; somente_memoria/erro preservam; transmitida+
somente_memoria avisa+bobeia; nunca alega recebido/lido).
"""
import json
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
import urllib.request

import pagina
import senderme as sm
from suporte import CasoIsolado, definir_eu

NODE_OK = shutil.which("node") is not None
CHROME = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")


def extrair_js(html=None):
    src = html if html is not None else pagina.PAGINA
    m = re.search(r"<script[^>]*>(.*?)</script>", src, re.S | re.I)
    assert m, "sem <script>"
    return m.group(1)


def extrair_css(html=None):
    src = html if html is not None else pagina.PAGINA
    m = re.search(r"<style[^>]*>(.*?)</style>", src, re.S | re.I)
    assert m, "sem <style>"
    return m.group(1)


class GanchosPreservados(unittest.TestCase):
    """Contrato antigo continua servido."""

    def test_ids_e_rotas_antigas_presentes(self):
        for gancho in ('id="sys"', 'id="texto"', 'id="loginerr"', 'id="form"',
                       "/api/login", "/api/enviar", 'id="btnEnviar"',
                       "AVISO_NAO_SALVO", "atualizarBloqueio",
                       "ultimoNaoSalvo", "transmitida",
                       'id="msgs"', 'id="presentes"', 'id="npres"',
                       'id="nick"', 'id="app"', 'id="login"',
                       'id="para"', 'id="arq"', 'id="eu"', 'id="status"',
                       'id="upd"', 'id="pane-chat"', 'id="pane-configs"',
                       'id="tab-chat"', 'id="tab-configs"'):
            self.assertIn(gancho, pagina.PAGINA, "gancho sumiu: %s" % gancho)

    def test_fatiar_legado_ainda_funciona(self):
        js = extrair_js()
        # mesmos marcadores que test_pagina_avisos usa
        self.assertIn("async function login(){", js)
        self.assertIn("async function trocarNick(){", js)
        self.assertIn('document.getElementById("form").addEventListener("submit"', js)
        self.assertIn('document.getElementById("texto").addEventListener("keydown"', js)
        ini_login = js.index("async function login(){")
        fim_login = js.index("async function trocarNick(){")
        ini_submit = js.index('document.getElementById("form").addEventListener("submit"')
        fim_submit = js.index('document.getElementById("texto").addEventListener("keydown"')
        self.assertLess(ini_login, fim_login)
        self.assertLess(ini_submit, fim_submit)

    def test_sem_cdn_nem_fonte_remota(self):
        html = pagina.PAGINA.lower()
        self.assertNotIn("https://cdn", html)
        self.assertNotIn("fonts.googleapis", html)
        self.assertNotIn("fonts.gstatic", html)
        self.assertIn("/bootstrap.min.css", pagina.PAGINA)


class EstruturaAcessivel(unittest.TestCase):
    def test_labels_para_campos(self):
        for fid in ("texto", "arq", "para", "nick", "novonick"):
            self.assertRegex(pagina.PAGINA, r'<label[^>]*for="%s"' % fid,
                             "sem <label for=%s>" % fid)

    def test_regioes_live_e_papeis(self):
        self.assertRegex(pagina.PAGINA, r'id="msgs"[^>]*role="log"')
        self.assertRegex(pagina.PAGINA, r'id="sys"[^>]*role="status"')
        self.assertIn('aria-live="polite"', pagina.PAGINA)
        self.assertRegex(pagina.PAGINA, r'id="loginerr"[^>]*role="alert"')

    def test_abas_com_papel_e_selecao(self):
        self.assertIn('role="tablist"', pagina.PAGINA)
        self.assertIn('role="tab"', pagina.PAGINA)
        self.assertIn("aria-selected", pagina.PAGINA)
        self.assertIn('role="tabpanel"', pagina.PAGINA)

    def test_skip_link_e_login_form(self):
        self.assertRegex(pagina.PAGINA, r'<a[^>]*href="#msgs"[^>]*>.*[Pp]ular.*</a>',
                         "sem skip link para #msgs")
        self.assertRegex(pagina.PAGINA, r'<form[^>]*id="loginform"',
                         "login deveria ser <form> p/ Enter funcionar")

    def test_textarea_limite_e_descricao(self):
        self.assertRegex(pagina.PAGINA, r'<textarea[^>]*id="texto"[^>]*maxlength="2000"',
                         "sem maxlength=2000 no #texto")
        self.assertRegex(pagina.PAGINA, r'<textarea[^>]*aria-describedby',
                         "sem aria-describedby no #texto")

    def test_imagem_anexo_tem_alt(self):
        js = extrair_js()
        self.assertIn("alt=", js, "preview de imagem sem alt")


class HierarquiaVisual(unittest.TestCase):
    def test_tokens_e_foco_visivel(self):
        css = extrair_css()
        self.assertIn("--sm-", css, "sem tokens --sm-*")
        self.assertIn(":focus-visible", css, "sem estilo de foco visivel")
        self.assertIn(":hover", css, "sem estado hover")
        self.assertIn(":disabled", css, "sem estado desabilitado")

    def test_responsivo_e_reducao_movimento(self):
        css = extrair_css()
        self.assertIn("@media", css, "sem adaptacao a janelas")
        self.assertIn("prefers-reduced-motion", css, "sem respeito a reducao de movimento")

    def test_textos_longos_e_listas(self):
        css = extrair_css().lower()
        self.assertIn("overflow-wrap", css, "sem quebra p/ textos longos")
        self.assertIn("text-overflow", css, "sem ellipsis p/ apelidos longos")
        self.assertIn("overflow-y", css, "sem rolagem contida p/ listas")

    def test_contraste_hora_sem_cinza_claro(self):
        css = extrair_css()
        self.assertNotIn("#868e96", css, "cinza #868e96 reprova contraste no balao")
        # hora e sys precisam existir com cor mais escura
        self.assertIn(".hora", css)
        self.assertIn(".sys", css)

    def test_numeros_tabulares_e_transicao_escopo(self):
        css = extrair_css().lower()
        self.assertIn("tabular-nums", css, "sem font-variant-numeric p/ horarios/contadores")
        self.assertNotIn("transition: all", css, "transition: all mascara estados")


@unittest.skipUnless(NODE_OK, "sem node no PATH")
class JsServidoValido(unittest.TestCase):
    def test_node_check_no_js_servido(self):
        js = extrair_js()
        with tempfile.TemporaryDirectory(prefix="sm-redesign-js-") as td:
            p = Path(td) / "pagina.js"
            p.write_text(js, encoding="utf-8")
            r = subprocess.run(["node", "--check", str(p)], capture_output=True,
                               text=True, timeout=15)
            self.assertEqual(r.returncode, 0, "node --check: %s" % (r.stderr or r.stdout))


class ContratoHttpRedesign(CasoIsolado):
    def _subir(self):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), sm.Handler)
        porta = srv.server_address[1]
        fio = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        fio.start()
        self.addCleanup(srv.shutdown)
        self.addCleanup(srv.server_close)
        return porta

    def test_js_servido_via_http_passa_node_check(self):
        if not NODE_OK:
            self.skipTest("sem node no PATH")
        definir_eu("alice")
        porta = self._subir()
        with urllib.request.urlopen("http://127.0.0.1:%d/" % porta, timeout=10) as r:
            html = r.read().decode("utf-8")
        js = extrair_js(html)
        with tempfile.TemporaryDirectory(prefix="sm-redesign-http-") as td:
            p = Path(td) / "servido.js"
            p.write_text(js, encoding="utf-8")
            r = subprocess.run(["node", "--check", str(p)], capture_output=True,
                               text=True, timeout=15)
            self.assertEqual(r.returncode, 0, "node --check servido: %s" % (r.stderr or r.stdout))


@unittest.skipUnless(CHROME, "sem chromium no PATH")
class NavegadorResponsivo(CasoIsolado):
    def _servir(self):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), sm.Handler)
        porta = srv.server_address[1]
        fio = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        fio.start()
        self.addCleanup(srv.shutdown)
        self.addCleanup(srv.server_close)
        return porta

    def _autopilot(self, largura, altura):
        import html as html_mod
        definir_eu("alice")
        sonda = """<script>
(async()=>{
 const out={erro:"",largura:window.innerWidth,overflowX:false,loginVisivel:false,appVisivel:false,
  textoFocavel:false,enterEnvia:false,tabAlcancavel:false,sysLive:"",msgsLive:""};
 try{
  out.loginVisivel=!!document.getElementById("login")&&getComputedStyle(document.getElementById("login")).display!=="none";
  const msgs=document.getElementById("msgs");
  out.msgsLive=msgs.getAttribute("role")+"|"+msgs.getAttribute("aria-live");
  const sys=document.getElementById("sys");
  out.sysLive=sys.getAttribute("role")+"|"+sys.getAttribute("aria-live");
  out.overflowX=document.documentElement.scrollWidth>document.documentElement.clientWidth+1;
  document.getElementById("nick").value="visitante";
  await login();
  await new Promise(r=>setTimeout(r,800));
  out.appVisivel=document.getElementById("app").style.display!=="none";
  const tx=document.getElementById("texto");
  tx.focus(); out.textoFocavel=document.activeElement===tx;
  out.tabAlcancavel=tx.tabIndex>=0;
  // Enter sem Shift dispara submit (contrato multilinha preservado no handler)
  let enviou=false;
  document.getElementById("form").addEventListener("submit",e=>{e.preventDefault();enviou=true;},{once:true});
  tx.value="oi-teclado";
  tx.dispatchEvent(new KeyboardEvent("keydown",{key:"Enter",bubbles:true,cancelable:true}));
  await new Promise(r=>setTimeout(r,300));
  out.enterEnvia=enviou;
  out.overflowX=document.documentElement.scrollWidth>document.documentElement.clientWidth+1;
 }catch(e){out.erro=String(e&&e.stack||e)}
 const pre=document.createElement("pre");pre.id="redesign-result";pre.textContent=JSON.stringify(out);
 document.body.appendChild(pre);
})();
</script>"""
        import senderme_app.http as H
        orig = H.PAGINA
        H.PAGINA = pagina.PAGINA.replace("</body>", sonda + "</body>")
        self.addCleanup(setattr, H, "PAGINA", orig)
        porta = self._servir()
        with tempfile.TemporaryDirectory(prefix="sm-redesign-chrome-") as prof:
            cmd = [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
                   "--user-data-dir=%s" % prof,
                   "--window-size=%d,%d" % (largura, altura),
                   "--virtual-time-budget=4000",
                   "--dump-dom", "http://127.0.0.1:%d/" % porta]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
            except subprocess.TimeoutExpired:
                self.fail("chromium travou")
            self.assertEqual(r.returncode, 0, "chromium %s" % (r.stderr or "")[-2000:])
            m = re.search(r'<pre id="redesign-result">(.*?)</pre>', r.stdout, re.S)
            self.assertIsNotNone(m, "sonda nao escreveu no DOM")
            return json.loads(html_mod.unescape(m.group(1)))

    def test_janela_grande_sem_overflow_e_com_teclado(self):
        obs = self._autopilot(1280, 800)
        self.assertEqual(obs.get("erro", ""), "", obs.get("erro"))
        self.assertFalse(obs.get("overflowX"), "overflow horizontal em 1280px")
        self.assertTrue(obs.get("loginVisivel"), "login nao visivel antes do login")
        self.assertTrue(obs.get("appVisivel"), "app nao apareceu apos login")
        self.assertTrue(obs.get("textoFocavel"), "textarea nao focavel por teclado")
        self.assertTrue(obs.get("enterEnvia"), "Enter nao dispara envio")
        self.assertIn("log", (obs.get("msgsLive") or ""))
        self.assertIn("status", (obs.get("sysLive") or ""))

    def test_janela_estreita_sem_overflow(self):
        obs = self._autopilot(390, 844)
        self.assertEqual(obs.get("erro", ""), "", obs.get("erro"))
        self.assertFalse(obs.get("overflowX"), "overflow horizontal em 390px")
        self.assertTrue(obs.get("textoFocavel"), "textarea nao focavel em janela estreita")


class MidSeguro(unittest.TestCase):
    """pagina.py:261 — mid validado antes de ir p/ href/src via innerHTML."""

    def test_js_valida_mid_hex64_antes_do_href(self):
        js = extrair_js()
        self.assertIn("midOk", js, "sem validador midOk no JS servido")
        self.assertRegex(js, r"/\^\[0-9a-f\]\{64\}\$/",
                         "sem regex ^[0-9a-f]{64}$ no JS")
        self.assertIn("if(m.arq.pronto&&midOk(m.mid))", js,
                      "link de download sem guarda midOk")
        self.assertIn("if(m.arq.pronto&&midOk(m.mid)&&(nm", js,
                      "preview de imagem sem guarda midOk")

    @unittest.skipUnless(NODE_OK, "sem node no PATH")
    def test_mid_hostil_nao_injeta_e_valido_ainda_baixa(self):
        js = extrair_js()
        ini_esc = js.index("function esc(")
        ini_mid = js.index("function midOk(")
        ini_bolha = js.index("function bolha(m){")
        fim_bolha = js.index("function dmPara(")
        sonda = js[ini_esc:ini_mid] + js[ini_mid:ini_bolha] + js[ini_bolha:fim_bolha]
        sonda += """
const document={createElement:function(){return {className:"",innerHTML:""}}};
let hostil={tipo:"file",mid:'\\"><img src=x onerror=alert(1)>',arq:{pronto:true,nome:"a.png",tamanho:1024},hora:"h",nick:"n",txt:"t"};
let r1=bolha(hostil).innerHTML;
let ok1=r1.indexOf('<img src=x')<0 && r1.indexOf('onerror')<0 && r1.indexOf('/api/arquivo/'+hostil.mid)<0 && r1.indexOf('<a href')<0 && r1.indexOf('<img src')<0;
let valido="ab".repeat(32);
let bom={tipo:"file",mid:valido,arq:{pronto:true,nome:"a.png",tamanho:1024},hora:"h",nick:"n",txt:"t"};
let r2=bolha(bom).innerHTML;
let ok2=r2.indexOf('/api/arquivo/'+valido)>=0 && r2.indexOf('<a href')>=0 && r2.indexOf('<img src')>=0;
console.log(JSON.stringify({ok1:ok1,ok2:ok2,r1:r1.slice(0,500),r2:r2.slice(0,300)}));
"""
        with tempfile.TemporaryDirectory(prefix="sm-mid-") as td:
            p = Path(td) / "mid.js"
            p.write_text(sonda, encoding="utf-8")
            r = subprocess.run(["node", str(p)], capture_output=True,
                               text=True, timeout=15)
        self.assertEqual(r.returncode, 0, "node: %s" % (r.stderr or r.stdout))
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertTrue(out["ok1"], "mid hostil injetou HTML: %s" % out["r1"][:300])
        self.assertTrue(out["ok2"], "mid valido hex64 deixou de renderizar link/img")


if __name__ == "__main__":
    unittest.main()
