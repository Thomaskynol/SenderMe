"""Layout sem rolagem de pagina em notebook (@designer).

Escopo: pagina.py (CSS/layout/HTML estrutural) apenas. Nenhuma mudanca em
JS de comportamento, contratos, textos honestos ou matriz de estados.
Nao toca backend/build/docs/manifesto/dados/segredos.

Reclamacao: em janela comum de notebook a pagina inteira rola e o campo
de envio sai da vista. Causa provavel: paddings/margens/alturas fixas +
falta de shell em altura total (100dvh com main rolando por dentro).

Contrato deste teste (TDD: falha antes, passa depois):
- 1366x768 e 1280x720: composer visivel sem rolar a pagina
  (pageScrollY==0), #msgs com rolagem interna.
- Estreita (~390), pouca altura (~400) e zoom 200%: rolagem da pagina
  permitida, nada cortado/inacessivel.
- 200 msgs + 40 pessoas: rolam as areas internas, envio funciona,
  rascunho preservado em envio lento.
- Teclado/anexo/DM/aviso intactos; node --check no JS servido via HTTP.

Harness: tmp/sinteticos/loopback/SENDERME_NO_BROADCAST=1, Chromium
headless com perfil-tmp isolado. Exits verdadeiros.
"""
import html as html_mod
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
CHROME = (shutil.which("chromium") or shutil.which("chromium-browser")
          or shutil.which("google-chrome"))


def extrair_css(html=None):
    src = html if html is not None else pagina.PAGINA
    m = re.search(r"<style[^>]*>(.*?)</style>", src, re.S | re.I)
    assert m, "sem <style>"
    return m.group(1)


def extrair_js(html=None):
    src = html if html is not None else pagina.PAGINA
    m = re.search(r"<script[^>]*>(.*?)</script>", src, re.S | re.I)
    assert m, "sem <script>"
    return m.group(1)


class ShellCss(unittest.TestCase):
    """Sinais estaticos do shell em altura total (sem truque)."""

    def test_shell_altura_total_com_rolagem_interna(self):
        css = extrair_css()
        self.assertIn("100dvh", css, "sem shell 100dvh")
        self.assertRegex(css, r"overflow-y\s*:\s*auto",
                         "sem overflow-y:auto interno")
        # #msgs participa do flex do shell (nao altura fixa sozinha)
        self.assertRegex(css, r"#msgs\s*\{[^}]*flex\s*:",
                         "#msgs fora do flex do shell")
        self.assertRegex(css, r"#presentes\s*\{[^}]*overflow-y\s*:\s*auto",
                         "#presentes sem rolagem propria")
        self.assertRegex(css, r"\.sm-compor\s*\{[^}]*flex\s*:\s*none",
                         "composer pode encolher/sumir no shell")

    def test_sem_truque_overflow_nem_reducao_fonte(self):
        css = extrair_css()
        baixo = css.lower()
        # overflow-x:hidden da base pode continuar; o truque proibido e
        # travar a rolagem vertical da pagina no root.
        self.assertNotRegex(
            baixo, r"(html|body)\s*\{[^}]*overflow-y\s*:\s*hidden",
            "overflow-y:hidden no root esconde conteudo (truque)")
        self.assertNotRegex(
            baixo, r"(html|body)\s*\{[^}]*overflow\s*:\s*hidden",
            "overflow:hidden no root corta acesso (truque)")
        # tokens, foco visivel e reduced-motion do redesign preservados
        self.assertIn("--sm-", css)
        self.assertIn(":focus-visible", css)
        self.assertIn("prefers-reduced-motion", css)

    def test_textarea_nao_estoura_o_shell(self):
        css = extrair_css()
        m = re.search(r"#texto\s*\{([^}]*)\}", css, re.S)
        self.assertIsNotNone(m, "sem regra #texto")
        bloco = m.group(1)
        alturas = [int(v) for v in re.findall(
            r"min-height\s*:\s*(\d+)\s*px", bloco)]
        self.assertTrue(alturas, "#texto sem min-height em px")
        self.assertLessEqual(max(alturas), 68,
                             "#texto alto demais p/ caber no shell")


