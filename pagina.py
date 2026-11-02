#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SenderMe — página web servida em `/` (HTML+CSS+JS embutidos).

Folha sem dependências: só dados (string). `senderme.py` importa PAGINA
para servir no HTTP local. O JS continua não-raw triple-quoted: escapar
vale para Python+JS (ver AGENTS.md).
"""
PAGINA = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SenderMe</title>
<link rel="stylesheet" href="/bootstrap.min.css">
<style>
:root{
--sm-bg:#e6edea;
--sm-surface:#ffffff;
--sm-tinta:#172825;
--sm-suave:#4d605d;
--sm-borda:#ccd9d4;
--sm-primaria:#0e5f5b;
--sm-primaria-escura:#093e3c;
--sm-bolha:#edf2f0;
--sm-bolha-eu:#d1ebdb;
--sm-dm:#5b4bc4;
--sm-aviso-bg:#fff8e1;
--sm-foco:#0e5f5b;
--sm-raio:.9rem;
--bs-primary:#0e5f5b;
--bs-primary-rgb:14,95,91;
}
html{-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale}
*,*::before,*::after{box-sizing:border-box}
body{margin:0;background:radial-gradient(1200px 500px at 15% -5%,#f7f3e2 0%,rgba(247,243,226,0) 60%),radial-gradient(900px 480px at 110% 10%,#d8e8e2 0%,rgba(216,232,226,0) 55%),var(--sm-bg);color:var(--sm-tinta);font-family:system-ui,-apple-system,"Segoe UI",Ubuntu,Cantarell,"Noto Sans",Arial,sans-serif;min-height:100vh;min-height:100dvh;overflow-x:hidden}
.sm-pular{position:absolute;left:.75rem;top:-4rem;z-index:50;background:var(--sm-primaria);color:#fff;padding:.6rem 1rem;border-radius:.6rem;text-decoration:none;transition-property:transform,background-color;transition-duration:150ms;transition-timing-function:ease-out}
.sm-pular:focus{top:.75rem;color:#fff}
:focus-visible{outline:3px solid var(--sm-foco);outline-offset:2px;border-radius:.35rem}
.visually-hidden{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
ul#presentes,ul#calados{list-style:none;padding-left:0;margin-bottom:0}
#presentes .list-group-item{display:flex;justify-content:space-between;align-items:center;gap:.5rem}
#calados .list-group-item{display:flex;justify-content:space-between;align-items:center;gap:.5rem}
.sm-envolt{max-width:1120px;margin-left:auto;margin-right:auto;padding-left:.75rem;padding-right:.75rem;padding-top:.75rem;padding-bottom:.75rem;min-width:0;min-height:100vh;min-height:100dvh}
.sm-topo{display:flex;align-items:center;justify-content:space-between;gap:1rem;background:rgba(255,255,255,.86);border:1px solid var(--sm-borda);border-radius:var(--sm-raio);padding:.55rem .9rem;margin-bottom:.6rem;box-shadow:0 1px 2px rgba(16,40,38,.08)}
.sm-marca{display:flex;align-items:center;gap:.7rem;min-width:0}
.sm-logo{display:inline-flex;align-items:center;justify-content:center;width:2.4rem;height:2.4rem;border-radius:.8rem;background:var(--sm-primaria);color:#fff;font-size:1.3rem;flex:none}
.sm-nome{font-family:"Iowan Old Style",Palatino,Georgia,"Times New Roman",serif;font-size:1.35rem;line-height:1;display:block;letter-spacing:.01em;text-wrap:balance}
.sm-rede{display:block;font-size:.78rem;color:var(--sm-suave)}
.sm-eu{display:flex;align-items:center;gap:.6rem;min-width:0;font-size:.9rem}
.sm-eu #eu{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:32ch}
.sm-abas{display:flex;gap:.4rem;background:rgba(255,255,255,.7);border:1px solid var(--sm-borda);border-radius:999px;padding:.3rem;margin-bottom:.6rem;width:fit-content;max-width:100%}
.sm-aba{border:1px solid transparent;background:transparent;border-radius:999px;padding:.5rem 1.1rem;min-height:44px;font-weight:600;color:var(--sm-suave);transition-property:background-color,color,border-color;transition-duration:150ms;transition-timing-function:ease-out}
.sm-aba:hover{background:#e2ebe8;color:var(--sm-tinta)}
.sm-aba.active{background:var(--sm-primaria);color:#fff}
#upd{border-left:4px solid #b98a00;flex:none;margin-bottom:.6rem}
.sm-grade{display:grid;grid-template-columns:290px minmax(0,1fr);gap:.8rem;align-items:start;min-height:0}
.sm-lateral{overflow:hidden;min-height:0}
.sm-lateral .card-header{font-weight:700}
#presentes{max-height:320px;overflow-y:auto;margin-bottom:0;min-height:0}
#presentes .list-group-item{padding:.55rem .8rem}
#presentes .nick{display:inline-block;vertical-align:bottom;max-width:14ch;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:600}
#presentes button{min-height:36px;min-width:44px}
#presentes button:hover{border-color:var(--sm-primaria);color:var(--sm-primaria)}
#presentes-vazio{padding:.7rem 1rem;color:var(--sm-suave);font-size:.9rem}
.sm-conversa{display:flex;flex-direction:column;gap:.5rem;min-width:0;min-height:0}
#msgs{height:clamp(260px,46vh,560px);overflow-y:auto;background:var(--sm-surface);border:1px solid var(--sm-borda);border-radius:var(--sm-raio);padding:.8rem;display:flex;flex-direction:column;gap:.55rem;scroll-behavior:smooth;min-height:0}
#msgs:focus-visible{outline:3px solid var(--sm-foco);outline-offset:2px}
.msg{display:flex;flex-direction:column;align-items:flex-start;max-width:100%;animation:sm-entrar 160ms ease-out}
.msg.eu{align-items:flex-end}
.cabecalho{display:flex;align-items:baseline;gap:.45rem;max-width:100%;margin-bottom:.25rem}
.hora{color:#475569;font-size:.75rem;font-variant-numeric:tabular-nums;flex:none}
.nick{font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:22ch;display:inline-block;vertical-align:bottom}
.balao{background:var(--sm-bolha);border:1px solid var(--sm-borda);border-radius:.2rem .7rem .7rem .7rem;padding:.55rem .8rem;white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;max-width:min(85%,46rem);box-shadow:0 1px 2px rgba(16,40,38,.07);transition-property:border-color,background-color;transition-duration:150ms;transition-timing-function:ease-out}
.eu .balao{background:var(--sm-bolha-eu);border-radius:.7rem .2rem .7rem .7rem}
.dm .balao{border-left:4px solid var(--sm-dm)}
.sys{color:#3d4f4d;font-size:.88rem;white-space:pre-wrap;background:#eef3f2;border:1px solid var(--sm-borda);border-radius:999px;padding:.3rem .8rem;align-self:center;text-align:center;max-width:100%}
#sys{min-height:1.5em;flex:none}
#sys:empty::before{content:"Pronto para conversar. /ajuda lista comandos.";color:var(--sm-suave);font-size:.88rem}
.sm-compor{background:var(--sm-surface);border:1px solid var(--sm-borda);border-radius:var(--sm-raio);padding:.75rem;box-shadow:0 1px 2px rgba(16,40,38,.07);flex:none}
.sm-rotulo-linha{display:flex;align-items:baseline;justify-content:space-between;gap:.6rem;margin-bottom:.35rem}
.sm-rotulo{font-size:.82rem;font-weight:700;color:var(--sm-suave);letter-spacing:.02em}
#contador{font-size:.78rem;color:var(--sm-suave);font-variant-numeric:tabular-nums}
#npres{font-variant-numeric:tabular-nums}
textarea{resize:vertical}
#texto{min-height:60px;max-height:28vh}
#texto::placeholder{color:#6b7d7a}
.sm-linha-envio{display:grid;grid-template-columns:minmax(0,1fr) 190px auto;gap:.6rem;align-items:end;margin-top:.5rem}
.sm-linha-envio .form-control{min-height:44px}
.sm-enviar{display:flex;align-items:end}
#btnEnviar{min-height:44px;min-width:96px;font-weight:700;background:var(--sm-primaria);border-color:var(--sm-primaria);transition-property:transform,background-color,border-color,box-shadow;transition-duration:150ms;transition-timing-function:ease-out}
#btnEnviar:hover{background:var(--sm-primaria-escura);border-color:var(--sm-primaria-escura)}
#btnEnviar:active{transform:scale(.97)}
#btnEnviar:disabled{opacity:.6;cursor:not-allowed;transform:none}
button:disabled{cursor:not-allowed}
.btn-secondary{min-height:44px}
a:hover{color:var(--sm-primaria-escura)}
.list-group-item button:hover{border-color:var(--sm-primaria)}
img{outline:1px solid rgba(0,0,0,.1);outline-offset:-1px}
.img-thumbnail{border-radius:.6rem}
.login-wrap{min-height:100vh;min-height:100dvh;display:flex;align-items:center;justify-content:center;padding:1rem}
.login-card{width:min(420px,100%);box-shadow:0 12px 32px rgba(16,40,38,.14);border:1px solid var(--sm-borda);border-radius:1rem}
.login-marca{font-family:"Iowan Old Style",Palatino,Georgia,serif;font-size:2rem;margin-bottom:0;text-wrap:balance}
.login-sub{color:var(--sm-suave)}
#loginerr:empty{margin:0}
.config-grade{display:grid;gap:1rem}
code#meuid{display:block;overflow-wrap:anywhere;word-break:break-all;background:#f2f5f4;padding:.5rem .7rem;border-radius:.5rem;border:1px solid var(--sm-borda)}
pre#rede,pre#ajuda{background:#f2f5f4;border:1px solid var(--sm-borda);border-radius:.6rem;padding:.7rem;max-height:220px;overflow-y:auto}
@keyframes sm-entrar{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
@media (max-width:920px){
.sm-grade{grid-template-columns:minmax(0,1fr)}
#presentes{max-height:170px}
#msgs{height:clamp(240px,44vh,520px)}
.sm-topo{flex-wrap:wrap}
}
@media (max-width:640px){
.sm-linha-envio{grid-template-columns:minmax(0,1fr)}
.sm-enviar{align-items:stretch}
#btnEnviar{width:100%}
.sm-eu #eu{max-width:18ch}
.sm-abas{width:100%}
.sm-aba{flex:1}
}
@media (min-width:921px) and (min-height:500px){
.sm-envolt#app[style*="block"]{display:flex !important;flex-direction:column;height:100vh;height:100dvh;min-height:0;padding-top:.6rem;padding-bottom:.6rem}
.sm-topo,.sm-abas,#upd{flex:none}
#pane-chat{flex:1 1 auto;min-height:0}
#pane-configs{flex:1 1 auto;min-height:0;overflow-y:auto}
.sm-grade{height:100%;min-height:0;align-items:stretch}
.sm-lateral{align-self:stretch;display:flex;flex-direction:column;min-height:0;max-height:100%}
#presentes{flex:1 1 auto;min-height:80px;max-height:none}
.sm-conversa{min-height:0;height:100%}
#msgs{height:auto;flex:1 1 auto;min-height:120px;max-height:none}
}
@media (prefers-reduced-motion:reduce){
*{animation:none;transition:none;scroll-behavior:auto}
}
</style>
</head>
<body>
<a class="sm-pular" href="#msgs">Pular para mensagens</a>
<div class="container py-3 sm-envolt" id="app" style="display:none">
<header class="sm-topo">
<div class="sm-marca"><span class="sm-logo" aria-hidden="true">◍</span><div><span class="sm-nome">SenderMe</span><small class="sm-rede">rede local, sem servidor central</small></div></div>
<div class="sm-eu"><span class="navbar-text" id="eu"></span> <span id="status" class="badge bg-success" role="status">online</span></div>
</header>
<nav aria-label="Seções do aplicativo"><div class="sm-abas" role="tablist" aria-label="Chat e configs">
<button class="sm-aba nav-link active" id="tab-chat" role="tab" aria-selected="true" aria-controls="pane-chat" onclick="mostrar('chat')">Chat</button>
<button class="sm-aba nav-link" id="tab-configs" role="tab" aria-selected="false" aria-controls="pane-configs" onclick="mostrar('configs')">Configs</button>
</div></nav>
<div id="upd" class="alert alert-warning" style="display:none" role="status"></div>
<div id="pane-chat" role="tabpanel" aria-labelledby="tab-chat" tabindex="0">
<div class="sm-grade">
<section class="card sm-lateral" aria-labelledby="titulo-presentes">
<div class="card-header" id="titulo-presentes">Presentes (<span id="npres">0</span>)</div>
<ul class="list-group list-group-flush" id="presentes" aria-label="Participantes presentes"></ul>
<p class="sm-vazio" id="presentes-vazio" hidden>Ninguém mais por aqui ainda. Quando alguém entrar na rede, aparece nesta lista.</p>
</section>
<section class="sm-conversa" aria-labelledby="titulo-conversa">
<h2 id="titulo-conversa" class="visually-hidden">Conversa</h2>
<div id="msgs" role="log" aria-live="polite" aria-label="Mensagens do chat" tabindex="0"></div>
<div id="sys" class="sys mt-2" role="status" aria-live="polite"></div>
<form id="form" class="sm-compor mt-2" aria-label="Enviar mensagem">
<div class="sm-campo">
<div class="sm-rotulo-linha"><label class="sm-rotulo" for="texto">Mensagem</label><span id="contador" aria-live="polite">0/2000</span></div>
<textarea id="texto" class="form-control mb-2" rows="2" maxlength="2000" aria-describedby="dica-envio contador" placeholder="Mensagem (Enter envia, Shift+Enter quebra linha). /ajuda lista comandos."></textarea>
<div class="form-text" id="dica-envio">Enter envia, Shift+Enter quebra linha. Até 2000 caracteres. Erros mantêm seu texto.</div>
</div>
<div class="sm-linha-envio">
<div><label class="sm-rotulo" for="arq">Anexo</label>
<input type="file" id="arq" class="form-control" aria-describedby="ajuda-arq">
<div class="form-text" id="ajuda-arq">Arquivos até 20 MB, qualquer tipo. 60 MB acumulados + 24 h, depois apaga os mais antigos.</div>
<div class="form-text" id="arq-nome" aria-live="polite"></div>
</div>
<div><label class="sm-rotulo" for="para">Destino (DM opcional)</label>
<input type="text" id="para" class="form-control" placeholder="@alvo (DM opcional)" autocomplete="off" spellcheck="false" aria-describedby="dica-dm">
<div class="form-text" id="dica-dm">Vazio fala com todos. Com @alvo vira privada. Esc limpa.</div>
</div>
<div class="sm-enviar"><button class="btn btn-primary" type="submit" id="btnEnviar">Enviar</button></div>
</div>
</form>
</section>
</div>
</div>
<div id="pane-configs" style="display:none" role="tabpanel" aria-labelledby="tab-configs" tabindex="0">
<div class="card mb-3"><div class="card-body config-grade">
<div><h2 class="h5">Apelido</h2>
<div class="d-flex gap-2"><div class="flex-grow-1"><label class="sm-rotulo visually-hidden" for="novonick">Novo apelido</label><input id="novonick" class="form-control" maxlength="24" autocomplete="nickname"></div><button class="btn btn-secondary" onclick="trocarNick()">Trocar</button></div>
<div class="form-text">Histórico mantém o nome da época.</div></div>
<div><h2 class="h5 mt-3">Meu ID</h2><code id="meuid"></code></div>
<div><h2 class="h5 mt-3">Rede</h2><pre id="rede" style="white-space:pre-wrap"></pre></div>
<div><h2 class="h5 mt-3">Silenciados</h2><ul id="calados" class="list-group"></ul></div>
<div><h2 class="h5 mt-3">Ajuda</h2><pre id="ajuda" style="white-space:pre-wrap"></pre></div>
</div></div>
</div>
</div>
<div class="login-wrap" id="login">
<div class="card p-4 login-card"><h1 class="h4 login-marca">SenderMe</h1>
<p class="login-sub">Escolha seu apelido para entrar.</p>
<form id="loginform" aria-label="Entrar no chat">
<label class="sm-rotulo" for="nick">Apelido</label>
<div class="d-flex gap-2 mt-1"><input id="nick" class="form-control" maxlength="24" placeholder="apelido" autocomplete="nickname">
<button class="btn btn-primary" type="submit">Entrar</button></div>
</form>
<div id="loginerr" class="text-danger mt-2" role="alert"></div>
</div>
</div>
<script>
let lastMid="", ME="", MINHAV="", enviando=false, falhas=0;
function esc(s){return (s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;")}
function midOk(x){return typeof x==="string"&&/^[0-9a-f]{64}$/.test(x)}
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
   document.getElementById("meuid").textContent=e.id;poll();configs();
   let tx=document.getElementById("texto");if(tx&&tx.focus){try{tx.focus()}catch(err){}}}
 }catch(err){selo(false)}
}
async function login(){
 try{
  let n=document.getElementById("nick").value;
  let r=await api("/api/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({nick:n})});
  if(r.ok){await estado();if(r.msg&&/aviso/i.test(r.msg)){sysMsg(r.msg)}}else{document.getElementById("loginerr").textContent=r.msg||"erro"}
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
 let a=document.getElementById("tab-chat"),b=document.getElementById("tab-configs");
 if(a&&a.setAttribute)a.setAttribute("aria-selected",q=="chat"?"true":"false");
 if(b&&b.setAttribute)b.setAttribute("aria-selected",q=="configs"?"true":"false");
 if(q=="configs")configs();
}
function bolha(m){
 let d=document.createElement("div");d.className="msg"+(m.proprio?" eu":"")+(m.dm?" dm":"");
 if(m.tipo=="join"||m.tipo=="leave"||m.tipo=="nick"){d.innerHTML='<div class="sys">'+esc(m.hora)+" "+esc(m.txt)+"</div>";return d}
 let h='<span class="cabecalho"><span class="hora">'+esc(m.hora)+'</span> <b class="nick" title="'+esc(m.nick)+'">'+esc(m.nick)+"</b>"+(m.dm?' <span class="badge bg-secondary">dm</span>':"")+"</span>";
 h+='<div class="balao">'+esc(m.txt||"");
 if(m.tipo=="file"&&m.arq){
  let kb=(m.arq.tamanho/1024).toFixed(1);
  h+="<br><b>📎 "+esc(m.arq.nome)+" ("+kb+" KB)</b><br>";
  if(m.arq.pronto&&midOk(m.mid)){h+='<a href="/api/arquivo/'+m.mid+'" target="_blank" rel="noopener">baixar</a>';}
  else{h+="<i>baixando/expirado…</i>"}
  let nm=(m.arq.nome||"").toLowerCase();
  if(m.arq.pronto&&midOk(m.mid)&&(nm.endsWith(".png")||nm.endsWith(".jpg")||nm.endsWith(".jpeg")||nm.endsWith(".gif")||nm.endsWith(".webp"))){
   h+='<br><img src="/api/arquivo/'+m.mid+'" alt="Prévia de '+esc(m.arq.nome)+'" loading="lazy" style="max-width:220px;max-height:160px" class="img-thumbnail">';}
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
   let seguir=(box.scrollTop+box.clientHeight>=box.scrollHeight-48);
   for(let m of r.eventos){box.appendChild(bolha(m));lastMid=m.mid}
   if(seguir){box.scrollTop=box.scrollHeight}
   let ul=document.getElementById("presentes");ul.innerHTML="";
   document.getElementById("npres").textContent=(r.presentes||[]).length;
   let vazio=document.getElementById("presentes-vazio");
   if(vazio){vazio.hidden=(r.presentes||[]).length!==0}
   for(let p of (r.presentes||[])){let li=document.createElement("li");li.className="list-group-item d-flex justify-content-between align-items-center gap-2";
    li.innerHTML='<span class="nick" title="'+esc(p.nick)+'">'+esc(p.nick)+(p.eu?" (você)":"")+'</span> <small class="text-muted">'+esc(p.curto)+"</small>";
    let b=document.createElement("button");b.className="btn btn-sm btn-outline-secondary ms-2";b.textContent=p.eu?"-":"DM";
    b.setAttribute("aria-label",p.eu?("Você: "+p.nick):("Conversar em privado com "+p.nick));
    if(!p.eu){b.dataset.n=p.nick;b.onclick=function(){dmPara(this.dataset.n)}}
    else{b.disabled=true}
    li.appendChild(b);ul.appendChild(li);}
  }
 }catch(err){selo(false)}
}
setInterval(function(){if(document.getElementById("app").style.display!=="none")poll()},700);
document.addEventListener("visibilitychange",function(){if(!document.hidden)poll()});
document.getElementById("form").addEventListener("submit",async e=>{
 e.preventDefault();
 if(enviando)return; enviando=true;
 let btn=document.getElementById("btnEnviar");
 let txtBtn=btn?(btn.textContent||"Enviar"):"Enviar";
 if(btn){btn.disabled=true;if(btn.setAttribute)btn.setAttribute("aria-busy","true");btn.textContent="Enviando…"}
 try{
  let f=document.getElementById("arq").files[0];
  let para=document.getElementById("para").value.trim();
  let txt=document.getElementById("texto").value;
  let txtEnviado=txt,paraEnviado=para,fEnviado=f||null;
  if(!f&&ultimoNaoSalvo&&txt===ultimoNaoSalvo.texto&&para===ultimoNaoSalvo.para){sysMsg(AVISO_NAO_SALVO);atualizarBloqueio();return}
  if(f){
   if(f.size>20*1024*1024){sysMsg("Arquivo > 20 MB");return}
   let fd=new FormData();fd.append("file",f);fd.append("texto",txt);fd.append("para",para);
   sysMsg("Enviando arquivo...");
   let r=await fetch("/api/upload",{method:"POST",body:fd});let j=await r.json();
   if(!j.ok){sysMsg("Falha no upload: "+(j.msg||"erro")+" (texto mantido)");return}
   let txtEl=document.getElementById("texto"),paraEl=document.getElementById("para"),arqEl=document.getElementById("arq");
   let curF=arqEl&&arqEl.files?arqEl.files[0]:null;
   if(arqEl&&curF===fEnviado){arqEl.value=""}
   if(txtEl&&txtEl.value===txtEnviado&&((paraEl?(paraEl.value||"").trim():"")===paraEnviado)){txtEl.value=""}
   atualizaContador();atualizaAnexo();sysMsg(null);poll();return;
  }
  let r=await api("/api/enviar",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({texto:txt,para:para})});
  if(r.rede===false){sysMsg("Sem conexao: mensagem mantida, tente de novo");return}
  if(r.transmitida===true&&r.estado==="somente_memoria"){sysMsg(AVISO_NAO_SALVO);ultimoNaoSalvo={texto:txt,para:para};atualizarBloqueio();return}
  let t=r.resposta||r.msg||"erro";
  let txtTrim=(txt||"").trim();let paraTrim=(para||"").trim();
  let ehDMPara=paraTrim!=="";let txtLow=txtTrim.toLowerCase();
  let ehDMBarra=txtLow.indexOf("/dm ")===0||txtLow==="/dm";
  let ehDM=ehDMPara||ehDMBarra;let ehPublica=!ehDM&&txtTrim.charAt(0)!=="/";
  if(r.estado==="entregue"||r.estado==="guardada"){
   if(r.resposta){sysMsg(r.resposta)}
   else if(r.ok&&ehPublica&&r.nivel==="local"&&typeof r.peers==="number"){
    if(r.peers===0){sysMsg("Publicada localmente, sem peers conectados — só você vê por enquanto.")}
    else{sysMsg("Publicada localmente para "+r.peers+" peer(s) — sem confirmação de recebimento ou leitura.")}
   }
   else if(r.ok&&ehDM&&r.nivel==="socket"&&r.estado==="entregue"){sysMsg("Enviada — sem confirmação de recebimento ou leitura.")}
   else if(r.ok){sysMsg(null)}
   else{sysMsg(t)}
   let txtEl2=document.getElementById("texto"),paraEl2=document.getElementById("para");
   if(txtEl2&&txtEl2.value===txtEnviado&&((paraEl2?(paraEl2.value||"").trim():"")===paraEnviado)){txtEl2.value=""}
   ultimoNaoSalvo=null;atualizarBloqueio();atualizaContador();poll();return;
  }
  if(r.estado==="somente_memoria"||r.estado==="erro"){
   sysMsg(t||"Erro: texto mantido");return;
  }
  // fallback legado: backend antigo sem r.estado — decide pelo texto
  if(!r.ok){
   sysMsg(t||"Erro: texto mantido");
   let tl=(""+t).toLowerCase();
   let falhouSalvar=tl.indexOf("aviso")>=0||tl.indexOf("nao consegui salvar")>=0||tl.indexOf("não consegui salvar")>=0||tl.indexOf("nao foi salvo")>=0||tl.indexOf("não foi salvo")>=0||tl.indexOf("só em memória")>=0||tl.indexOf("so em memoria")>=0||tl.indexOf("perdid")>=0;
   let guardada=tl.indexOf("guardad")>=0||tl.indexOf("salvo local")>=0||tl.indexOf("entrego quando voltar")>=0;
   if(!falhouSalvar&&guardada){let txtEl3=document.getElementById("texto"),paraEl3=document.getElementById("para");if(txtEl3&&txtEl3.value===txtEnviado&&((paraEl3?(paraEl3.value||"").trim():"")===paraEnviado)){txtEl3.value=""}atualizaContador();poll()}
   return;
  }
  if(r.resposta){sysMsg(r.resposta)}
  else{sysMsg(null)}
  let txtEl4=document.getElementById("texto"),paraEl4=document.getElementById("para");
  if(txtEl4&&txtEl4.value===txtEnviado&&((paraEl4?(paraEl4.value||"").trim():"")===paraEnviado)){txtEl4.value=""}atualizaContador();poll();
 }catch(err){sysMsg("Falha de rede (texto mantido)")}
 finally{enviando=false;if(btn){if(btn.removeAttribute)btn.removeAttribute("aria-busy");btn.textContent=txtBtn;atualizarBloqueio()}}
});
function sysMsg(t){let s=document.getElementById("sys");if(t){s.textContent=t}else{s.textContent=""}}
var AVISO_NAO_SALVO="Mensagem transmitida, mas NÃO salva no histórico. Texto mantido como cópia — edite para liberar novo envio.";
var ultimoNaoSalvo=null;
function atualizarBloqueio(){
 var tE=document.getElementById("texto"),pE=document.getElementById("para"),b=document.getElementById("btnEnviar");
 if(!tE||!pE||!b||tE.value===undefined)return false;
 if(enviando){b.disabled=true;return true}
 var bloq=!!(ultimoNaoSalvo&&tE.value===ultimoNaoSalvo.texto&&(pE.value||"").trim()===ultimoNaoSalvo.para);
 b.disabled=bloq;return bloq;
}
function atualizaContador(){
 var t=document.getElementById("texto"),c=document.getElementById("contador");
 if(!t||!c||c.textContent===undefined)return;
 c.textContent=(t.value||"").length+"/2000";
}
function atualizaAnexo(){
 var a=document.getElementById("arq"),n=document.getElementById("arq-nome");
 if(!a||!n||n.textContent===undefined)return;
 let f=a.files&&a.files[0];
 n.textContent=f?("Selecionado: "+f.name+" ("+(f.size/1024).toFixed(1)+" KB) — Enviar publica junto. "):"";
}
(function(){var t=document.getElementById("texto"),p=document.getElementById("para");
 if(t&&t.addEventListener)t.addEventListener("input",function(){atualizarBloqueio();atualizaContador()});
 if(p&&p.addEventListener)p.addEventListener("input",function(){atualizarBloqueio()});})();
document.getElementById("texto").addEventListener("keydown",e=>{
 if(e.key=="Enter"&&!e.shiftKey){e.preventDefault();document.getElementById("form").requestSubmit()}
});
async function configs(){
 try{
  let r=await api("/api/rede");document.getElementById("rede").textContent=(r.linhas||[]).join("\\n");
  let a=await api("/api/ajuda");document.getElementById("ajuda").textContent=a.texto||"";
  let c=await api("/api/calados");let ul=document.getElementById("calados");ul.innerHTML="";
  for(let x of (c.lista||[])){let li=document.createElement("li");li.className="list-group-item d-flex justify-content-between align-items-center gap-2";
   li.innerHTML='<span class="nick" title="'+esc(x.nick)+'">'+esc(x.nick)+' <small class="text-muted">'+esc(x.curto)+"</small></span>";
   let b=document.createElement("button");b.className="btn btn-sm btn-outline-primary";b.textContent="descalar";
   b.setAttribute("aria-label","Voltar a ver "+x.nick);
   b.dataset.n=x.nick;b.onclick=function(){descalar(this.dataset.n)};
   li.appendChild(b);ul.appendChild(li);}
 }catch(err){}
}
(function(){
 var lf=document.getElementById("loginform");
 if(lf&&lf.addEventListener)lf.addEventListener("submit",function(e){e.preventDefault();login()});
 var arq=document.getElementById("arq");
 if(arq&&arq.addEventListener)arq.addEventListener("change",function(){atualizaAnexo()});
 var tx=document.getElementById("texto");
 if(tx&&tx.addEventListener){atualizaContador()}
 var pa=document.getElementById("para");
 if(pa&&pa.addEventListener)pa.addEventListener("keydown",function(e){if(e.key=="Escape"){pa.value="";atualizarBloqueio()}});
 var a=document.getElementById("tab-chat"),b=document.getElementById("tab-configs");
 function tecla(e){
  if(e.key!=="ArrowRight"&&e.key!=="ArrowLeft")return;
  e.preventDefault();
  let indo=a&&(document.activeElement===a||e.key==="ArrowRight"&&document.activeElement!==b);
  if(document.activeElement===a&&e.key==="ArrowRight"){mostrar("configs");if(b&&b.focus)b.focus()}
  else if(document.activeElement===b&&e.key==="ArrowLeft"){mostrar("chat");if(a&&a.focus)a.focus()}
 }
 if(a&&a.addEventListener)a.addEventListener("keydown",tecla);
 if(b&&b.addEventListener)b.addEventListener("keydown",tecla);
})();
estado();
</script>
</body>
</html>
"""