@unittest.skipUnless(NODE_OK, "sem node no PATH")
class JsServidoValidoLayout(unittest.TestCase):
    def test_node_check_js_servido_via_http_real(self):
        definir_eu("alice")
        srv = ThreadingHTTPServer(("127.0.0.1", 0), sm.Handler)
        porta = srv.server_address[1]
        fio = threading.Thread(target=srv.serve_forever,
                               kwargs={"poll_interval": 0.01}, daemon=True)
        fio.start()
        self.addCleanup(srv.shutdown)
        self.addCleanup(srv.server_close)
        with urllib.request.urlopen("http://127.0.0.1:%d/" % porta,
                                    timeout=10) as rh:
            html = rh.read().decode("utf-8")
        js = extrair_js(html)
        with tempfile.TemporaryDirectory(prefix="sm-layout-http-") as td:
            p = Path(td) / "servido.js"
            p.write_text(js, encoding="utf-8")
            r = subprocess.run(["node", "--check", str(p)],
                               capture_output=True, text=True, timeout=15)
            self.assertEqual(r.returncode, 0,
                             "node --check servido: %s" % (r.stderr or r.stdout))


@unittest.skipUnless(CHROME, "sem chromium no PATH")
class LayoutNavegador(CasoIsolado):
    def _servir(self):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), sm.Handler)
        porta = srv.server_address[1]
        fio = threading.Thread(target=srv.serve_forever,
                               kwargs={"poll_interval": 0.01}, daemon=True)
        fio.start()
        self.addCleanup(srv.shutdown)
        self.addCleanup(srv.server_close)
        return porta

    def _rodar(self, sonda_js, largura, altura, budget="12000",
               escala=None):
        definir_eu("alice")
        autopilot = ("<script>(async()=>{const out={erro:\"\"};try{%s}"
                     % sonda_js)
        autopilot += ('catch(e){out.erro=String(e&&e.stack||e)}'
                      'const pre=document.createElement("pre");'
                      'pre.id="layout-result";'
                      'pre.textContent=JSON.stringify(out);'
                      'document.body.appendChild(pre);})();</script>')
        import senderme_app.http as H
        orig = H.PAGINA
        H.PAGINA = pagina.PAGINA.replace("</body>", autopilot + "</body>")
        self.addCleanup(setattr, H, "PAGINA", orig)
        porta = self._servir()
        with tempfile.TemporaryDirectory(prefix="sm-layout-chrome-") as prof:
            cmd = [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
                   "--user-data-dir=%s" % prof,
                   "--window-size=%d,%d" % (largura, altura),
                   "--virtual-time-budget=%s" % budget,
                   "--dump-dom", "http://127.0.0.1:%d/" % porta]
            if escala is not None:
                cmd.insert(4, "--force-device-scale-factor=%s" % escala)
            try:
                r = subprocess.run(cmd, capture_output=True, text=True,
                                   timeout=90)
            except subprocess.TimeoutExpired:
                self.fail("chromium travou (timeout 90s)")
            self.assertEqual(r.returncode, 0,
                             "chromium %s: %s" % (r.returncode,
                                                 (r.stderr or "")[-2000:]))
            m = re.search(r'<pre id="layout-result">(.*?)</pre>', r.stdout,
                          re.S)
            self.assertIsNotNone(m, "autopilot nao escreveu no DOM isolado")
            return json.loads(html_mod.unescape(m.group(1)))

    LOGIN = """
  document.getElementById("nick").value="visitante";
  await login();
  await new Promise(r=>setTimeout(r,900));
  out.appVisivel=document.getElementById("app").style.display!=="none";
"""

    MEDIR = """
  out.vw=window.innerWidth; out.vh=window.innerHeight;
  out.pageY=window.scrollY;
  const comp=document.querySelector(".sm-compor");
  const rc=comp.getBoundingClientRect();
  out.composerTop=rc.top; out.composerBottom=rc.bottom;
  out.composerVisivel=(rc.top>=0&&rc.bottom<=window.innerHeight);
  const msgs=document.getElementById("msgs");
  const cs=getComputedStyle(msgs);
  out.msgsOverflowY=cs.overflowY;
  out.msgsClient=msgs.clientHeight; out.msgsScroll=msgs.scrollHeight;
  out.msgsRolagemInterna=(msgs.scrollHeight>msgs.clientHeight+2)
    &&(cs.overflowY==="auto"||cs.overflowY==="scroll");
  out.bodyOverflowY=getComputedStyle(document.body).overflowY;
  out.htmlOverflowY=getComputedStyle(document.documentElement).overflowY;
  const pres=document.getElementById("presentes");
  const cp=getComputedStyle(pres);
  out.presentesOverflowY=cp.overflowY;
"""

    SEMEAR = """
  const caixa=document.getElementById("msgs");
  for(let i=0;i<200;i++){const d=document.createElement("div");d.className="msg";
    d.innerHTML='<div class="balao">m'+i+" "+"x".repeat(40)+"</div>";
    caixa.appendChild(d);}
  const ul=document.getElementById("presentes");
  for(let i=0;i<40;i++){const li=document.createElement("li");
    li.className="list-group-item";
    li.innerHTML='<span class="nick">pessoa-'+i+"</span>";ul.appendChild(li);}
  await new Promise(r=>setTimeout(r,400));
  out.msgsRolagemAposCarga=(caixa.scrollHeight>caixa.clientHeight+2);
  out.presentesClient=ul.clientHeight; out.presentesScroll=ul.scrollHeight;
  out.presentesRolagemInterna=(ul.scrollHeight>ul.clientHeight+2);
  const rc2=document.querySelector(".sm-compor").getBoundingClientRect();
  out.composerAposCarga=(rc2.top>=0&&rc2.bottom<=window.innerHeight);
  out.pageYAposCarga=window.scrollY;
"""

    def test_notebook_1366x768_composer_visivel_e_msgs_rola_dentro(self):
        sonda = (self.LOGIN + self.MEDIR + self.SEMEAR + """
  const tx=document.getElementById("texto");
  tx.value="ola-layout-1366";
  document.getElementById("form").requestSubmit();
  await new Promise(r=>setTimeout(r,900));
  out.textoApos=tx.value;
  out.sys=(document.getElementById("sys").textContent||"");
""")
        obs = self._rodar(sonda, 1366, 768)
        self.assertEqual(obs.get("erro", ""), "", obs.get("erro"))
        self.assertTrue(obs.get("appVisivel"), "app nao apareceu: %r" % obs)
        self.assertEqual(obs.get("pageY"), 0,
                         "pagina rolou em 1366x768 (composer fora da vista): %r" % obs)
        self.assertTrue(obs.get("composerVisivel"),
                        "composer fora da vista em 1366x768: %r" % obs)
        self.assertEqual(obs.get("msgsOverflowY"), "auto",
                         "#msgs sem overflow interno: %r" % obs)
        self.assertTrue(obs.get("msgsRolagemAposCarga"),
                        "#msgs nao rolou dentro com 200 msgs: %r" % obs)
        self.assertTrue(obs.get("composerAposCarga"),
                        "200 msgs empurraram o composer p/ fora: %r" % obs)
        self.assertEqual(obs.get("pageYAposCarga"), 0,
                         "carga rolou a pagina (deveria rolar dentro): %r" % obs)
        self.assertTrue(obs.get("presentesRolagemInterna"),
                        "#presentes sem rolagem propria com 40 pessoas: %r" % obs)
        self.assertEqual(obs.get("textoApos"), "",
                         "envio real nao limpou apos sucesso: %r" % obs)

    def test_notebook_1280x720_composer_visivel(self):
        sonda = self.LOGIN + self.MEDIR
        obs = self._rodar(sonda, 1280, 720)
        self.assertEqual(obs.get("erro", ""), "", obs.get("erro"))
        self.assertEqual(obs.get("pageY"), 0,
                         "pagina rolou em 1280x720: %r" % obs)
        self.assertTrue(obs.get("composerVisivel"),
                        "composer fora da vista em 1280x720: %r" % obs)
        self.assertEqual(obs.get("msgsOverflowY"), "auto",
                         "#msgs sem overflow interno em 1280x720: %r" % obs)

    def _acessivel(self, largura, altura, escala=None, rotulo=""):
        sonda = self.LOGIN + """
  const sels=["#texto","#btnEnviar","#arq","#para","#tab-chat","#tab-configs",
    "#presentes","#msgs","#eu","#status"];
  out.itens=[];
  for(const sel of sels){
    const el=document.querySelector(sel);
    if(!el){out.itens.push({sel,ok:false,motivo:"ausente"});continue}
    try{el.scrollIntoView({block:"nearest"});}catch(e){}
    await new Promise(r=>setTimeout(r,120));
    const r2=el.getBoundingClientRect();
    const cs=getComputedStyle(el);
    const ok=r2.width>0&&r2.height>0&&cs.display!=="none"
      &&cs.visibility!=="hidden"&&r2.right>0&&r2.left<window.innerWidth;
    out.itens.push({sel,ok,top:Math.round(r2.top),bottom:Math.round(r2.bottom)});
  }
  out.rolagemPaginaPermitida=(document.documentElement.scrollHeight
    >=document.documentElement.clientHeight);
  out.bodyOverflowY=getComputedStyle(document.body).overflowY;
  out.htmlOverflowY=getComputedStyle(document.documentElement).overflowY;
  out.vw=window.innerWidth; out.vh=window.innerHeight;
"""
        obs = self._rodar(sonda, largura, altura, escala=escala)
        self.assertEqual(obs.get("erro", ""), "", obs.get("erro"))
        ruins = [i for i in obs.get("itens", []) if not i.get("ok")]
        self.assertEqual(ruins, [], "inacessivel %s: %r" % (rotulo, obs))
        self.assertNotEqual(obs.get("bodyOverflowY"), "hidden",
                            "pagina travada %s: %r" % (rotulo, obs))
        self.assertNotEqual(obs.get("htmlOverflowY"), "hidden",
                            "pagina travada %s: %r" % (rotulo, obs))
        return obs

    def test_estreita_390_tudo_acessivel(self):
        self._acessivel(390, 844, rotulo="390px")

    def test_pouca_altura_400_tudo_acessivel(self):
        self._acessivel(1280, 400, rotulo="h400")

    def test_zoom_200_tudo_acessivel(self):
        self._acessivel(1366, 768, escala="2", rotulo="zoom200")

    def test_rascunho_preservado_em_envio_lento_com_carga(self):
        sonda = self.LOGIN + self.SEMEAR + """
  const tx=document.getElementById("texto"),pa=document.getElementById("para"),
    bt=document.getElementById("btnEnviar");
  const _api=api; let n=0; let _res=null;
  api=async function(p,o){ if(p==="/api/enviar"){n++;
    return new Promise(r=>{_res=()=>r({ok:true,msg:"",resposta:"",
      estado:"entregue",transmitida:true,nivel:"local",confirmado:false,peers:0});});}
    return _api(p,o); };
  tx.value="A-carga"; pa.value="";
  document.getElementById("form").requestSubmit();
  await new Promise(r=>setTimeout(r,400));
  out.btnDurante=bt.disabled;
  tx.value="B-carga"; tx.dispatchEvent(new Event("input",{bubbles:true}));
  _res();
  await new Promise(r=>setTimeout(r,600));
  out.after=tx.value; out.chamadas=n; out.btnDepois=bt.disabled;
  const rc3=document.querySelector(".sm-compor").getBoundingClientRect();
  out.composerFim=(rc3.top>=0&&rc3.bottom<=window.innerHeight);
"""
        obs = self._rodar(sonda, 1366, 768)
        self.assertEqual(obs.get("erro", ""), "", obs.get("erro"))
        self.assertEqual(obs.get("after"), "B-carga",
                         "sucesso de A apagou B com carga: %r" % obs)
        self.assertEqual(obs.get("chamadas"), 1, "duplo envio: %r" % obs)
        self.assertTrue(obs.get("btnDurante"), "botao sem disabled: %r" % obs)
        self.assertTrue(obs.get("composerFim"),
                        "composer sumiu apos envio com carga: %r" % obs)

    def test_teclado_anexo_dm_aviso_intactos(self):
        sonda = self.LOGIN + """
  const tx=document.getElementById("texto"),pa=document.getElementById("para");
  // Tab alcanca o campo
  tx.focus();
  out.focoTexto=(document.activeElement===tx);
  out.tabIndexOk=(tx.tabIndex>=0);
  // Enter envia, Shift+Enter nao
  let nEnvios=0;
  document.getElementById("form").addEventListener("submit",
    e=>{e.preventDefault();nEnvios++;},{once:false});
  // conta apenas os sinteticos abaixo (poll/envio real nao disparam submit)
  nEnvios=0;
  tx.value="linha";
  tx.dispatchEvent(new KeyboardEvent("keydown",{key:"Enter",bubbles:true,cancelable:true}));
  await new Promise(r=>setTimeout(r,300));
  out.enterEnvia=(nEnvios>=1);
  const antes=nEnvios;
  tx.dispatchEvent(new KeyboardEvent("keydown",{key:"Enter",shiftKey:true,bubbles:true,cancelable:true}));
  await new Promise(r=>setTimeout(r,200));
  out.shiftEnterNaoEnvia=(nEnvios===antes);
  // Esc limpa DM
  pa.value="@alguem";
  pa.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",bubbles:true,cancelable:true}));
  await new Promise(r=>setTimeout(r,200));
  out.escLimpaDM=(pa.value==="");
  // setas trocam de aba (contrato ARIA do redesign)
  const a=document.getElementById("tab-chat"),b=document.getElementById("tab-configs");
  a.focus();
  a.dispatchEvent(new KeyboardEvent("keydown",{key:"ArrowRight",bubbles:true,cancelable:true}));
  await new Promise(r=>setTimeout(r,200));
  out.setaVaiConfigs=(document.activeElement===b)
    &&(document.getElementById("pane-configs").style.display!=="none");
  b.dispatchEvent(new KeyboardEvent("keydown",{key:"ArrowLeft",bubbles:true,cancelable:true}));
  await new Promise(r=>setTimeout(r,200));
  out.setaVoltaChat=(document.activeElement===a)
    &&(document.getElementById("pane-chat").style.display!=="none");
  // anexo: input recebe arquivo e anuncia
  const aq=document.getElementById("arq");
  const dt=new DataTransfer();
  dt.items.add(new File(["x"],"prova.txt",{type:"text/plain"}));
  aq.files=dt.files;
  aq.dispatchEvent(new Event("change",{bubbles:true}));
  await new Promise(r=>setTimeout(r,200));
  out.anexoNome=(document.getElementById("arq-nome").textContent||"");
  // DM via aria-label do botao
  out.dmBotaoExiste=!!document.querySelector('#presentes [aria-label]');
  // aviso honesto continua texto (nunca some por CSS)
  const sys=document.getElementById("sys");
  sys.textContent="Mensagem transmitida, mas NO salva.";
  await new Promise(r=>setTimeout(r,100));
  const cs2=getComputedStyle(sys);
  out.avisoVisivel=(cs2.display!=="none"&&cs2.visibility!=="hidden");
  out.contador=(document.getElementById("contador").textContent||"");
"""
        obs = self._rodar(sonda, 1366, 768)
        self.assertEqual(obs.get("erro", ""), "", obs.get("erro"))
        self.assertTrue(obs.get("focoTexto"), "textarea sem foco: %r" % obs)
        self.assertTrue(obs.get("tabIndexOk"), "fora do Tab: %r" % obs)
        self.assertTrue(obs.get("enterEnvia"), "Enter nao envia: %r" % obs)
        self.assertTrue(obs.get("shiftEnterNaoEnvia"),
                        "Shift+Enter enviou (quebra multilinha): %r" % obs)
        self.assertTrue(obs.get("escLimpaDM"), "Esc nao limpa DM: %r" % obs)
        self.assertTrue(obs.get("setaVaiConfigs"), "seta p/ configs: %r" % obs)
        self.assertTrue(obs.get("setaVoltaChat"), "seta volta chat: %r" % obs)
        self.assertIn("prova.txt", obs.get("anexoNome", ""),
                      "anexo nao anuncia: %r" % obs)
        self.assertTrue(obs.get("avisoVisivel"), "aviso escondido: %r" % obs)


if __name__ == "__main__":
    unittest.main()
