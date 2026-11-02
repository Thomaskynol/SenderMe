# SenderMe — Progresso e Próximos Passos

> **Este é o documento de retomada.** Sessão nova sem memória: leia `01-produto.md`,
> depois `02-arquitetura.md`, e use este arquivo para continuar de onde parou.
> Trechos antigos ficam datados; "atual" = entrada mais recente.
> Relatórios de rodada (`RELATORIO_*.md`) e `arquivos_e_entregas/` foram
> arquivados fora da árvore em `SenderMe-historico/relatorios/` (1.13);
> "relatório X arquivado" abaixo aponta para lá.

## Integração final 1.23 (2026-11-02, ASSINADA)

- Pousado absorvido sem reedição de lógica (`ses_e649e88cbffesH6hPwZqpscC9o`:
  `pagina.py` só CSS/estrutura + textarea rows 3→2, JS byte-idêntico
  staged-vs-worktree (14124); `tests/test_ui_layout.py` 11 testes: shell
  100dvh com rolagem interna, composer visível sem scroll de página em
  1366×768 e 1280×720, 390px/400px/zoom-200% acessíveis, carga 200 msgs +
  40 pessoas, rascunho em envio lento). Checkpoint pré-bump
  `sender-me-pre-1.23-20261102T083256Z.zip` fora da árvore (SHA
  `6287b11765b817db96446faa14d703dc491ae36341a0109a1c081d05c2f92fd2`,
  89 arquivos; sem dados/privada/.git/dist/logs/caches; `.planning/` da
  sessão fora do ZIP).
- Bump `meta.py` 1.22 → 1.23 (1 linha; 1.23 livre confirmado: zero refs).
  "Atual" em README + docs/01–02 (títulos e `VERSAO` citada) +
  `ROTEIRO-ESCOLA.md` (unsigned: título, referência e esperado → 1.23);
  histórico intacto. Assinatura oficial
  `python3 dono/assinar_update.py`: código==manifesto 1.23, 26/26 nomes+hashes,
  sig True. `bash build_dist.sh` release exit 0: `dist/SenderMe` com 26 +
  manifesto, sem `.git`/`dados`/`dono`/`logs`/`docs`/checkpoints/roteiro/README,
  `TERCEIROS.md` presente, `VERSAO` 1.23.
- Boot da `dist/` limpa em cópia isolada (`/tmp/opencode`, identidade sintética
  nova, portas efêmeras, `SENDERME_NO_BROADCAST=1`, só PID próprio): `/api/eu` →
  1.23, `logado:false`; `node --check` no JS direto + no JS servido via HTTP OK;
  processo encerrado, porta fechada, cópia removida.
- P2P real 1.22→1.23 (base 1.22 do checkpoint pré-bump acima, manifesto 1.22
  assinado, fora da árvore + install 1.23 desta árvore, identidades sintéticas
  distintas, portas efêmeras, `SENDERME_FIXOS` cruzado, `SENDERME_NO_BROADCAST=1`,
  loopback, só `curl`, launcher emulado no exit 42 — `start.sh` real nunca
  executado): B "update v1.23 recebido, baixando 26 arquivos", aplicou,
  exit 42, relançado, `/api/eu` → 1.23 com id de B preservado,
  `update-manifest.json` A==B byte-idêntico (retransmite), pública A→B
  `{ok:true, estado:entregue, transmitida:true, nivel:local}` visível em B,
  `grep` por segredos nos dois diários exit 1 (sem achados); só PIDs próprios
  mortos, tmp removido.
- Nota de harness (não bug do app): a 1ª tentativa separou código e
  `SENDERME_HOME` (update aplicou dentro do HOME e o relançado seguiu 1.22 —
  esperado, pois `PASTA == SENDERME_HOME or dirname(app)`); refeita no layout
  dist (código+dados juntos), OK.
- Suíte completa fresca: `python3 -m unittest discover -s tests` → **412 testes
  OK, 0 falhas, 0 skips, exit 0** (401 + 11 `test_ui_layout`). Chromium isolado
  (perfil tmp, 1366×768 + 1280×720, composer visível com `pageScrollY==0`)
  11/11 OK.
- "Atual" em README + docs/01–03; linha 1.22→1.23 na matriz de docs/04;
  `ARQUIVOS_UPDATE` 26 (sem mudança de conjunto).
- Não testado aqui: Mint/pendrive físico, rede da escola, 6–20 peers,
  auditoria cripto externa, kill -9 ao vivo (recuperação coberta pela suíte:
  `test_recovery_pendente`, `test_update_troca_concorrente`, 412 OK).

## Integração final 1.22 (2026-11-02, ASSINADA)

- Pousado absorvido sem reedição de lógica: rascunho preservado
  (`ses_e64fd1184`: `pagina.py` snapshot txt/para/arquivo no submit, limpa
  cada campo só se o valor atual ainda for o enviado, `atualizarBloqueio()`
  mantém o botão desabilitado enquanto `enviando`, sem reenvio automático;
  `tests/test_ui_preserva_rascunho.py` 16 testes: DOM simulado node com
  resposta atrasada + Chromium headless isolado com digitação-durante-envio
  real; contrato `/api/enviar` intacto) + `TERCEIROS.md` MIT
  (`ses_e64fd117c`: aviso de terceiros na raiz, MIT integral do Bootstrap
  com campos byte-iguais ao header de `bootstrap.min.css`, nada sobre licença
  do SenderMe; `meta.py` 26 arquivos, allowlist do `build_dist.sh`, 6 testes
  `Terceiros` em `test_dist_boot`/`test_update_dist`). Checkpoint/ZIP 1.21
  preservados fora da árvore; stage git da 1.21 mantido, só acrescido.
- Bump `meta.py` 1.21 → 1.22 (1 linha; 1.22 livre confirmado: sem refs, sem
  tags, checkpoints só até 1.21). Assinatura oficial
  `python3 dono/assinar_update.py`: código==manifesto 1.22, 26/26 nomes+hashes,
  sig True. `bash build_dist.sh` release exit 0: `dist/SenderMe` com 27 arquivos
  (26 + manifesto), sem `.git`/`dados`/`dono`/`logs`/`docs`/checkpoints/roteiro/README,
  `TERCEIROS.md` presente, header MIT no css, `VERSAO` 1.22.
- Boot da `dist/` limpa em cópia isolada (`/tmp`, identidade sintética nova,
  portas efêmeras, `SENDERME_NO_BROADCAST=1`, só PID próprio): `/api/eu` →
  1.22, `logado:false`; processo encerrado e cópia removida.
- P2P real 1.21→1.22 (base 1.21 = `dist/` 1.21 desta árvore antes do bump,
  montada em tmp com identidade sintética, chave do dono, loopback,
  `SENDERME_FIXOS` cruzado, só `curl`): B "update v1.22 recebido, baixando
  26 arquivos", aplicou, exit 42, launcher re-executou, `/api/eu` → 1.22 nos
  dois com id de B preservado, `update-manifest.json` A==B v1.22 byte-idêntico
  (retransmite), `TERCEIROS.md` chegou em B, docs 1.21 de B preservados no
  disco (o update nunca apaga), pública A→B `{ok:true, estado:entregue,
  transmitida:true}` entregue e visível em B, 0 canários nos dois diários;
  só PIDs próprios mortos, tmp removido.
- Suíte completa fresca: `python3 -m unittest discover -s tests` → **401 testes
  OK, 0 falhas, 0 skips, exit 0**. Focados UI: `node --check` no JS
  direto + no JS servido via HTTP OK; Chromium isolado (perfil tmp,
  digitar-durante-envio real) OK + `test_ui_preserva_rascunho` 16/16 OK.
- "Atual" em README + docs/01–03; linha 1.21→1.22 na matriz de docs/04;
  `ARQUIVOS_UPDATE` 26 (só runtime + aviso MIT); `ROTEIRO-ESCOLA.md` intacto
  (passos iguais, versão de referência segue 1.21 — sem mudança de passos).
- Não testado aqui: Mint/pendrive físico, rede da escola, 6–20 peers,
  auditoria cripto externa.

## Integração final 1.21 (2026-11-02, ASSINADA)

- Review 1🟡 corrigido sem mudar contrato/estados: `pagina.py` validava nada
  antes de interpolar `m.mid` cru em `href`/`src` via `innerHTML` (linha 261).
  Agora `function midOk(x)` (`^[0-9a-f]{64}$`) guarda os dois usos em
  `bolha()` (link `baixar` e preview `<img>`); `mid` inválido cai no ramo
  `baixando/expirado…` sem link — comportamento p/ `mid` válido é byte-igual.
  +2 testes `MidSeguro` em `tests/test_ui_redesign.py` (regex presente +
  guardas presentes + sonda Node: hostil `"><img src=x onerror=…>` não injeta
  nem renderiza link/img, `mid` hex64 válido ainda renderiza ambos).
- Organização: `SenderMe-checkpoints/` (9 zips, untracked) movido p/
  `Projetos/SenderMe-checkpoints/` via `mv -n` (0 colisões, dir removido);
  `.planning/sender-refactor/` mantido (referência Lane C); nenhum
  `RELATORIO_*`/`arquivos_e_entregas/` na árvore; `shots/` vazio; `.gitignore`
  agora cobre `SenderMe-checkpoints/` (`logs/`/`dist/` já cobertos).
  Auditoria de segredos: `git ls-files` sem `dados/`/`logs/`/checkpoints/`dist`/privada;
  `dono/` rastreia só `assinar_update.py`+`publica.txt`; menções a
  `privada.json` no conteúdo são só referências de caminho; `git log --all`
  tem 1 commit (`24176fa`), sem tags/stash — nenhum valor exposto.
- Bump `meta.py` 1.20 → 1.21 (1 linha; 1.21 livre confirmado: sem refs, sem
  tags, checkpoints só até 1.20). Assinatura oficial
  `python3 dono/assinar_update.py`: código==manifesto 1.21, 25/25 nomes+hashes,
  sig True. `bash build_dist.sh` release exit 0: `dist/SenderMe` com 26 arquivos
  (25 + manifesto), sem `.git`/`dados`/`dono`/`logs`/`docs`/checkpoints/roteiro/README,
  header MIT no css, `midOk` presente, `VERSAO` 1.21.
- Boot da `dist/` limpa em cópia isolada (`/tmp`, identidade sintética nova,
  portas efêmeras, `SENDERME_NO_BROADCAST=1`, só PID próprio): `/api/eu` →
  1.21, `logado:false`; processo encerrado e cópia removida.
- P2P real 1.20→1.21 (base 1.20 do checkpoint `sender-me-1.20-20261101T155106Z.zip`
  preservado fora da árvore, chave do dono, loopback, `SENDERME_FIXOS` cruzado,
  só `curl`): B "update v1.21 recebido, baixando 25 arquivos", aplicou, exit 42,
  launcher re-executou, `/api/eu` → 1.21 nos dois, mesmo id em B, envelope
  A==B v1.21 byte-idêntico (retransmite), docs 1.20 de B preservados no disco,
  pública A→B `{ok:true, estado:entregue, transmitida:true}` entregue e visível
  em B, 0 canários nos dois diários; só PIDs próprios mortos (lanes alheios
  em `/tmp/opencode` intactos), tmp removido.
- Suíte completa fresca: `python3 -m unittest discover -s tests` → **379 testes
  OK, 0 falhas, 0 skips, exit 0** (207 s). Focados UI: `node --check` no JS
  direto + no JS servido via HTTP OK; Chromium isolado (perfis tmp) 2 janelas
  (1280px + 390px, sem overflow, login→app, textarea focável, Enter envia,
  live regions) + `MidSeguro` 2/2 OK.
- "Atual" em README + docs/01–03; linha 1.20→1.21 na matriz de docs/04;
  `ARQUIVOS_UPDATE` 25 (só runtime); `ROTEIRO-ESCOLA.md` com marcadores 1.21
  (passos iguais, allowlist corrigida p/ runtime+manifesto).
- Não testado aqui: Mint/pendrive físico, rede da escola, 6–20 peers,
  auditoria cripto externa.

## Integração final 1.20 (2026-11-01, ASSINADA)

- Pousado absorvido sem reedição de lógica: `diario.py` race (retorno por
  chamada sob lock) + categoria de versão sem dado cru + `tests/test_diario.py`
  27 → 35 testes; `ROTEIRO-ESCOLA.md` na raiz + `docs/05` como apontador +
  `dist/Roteiro-Escola.md` removido + 1 linha no README (DRIFT intencional em
  assinado, absorvido nesta assinatura).
- Checkpoint pré-bump NOVO
  `SenderMe-checkpoints/sender-me-pre-1.20-20261101T154458Z.zip` (79 arquivos:
  lista da 1.18 + `ROTEIRO-ESCOLA.md`, sem privada/dados/logs/.git; NÃO havia
  checkpoint 1.19 na pasta — só até 1.18 e pré-1.18).
- Bump `meta.py` 1.19 → 1.20 (1 linha); "atual" em README + docs/01–03;
  docs/04 intacto (não cita release vigente: cabeçalho datado 1.17 + genéricos
  "release atual"/"versão nova"); `ARQUIVOS_UPDATE` 29, sem mudança.
- Assinatura oficial `python3 dono/assinar_update.py` (2x: pré-validação +
  final após esta entrada; gate refeito): versão código==manifesto 1.20,
  29/29 nomes+hashes, sig True, drift 0.
- Suíte completa: 353 testes OK (345 + 8 do diário), 0 falhas, exit 0;
  focados `test_diario` + `test_update_dist` + `test_dist_boot`: 47 OK, exit 0.
- Release: `dist/` refeita da árvore (gate do `build_dist.sh` passou nos bytes
  finais) + boot da dist via `start.sh` real (1.20 em `/api/eu`, exit 143 no
  SIGTERM); P2P real 1.19→1.20 (base 1.19 do checkpoint pré-1.20, chave do
  dono, loopback, `SENDERME_NO_BROADCAST=1`, `SENDERME_FIXOS` cruzado, só
  `curl`): B aplicou + restart pelo launcher, `/api/eu` → 1.20 nos dois,
  mesma identidade em B, envelope A==B v1.20, pública (`entregue`) e DM
  (`entregue/socket`) A→B entregues, 0 canários nos dois diários; exits
  A=-15 (SIGTERM de limpeza, processo direto) e launcher de B=143, só PIDs
  próprios (lanes alheios em `/tmp/opencode` não tocados).
- JS servido pela 1.20: `node --check` OK (10135 bytes); Chromium headless
  real com perfil tmp isolado: exit 0, DOM 13545 bytes,
  `<title>SenderMe</title>`, 0 `uncaught` (só carga da página de login —
  interação com botões/campos não exercida).
- Kit escola: `dist/SenderMe` limpa (30 arquivos = 29 + manifesto; sem
  roteiro/dados/privada/logs/`__pycache__`); `ROTEIRO-ESCOLA.md` na raiz com
  seção de logs conferindo com `diario.py`/`preboot.py` (principal + 5
  backups ~6 MiB; `preboot.log` teto 256 KiB + `.1`); sem etapa de cópia
  para `dist/` (allowlist só tem runtime + docs/01–03 + manifesto).
- Não testado aqui: Mint/pendrive físico, navegador com interação, rede da
  escola, 6–20 peers, auditoria cripto.

## Correção de logs 1.19 (2026-11-01, ASSINADA)

- 5 itens focados, sem refatoração ampla (só soma comportamento em
  `diario.py`/`preboot.py`/`update_proto.py`/`app.py`/`senderme.py` +
  `tests/test_diario.py` 18 → 27 testes; `ARQUIVOS_UPDATE` 29, sem mudança):
  1. falha pós-abertura (`_ArquivoSeguro` captura write/flush/rotação que o
     `logging` engolia → `registrar()` retorna False + 1 aviso no terminal);
  2. `SENDERME_SEM_LOG=1` desliga também o `preboot.log` (só `os`,
     autonomia preservada); 3a. peers no diário como `peer-N` temporário por
     execução (sem derivar do id permanente); 3b. allowlist
     `CAMPOS_PERMITIDOS` + validação por valor (versão arbitrária da rede
     vira `invalida`; terminal de `tratar_ver` sanitizado via
     `sanear_versao`); 4. `threading.excepthook` seguro (`thread_falha` só
     com tipo + nome sanitizado; traceback só no terminal; limites
     documentados); 5. docs/05 final (coleta `.1`–`.5` + `preboot.log/.1`,
     sem "apague dados/", kit `dist/Roteiro-Escola.md` ao lado da dist) +
     decisão 5e (código mantém `BACKUPS=5`; texto corrigido p/ "principal +
     5 backups, 6 arquivos").
- Assinados tocados: `senderme_app/{diario,preboot,update_proto,app}.py`,
  `senderme.py` (fachada +2), `meta.py` (1.18 → 1.19), README (versão),
  docs/01–03 (versão + contrato 1.19 + diário/roteiro). Fora do manifesto:
  docs/04, docs/05, AGENTS.md, `.gitignore`, testes.
- Assinatura oficial `python3 dono/assinar_update.py`: versão
  código==manifesto 1.19, 29/29 nomes+hashes, sig True (2ª assinatura após
  entrada desta rodada na docs/03; gate refeito).
- Suíte completa: 345 testes OK (336 + 9 do diário), 0 falhas.
- Release: `dist/` refeita da árvore + boot da dist (1.19, 1ª linha
  `boot`, exit 143 no SIGTERM); P2P real 1.18→1.19 (checkpoint 1.18
  preservado fora da árvore, chave do dono, loopback, sem broadcast,
  `SENDERME_FIXOS` cruzado, só `curl`): B aplicado + restart, envelope
  1.19 em B, mesma identidade, pública A→B entregue, 0 canários nos dois
  diários; exits 143/143, só PIDs próprios.
- Não testado aqui: Mint/pendrive físico, navegador real, rede da escola,
  6–20 peers, auditoria cripto.

## Diário em arquivo 1.18 (2026-11-01, ASSINADA)

- Diário persistente (`senderme_app/diario.py`, pousado com hooks em
  `app`/`tcp`/`udp`/`http`/`update`/`update_proto` + `sm.*` + preboot
  autônomo, 18 testes em `tests/test_diario.py`): `VERSAO` 1.17 → 1.18
  (1 linha em `meta.py`); `ARQUIVOS_UPDATE` 28 → 29 arquivos (só soma
  `diario.py`; `start.sh`/`build_dist.sh`/testes já cobriam).
- Assinados tocados: `senderme_app/meta.py` (versão), README.md (versão,
  17 → 18 módulos, +1 linha do roteiro), docs/01 (versão + contrato
  1.18 inalterado + bala do diário), docs/02 (versão + lista 29 + seção
  do diário + `SENDERME_SEM_LOG`), docs/03 (esta entrada). Fora do
  manifesto: `.gitignore` (+=`logs/`), docs/05 (só refs de versão, se
  tocado), AGENTS.md.
- Assinatura oficial `python3 dono/assinar_update.py`: versão
  código==manifesto 1.18, 29/29 nomes+hashes, sig True.
- Suíte completa: 336 testes OK (318 + 18 do diário), 0 falhas.
- Release: `dist/` refeita da árvore + boot da dist; README da árvore ==
  README da `dist/`; P2P real 1.17→1.18 (cópia preservada da 1.17, chaves
  sintéticas, loopback, sem broadcast) com update aplicado e restart.
- Não testado aqui: Mint/pendrive físico, rede da escola, 6–20 peers,
  auditoria cripto.

## Coerência 1.17 (2026-11-01, ASSINADA)

- "atual" 1.15→1.17 em README, docs/01, 02, 04 e AGENTS.md (código+manifesto
  estavam 1.16, docs afirmavam 1.15); histórico abaixo intacto. Sem tocar
  resto do código, testes, scripts, `dono/`, `dados/`, `dist/`, `.git`.
- `senderme_app/meta.py`: `VERSAO` 1.16 → 1.17 (1 linha).
  `ARQUIVOS_UPDATE` inalterada (28 arquivos). Assinatura oficial
  `python3 dono/assinar_update.py`: versão código==manifesto 1.17, 28/28
  nomes+hashes, sig True; suíte zerou o drift (`test_update_dist` voltou a
  passar).
- Assinados tocados: README.md, docs/01-03 (docs/04 e AGENTS.md fora do
  manifesto). Checkpoint pré-edição reutilizado (zip íntegro, fora da árvore
  e de /tmp): `SenderMe-checkpoints/sender-me-1.16-20261101T093821Z.zip`
  (104 arquivos, sem `dados/`/privada/`.git`/`__pycache__`/`dist`/`.planning`,
  `testzip` OK, SHA256
  `1ea57de43a5675abf749875c0d7f8627ff2a9aee687b916dc308fd742a2654ec`).
- Coerência de release (esta assinatura): código==manifesto 1.17, 28/28,
  sig True; `dist/` refeita da árvore + boot; README da árvore == README da
  `dist/`; suíte completa 318 OK.
- Não testado aqui: Mint/pendrive físico, rede da escola, 6–20 peers,
  auditoria cripto.

## Polimento docs 1.15 (2026-11-01, NÃO assinada — código+manifesto seguem 1.14)

- Docs ("atual" em README, docs/01, 02, 04 e AGENTS.md) 1.14→1.15; histórico
  abaixo intacto (a entrada anterior registra o estado de então, resolvido
  pela assinatura vigente). Sem tocar código, testes,
  scripts, manifesto, `dono/`, `dados/`, `dist/`, `.git`.
- Frases transitórias sobre a própria release eliminadas nos 6 arquivos
  (repasse entre lanes, expectativa de assinatura da release vigente).
  Menções restantes a assinatura futura tratam só de itens realmente
  futuros (licença do SenderMe, validações físicas); versões antigas
  restantes só onde são história ou a versão assinada vigente.
- README: atribuição do Bootstrap elevada a seção com o texto integral da
  licença MIT 5.3.3 (`Copyright 2011-2024 The Bootstrap Authors`, do cabeçalho
  do próprio `bootstrap.min.css`); reafirmado que isso NÃO licencia o
  SenderMe (licença do código segue pendente). Sem arquivo novo no protocolo:
  README já é assinado+distribuído.
- Assinados tocados: README.md, docs/01-03 (docs/04 e AGENTS.md fora do
  manifesto). Checkpoint pré-edição íntegro (zip, fora da árvore e de /tmp):
  `SenderMe-checkpoints/sender-me-pre-1.15-20261101T092311Z.zip` (80 arquivos,
  sem `dados/`/privada/`.git`/`__pycache__`/`dist`/`.planning`, `testzip` OK,
  SHA256 `37b83a58063c167d42da56027ffbad0aa1a4aa0621bb43795d496edcbbfbd326`).
- Coerência de release então (resolvido pela 1.15 assinada: código==manifesto
  1.15, 28/28, sig True): código+manifesto na árvore reportam 1.14, 28 arquivos;
  `dist/` ou P2P como 1.15 exige o envelope 1.15 assinado (bump + re-sign +
  build + boot da dist; conferir README da árvore == README da `dist/`).
- Não testado aqui: Mint/pendrive físico, rede da escola, 6–20 peers,
  auditoria cripto.

## Polimento docs 1.14 (2026-11-01, NÃO assinada — código+manifesto seguem 1.13)

- Docs ("atual" em README, docs/01, 02, 04 e AGENTS.md) 1.13→1.14; histórico
  abaixo intacto (1.12 passa a "release anterior"). Sem tocar código,
  testes, scripts, manifesto, `dono/`, `dados/`, `dist/`, `.git`.
- Endurecimento das afirmações de segurança (só reformulação, sem mudar
  comportamento): assinatura de mensagem = autenticidade contra a chave
  conhecida (chaves locais sem PKI, apelido reutilizável), NÃO prova de
  identidade absoluta; assinatura de release = autenticidade via chave
  pública do dono embutida, NÃO criptografia; DMs e tráfego P2P em claro
  na LAN, observáveis localmente (ver `01-produto.md`, `02-arquitetura.md`,
  README).
- Migração/plataformas reconciliadas com `04-migracao.md`: 1.0 sem código
  de update (só via pendrive); 1.1–1.2 aplicam mas o launcher antigo (só
  `senderme.py`+CSS, exit 0 mesmo com falha) exige restart manual com o
  `update-manifest.json` da release nova; FAT32/NTFS/exFAT/`noexec` como
  alvos NÃO validados fisicamente; `bash build_dist.sh` release rejeita
  drift; re-sign só p/ NOVA versão com conteúdo diferente, não a cada build.
- Bootstrap: atribuição registrada no README (5.3.3, MIT © Bootstrap
  Authors, https://getbootstrap.com/); `bootstrap.min.css` intocado;
  licença do SenderMe segue pendente.
- Assinados tocados: README.md, docs/01-03 (docs/04 e AGENTS.md fora do
  manifesto). Checkpoint pré-edição íntegro (zip, fora da árvore e de /tmp):
  `SenderMe-checkpoints/sender-me-pre-1.14-20261101T091156Z.zip` (78 arquivos,
  sem `dados/`/privada/`.git`/`__pycache__`/`dist`, `testzip` OK).
- Pendente então (resolvido pela 1.14 assinada): bump `VERSAO`→1.14 + `python3
  dono/assinar_update.py` + `bash build_dist.sh` release + boot da dist;
  conferir README da árvore == README da `dist/` após gerar a dist.
- Não testado aqui: Mint/pendrive físico, rede da escola, 6–20 peers,
  auditoria cripto.

## Integracao 1.12 (2026-11-01, ASSINADA — release anterior)

- `senderme_app/meta.py`: `VERSAO` 1.11 → 1.12 (1 linha). `ARQUIVOS_UPDATE`
  27 → 28 arquivos (+`senderme_app/update_store.py`). Assinatura oficial
  `python3 dono/assinar_update.py`: versão código==manifesto 1.12, 28/28
  nomes+hashes, sig True; suíte zerou o drift (`test_update_dist` voltou a
  passar).
- Lanes integradas sem reeditar fonte (só reconciliação):
  1. Reoferta diferida (`senderme_app/update_proto.py`: quando o cooldown
     de 10 s suprime a oferta para um peer antigo ainda conectado — ou o
     envio falha com o peer ainda conectado — UMA tentativa diferida é
     agendada para o fim do intervalo (Timer daemon), revalidando
     peer/socket/versão e cancelada no disconnect ou em `ver` que a
     supere; segue 1 oferta por (peer, versão) viva) + gancho em
     `senderme_app/tcp.py` (cancela no fim de `ler_loop` se o peer ficou
     sem conexão viva); `tests/test_update_reoferta_diferida.py`
     (9 testes, incl. espera real do cooldown na mesma conexão e P2P real
     com 1 conexão/1 `ver`/só a 1ª falha injetada).
  2. Split Desenho A (`senderme_app/update.py` 811 → 608 linhas;
     `senderme_app/update_store.py` novo, 227 linhas, folha só-stdlib com
     os helpers fd-fixados extraídos sem mudar lógica, re-exportados por
     `update.py` para compat; `preboot.py` segue 100% autônomo);
     `start.sh`/RUNTIME e allowlist do `build_dist.sh` já cobriam
     `update_store.py`; `tests/test_update_store.py` (5 testes: folha
     pura, re-exports idênticos, preboot autônomo, âncora do alvo SIGKILL
     em `update.py`, roundtrip fd em tmp).
- Sem exceções à meta de 700 linhas: `update.py` (608) e `preboot.py`
  (629, autonomia proposital, não exceção — ver `02-arquitetura.md`).
- Contrato 1.12 (compat com 1.11/1.10): `/api/enviar` intacto; a oferta de
  update ganha a tentativa diferida acima (sem novo campo de protocolo).
- Evidência 1.12: sondas dos lanes verdes antes do bump (9+5); suíte
  completa, build release, boot da dist, P2P REAL 1.11→1.12 normal +
  kill-test e assinatura — ver relatório 1.12 arquivado.
- Pendente (não testado aqui): Mint/pendrive físico, rede da escola, 6–20
  peers, auditoria cripto.

## Integracao 1.11 (2026-11-01, ASSINADA — release anterior)

- `senderme_app/meta.py`: `VERSAO` 1.10 → 1.11 (1 linha). `ARQUIVOS_UPDATE`
  26 → 27 arquivos (+`senderme_app/update_proto.py`). Assinatura oficial
  `python3 dono/assinar_update.py`: versão código==manifesto 1.11, 27/27
  nomes+hashes, sig True; suíte zerou o drift (`test_update_dist` voltou a
  passar).
- Lanes integradas sem reeditar fonte (só reconciliação):
  1. Núcleo: guards `lexists` no marcador, reoferta com cooldown (marca
     1x por peer/versão em conexão viva só após envio confirmado; falha
     nunca marca; morte da conexão reoferta no próximo `ver`; `ver`
     repetida após falha recente respeita cooldown de 10 s; chunks
     faltantes repedidos em rodadas), split proto-only
     (`update_proto.py` 258 linhas, protocolo/transferência sem mudar
     lógica; `update.py` 989 → 811; `preboot.py` 629, autônomo);
     `start.sh`/`build_dist.sh` atualizados (RUNTIME/allowlist cobrem
     `update_proto.py`).
  2. Contrato: `nivel` ∈ {`local`,`socket`} + `confirmado=false` + `peers`
     em `/api/enviar` (compat: campos novos opcionais, antigos intactos),
     UI honesta por caso (ver `01-produto.md`, contrato 1.11).
- Falta deste lane (fonte editada aqui): `senderme_app/udp.py` suprime o
  broadcast com `SENDERME_NO_BROADCAST=1` (unicast preservado; default-off);
  harnesses (`test_update_e2e_abc`, `test_e2e_peers`,
  `test_update_marcador_pendente`) e `test_dist_boot.BootReal` exportam a
  var. Sonda dedicada: com a var 0 broadcasts + unicast OK; sem a var
  broadcast normal (relatório 1.11 arquivado).
- Evidência 1.11: suíte 304 testes OK exit 0 (sem skips); `compileall` +
  `bash -n` + `node --check` no JS servido OK; `bash build_dist.sh` exit 0;
  P2P REAL 1.10→1.11 (instalação 1.10 do checkpoint
  `sender-me-pre-1.11-20261101T061034Z.zip` + dist 1.11, identidades
  sintéticas, assinatura real): A aplicou, exit 42, restart, `/api/eu`
  1.11, manifesto A==B, DM pós-restart; interrupção (kill -9 com
  `atualizando=true` → sem marcador, preboot exit 0, boot 1.10 íntegro,
  retry aplica 1.11) + recuperação/reinício cobertos em
  `test_recovery_pendente` + `test_update_falhas` + `test_update_e2e_abc`;
  relatório 1.11 arquivado.
- Pendente (não testado aqui): Mint/pendrive físico, rede da escola, 6–20
  peers, auditoria cripto.

## Integracao 1.10 (2026-11-01, ASSINADA — release anterior)

- `senderme_app/meta.py`: `VERSAO` 1.9 → 1.10 (1 linha). `ARQUIVOS_UPDATE`
  inalterada (26 arquivos). Assinatura oficial `python3 dono/assinar_update.py`:
  versão código==manifesto 1.10, 26/26 nomes+hashes, sig True; suíte zerou o
  drift (`test_update_dist` voltou a passar).
- Lanes integradas sem reeditar fonte (só reconciliação):
  1. Marcador/tmp Opção B (sem módulo novo): `update.py` (989 linhas) +
     `preboot.py` (610 linhas) abrem `.upd-pendente.json.tmp`,
     `update-manifest.json.tmp` e `update-manifest.json.upd-tmp` por `openat`
     fd-relativo `O_NOFOLLOW` + pós-cheque; em corrida, False + journal
     preservado + mensagem honesta. `tests/test_update_marcador_tmp.py`
     (3 testes, gancho por basename no `os.open` O_CREAT).
  2. `transmitida` no backend: `enviar_dm_para`/`tratar_comando_web` com
     `com_estado=True` retornam a 4-tupla `(ok, msg, estado, transmitida)`;
     `/api/enviar` expõe `transmitida` no JSON (`tests/test_dm.py`, 24;
     `+Transmitida` em `tests/test_api_contrato.py`).
  3. UI bloqueio de reenvio: `transmitida=true`+`somente_memoria` → aviso sem
     alegar recebimento, texto mantido, `btnEnviar` desabilitado p/ o idêntico
     até editar (`tests/test_pagina_avisos.py`, 22).
- Contrato 1.10: `transmitida=true`+`somente_memoria` → aviso sem alegar
  recebimento, texto mantido, reenvio idêntico bloqueado até editar.
- Evidência 1.10: suíte 266 testes OK exit 0 (sem skips); `compileall` +
  `bash -n` + `node --check` no JS servido OK; `bash build_dist.sh` exit 0;
  P2P REAL 1.9→1.10 (instalação 1.9 do checkpoint
  `sender-me-pre-1.10-20261101.zip` + dist 1.10, identidades sintéticas,
  assinatura real): A aplicou, exit 42, restart, `/api/eu` 1.10, manifesto
  A==B, DM pós-restart; interrupção+recuperação via marcador cobertas em
  `test_recovery_pendente` + `test_update_falhas`; relatório 1.10 arquivado.
- Pendente (não testado aqui): Mint/pendrive físico, rede da escola, 6–20
  peers, auditoria cripto.

## Integracao 1.9 (2026-10-31, ASSINADA — release anterior)

- `senderme_app/meta.py`: `VERSAO` 1.8 → 1.9 (1 linha). `ARQUIVOS_UPDATE`
  inalterada (26 arquivos). Assinatura oficial `python3 dono/assinar_update.py`:
  versão código==manifesto 1.9, 26/26 nomes+hashes, sig True; suíte zerou o
  drift (`test_update_dist` + `test_migracao_manual` voltaram a passar).
- Lanes integradas sem reeditar fonte (só reconciliação):
  1. UI decide por `r.estado` {entregue,guardada→limpa; somente_memoria,erro→
     preserva} + fallback legado sem estado (`pagina.py`,
     `tests/test_pagina_avisos.py`, 14 testes; sonda UI do ZIP passa como está).
  2. TOCTOU: `update.py` (959 linhas — exceção documentada em `02`) com
     helpers fd-fixados openat/O_NOFOLLOW + fail-closed sem suporte;
     `preboot.py` com duplicação proposital (nunca importa `senderme_app`);
     `tests/test_update_troca_concorrente.py`. Sonda symlink do ZIP adaptada
     (gancho por basename: a promoção agora usa `os.replace` com basenames +
     dir_fd) sem enfraquecer — externo intacto + hook atingido; suíte fixa
     ainda retorno False + journal + mensagem honesta (sem "revertida").
  3. HEAD+estado: `_json` sem corpo p/ HEAD (status+`Content-Length`, zero
     bytes); `/api/enviar` inclui `estado`; `enviar_dm_para`/`tratar_comando_web`
     com `com_estado` opcional (compat 2-tupla); sonda HEAD do ZIP passa.
- Evidência 1.9: suíte 244 testes OK exit 0 (sem skips); `compileall` +
  `bash -n` + `node --check` no JS servido OK; `bash build_dist.sh` exit 0
  (dist 26 runtime + manifesto, sem `dados/`/`dono/`/`.git`); P2P REAL 1.8→1.9
  (instalação 1.8 do checkpoint `sender-me-pre-1.9-20261031.zip` + dist 1.9,
  identidades sintéticas, assinatura real): A aplicou, exit 42, restart,
  `/api/eu` 1.9, manifesto+26/26 iguais a B, DM pós-restart `estado=entregue`;
  Chromium real isolado (perfil tmp) 2/2 em `test_pagina_avisos`.
- Incidente de teste (sem dano): 2ª tentativa P2P rodou no diretório real por
  `cd` em subshell (`&&...&`); processos mortos em ~2 min; `dados/` real
  intacto (mtimes 29/30-10, sem escrita); relatório 1.9 arquivado.
- Pendente (não testado aqui): Mint/pendrive físico, rede da escola, 6–20
  peers, auditoria cripto.

## Consolidacao 2026-10-31 (v1.8 pronta, NAO assinada — manifesto vigente segue 1.7)

- `senderme_app/meta.py`: `VERSAO` 1.7 -> 1.8 (default; `SENDERME_VERSAO`
  continua sobrescrevendo em teste e **nao conta como release**).
  `ARQUIVOS_UPDATE` inalterada (26 arquivos). Nada assinado nesta sessao;
  `update-manifest.json` permanece o 1.7 oficial ate a assinatura oficial.
- Lanes da rodada (codigo dos lanes revisado em paralelo; aqui so o registro):
  1. `build_dist.sh`: gate de release + `--dev` (sem `--dev`, qualquer drift
     reprova com erro + exit != 0; com `--dev`, drift vira aviso e a saida
     sai marcada DEV, nunca "OK").
  2. `pagina.py`: avisos UI + sem-duplicata (`tests/test_pagina_avisos.py`,
     9 testes).
  3. `senderme_app/update.py` + `senderme_app/preboot.py`: contencao
     anti-symlink fail-closed + limites TOCTOU/FAT32 documentados
     (`tests/test_update_symlink.py`, 6 testes).
  4. `senderme_app/http.py`: `Host` conferido tambem em GET/HEAD; leitura
     fora da origem = 403 sem vazar bytes; `curl`/scripts locais com `Host`
     correto passam (`tests/test_host_get.py`, 12 testes).
- Drift manifesto 1.7 x disco (pendente da mesma re-assinatura, agora como
  release 1.8): `update.py`, `http.py`, `preboot.py`, `start.sh`,
  `build_dist.sh`, `pagina.py`, `senderme_app/meta.py` (só o bump),
  `docs/01/02/03/04`. `test_update_dist` + `BuildDist` DEVEM continuar
  falhando ate a assinatura oficial — deteccao funcionando como projetada,
  nao regressao; nao afrouxar expectativas.
- Checkpoint pre-rodada verificado e integro (gzip -t OK):
  `SenderMe-checkpoints/sender-me-pre-rodada-20261031.tar.gz` (nao recriado).
- Migracao: sem snapshot historico autentico nesta sessao (`SENDERME_VERSAO`
  nao conta como base historica); limitacao registrada em `04-migracao.md`.
- Assinatura 1.8 (comando oficial a autorizar, NAO executado):
  `python3 dono/assinar_update.py` — ver lista/hashes em
  `RELATORIO_RODADA_ATUAL.md` (arquivado).

## Situação atual (2026-10-31, v1.7 + lane compat/dist/docs — drift parcial, re-assinatura pendente)

- Lane compat/dist/docs (sem re-assinar com a chave real; sem bump de
  `VERSAO`, ainda 1.7): checkpoint em
  `/tmp/opencode/sender-me-pre-compat-20261031.tar.gz` (64 arquivos, sem
  `dados/`/privada/`.git`/caches/`dist`, SHA256
  `5871f732b343232d5c0b2413d61bf1f637b27e0a98a8755c8955ff95937433bc`).
- `start.sh`: fallback R1 estendido a subdir (`find senderme_app -name
  '*.py'`, R1b) — antes, subdir novo no disco não subia para `/tmp`
  (confirmado em teste real com sonda); regressão permanente
  `test_dist_boot.LauncherCopiaEExit.test_subdir_novo_no_disco_sobe_para_tmp`
  (vermelho antes, verde depois). `bash -n` OK. RUNTIME cobre os 20 `.py`;
  `bootstrap.min.css` vai em cópia separada (contrato total confere com os
  21 py/css de `ARQUIVOS_UPDATE`, verificado por script).
- `build_dist.sh`: allowlist confere arquivo a arquivo com
  `ARQUIVOS_UPDATE` + `update-manifest.json` + docs/01-03 (verificado por
  script; sem faltas nem sobras). `dist/` sem segredos (parte do `BuildDist`
  que confere conteúdo continua verde).
- **Drift manifesto 1.7 × disco (re-assinatura oficial PENDENTE)**:
  `senderme_app/update.py`, `senderme_app/http.py`,
  `senderme_app/preboot.py` (lanes anteriores) + `start.sh`,
  `docs/02-arquitetura.md`, `docs/03-progresso.md` (este lane).
  `test_update_dist` + `BuildDist` falham nesses arquivos — detecção
  funcionando como projetada, não regressão. Release com esse conteúdo
  exige bump de versão (nunca reutilizar 1.7) + `dono/assinar_update.py`
  oficial; até lá, sem `dist/` nem P2P como release.
- Docs: `04-migracao.md` (matriz com linha 1.6→atual não-executável, regra
  de restart manual, drift×adulteração, skips sem git, avaliação de
  fixtures sanitizadas ~100 KB documentada como não-incluída);
  `02-arquitetura.md` (bloco `start.sh` atualizado); docstring de
  `test_migracao_manual.py` sem "1.6" fixo (usa `meta.VERSAO`). `01-produto`
  intacto (sem drift novo) e `04` é repo-only (fora do manifesto). Edições
  em 02/03 (agora em drift listado acima) e `start.sh` — esperado, aguarda
  a mesma re-assinatura.
- Fixtures históricas: sem `git show 24176fa` os 2 testes de migração
  pulam (`skipTest` — limitação documentada em `04`, não sucesso).
- Não validado (segue): Mint/FAT32 físico, broadcast escolar, carga 6–20,
  auditoria cripto, restart real entre releases reais, 1.6→atual byte-exata
  (sem árvore 1.6 no repo), loop `baixar_update` sob stall/timeout.

## Situação em 2026-10-31 (v1.7 — lanes R1–R7 + preboot no manifesto, histórico)

- v1.7 = v1.6 + correções das 4 lanes (R1–R7: update/launcher/preboot novo,
  identidade `null`, CSRF host+porta, migração com manifesto) + `preboot.py`
  no manifesto (26 arquivos; a 1.6 assinada listava 25 — era o drift que
  deixava as 2 únicas falhas da suíte). Manifesto 1.7 re-assinado pelo
  processo oficial (`python3 dono/assinar_update.py`, 26 arquivos).
- Menções de "versão atual" 1.6→1.7 (README, docs/01, docs/02, docs/04,
  AGENTS.md); histórico datado abaixo preservado.

## Situação em 2026-10-31 (v1.6 — backup atômico do updater, histórico)

- v1.6 = v1.5 + backup atômico do updater (`update.py`: tmp+`os.replace`,
  volta restaura só backups concluídos, teste de regressão em
  `tests/test_update_falhas.py`) + matriz A→B→C em `docs/04` citando
  `test_update_e2e_abc` (exit 42 + `start.sh` real saem dos não-testados).
  Manifesto 1.6 re-assinado pelo processo oficial
  (`python3 dono/assinar_update.py`, 25 arquivos, sem mudar a lista).
- Menções de "versão atual" 1.5→1.6 (README, docs/01, docs/02, docs/04);
  histórico datado abaixo preservado.

## Situação em 2026-10-31 (v1.5 — relançamento pós-lanes, histórico)

- v1.5 = v1.4 + correções das 3 lanes (arquivos assinados mudaram sem
  re-assinar → drift de hash em `docs/02-arquitetura.md`; reutilizar 1.4 é
  proibido pois mesma versão é rejeitada). Manifesto 1.5 re-assinado pelo
  processo oficial (`python3 dono/assinar_update.py`, 25 arquivos, sem mudar
  a lista). Conteúdo das lanes: `update.py` (rollback/manifesto, TDD verde),
  `http.py` (gate userinfo/esquema + testes) + seção CSRF em `docs/02`,
  `tests/test_migracao_manual.py` + `docs/04`.
- Menções de "versão atual" 1.4→1.5 (README, docs/01, docs/02, docs/04,
  AGENTS.md); histórico datado abaixo preservado.

## Situação em 2026-10-31 (v1.4 — ressalvas + relançamento, histórico)

- v1.4 = v1.3 + correções das ressalvas (8 arquivos próprios à frente do
  manifesto v1.3 assinado → drift de hash; reutilizar 1.3 é proibido pois
  mesma versão é rejeitada). Manifesto 1.4 re-assinado pelo processo oficial
  (`python3 dono/assinar_update.py`, 25 arquivos, sem mudar a lista).
- Fix pendente `app.py`: bool de `reescrever_historico()` descartado na
  `purgar()` — agora propaga/loga como os demais pontos de persistência
  (sem mudar formato em disco).
- Testes `test_dist_boot`/`test_migracao_legada` deixaram de fixar "1.3"
  literal (versão dinâmica de `senderme_app/meta.py`).

## Situação em 2026-10-31 (v1.3 — refatoração + correções, histórico)

- `senderme.py` monolito (2463 linhas) dividido por responsabilidade real:
  entrada fina (~130 linhas, compat `sm.*` via re-export + delegação de
  estado) + `senderme_app/` com 14 módulos (todos ≤700 linhas, medido).
  `pagina.py` NÃO desmembrado (decisão: duplo escape contido, offline OK,
  churn em launcher/build/manifesto não compensava; reavaliar se o JS crescer).
- Defeitos corrigidos (cada um com teste que falhava antes e passa depois):
  identidade corrompida/falha-escrita (`persist.py`), update com flag presa +
  pacote parcial + envelope não persistido (`update.py`: staging/backup/
  marcador/recuperação no boot, `finalizar_update()` retorna bool, exit 42 só
  no fio do `baixar_update`), CSRF na API (`http.py`: Origin/Referer externo
  → 403), `start.sh` (copia RUNTIME completo, `trap` limpa, não-42 propaga).
- Fonte única: `ARQUIVOS_UPDATE` em `senderme_app/meta.py` (25 arquivos) —
  start.sh/build/assinador/testes conferem contra ela. Manifesto 1.3
  re-assinado pelo processo oficial (`dono/assinar_update.py`).
- Suíte: 95 testes antigos verdes (2 adaptações mínimas de costura:
  `test_nicks`→patch em `manut`, `test_purga`→teto em `arquivos`) + ~25 novos
  (identidade, update red→green, CSRF, fluxo sintético, dist/boot, migração
  legada, 2 peers E2E). `node --check` no JS servido OK; `bash -n` OK.
- Migração ≤1.2: P2P baixa/aplica mas o launcher antigo não reinicia
  (demonstrado com o `start.sh` real do 24176fa: `ModuleNotFoundError` + exit
  0); caminho manual = rodar o novo `start.sh` (testado na mesma cópia).
  A→B→C com envelope+hashes verificado (chave sintética). Detalhes e matriz
  em `04-migracao.md`.
- Não verificado: navegador interativo, Mint/FAT32 real, broadcast da escola,
  carga 6–20, auditoria cripto. Release 1.3 assinada em 2026-10-31, superada pela 1.4 (drift corrigido por bump+re-assinatura). **Nada publicado**.

## Situação em 2026-10-30 (v2 navegador pronta, histórico)

- [x] v1 terminal feita e testada (ver histórico abaixo).
- [x] Requisitos **v2 navegador** fechados (ver `01-produto.md` v2).
- [x] Arquitetura **v2** anotada (ver `02-arquitetura.md` v2).
- [x] **`senderme.py` reescrito p/ web** (2179 linhas, stdlib, `py_compile` OK).
- [x] `bootstrap.min.css` 5.3.3 local (~228 KB, offline).
- [x] `start.sh` atualizado (copia py+css, `xdg-open` sozinho, `bash -n` OK).
- [x] `README.md` atualizado p/ v2.
- [x] Testes v2 no mesmo PC — **ver lista nova abaixo**.

**Estado da pasta:** `docs/`, `senderme.py` (v2), `bootstrap.min.css`, `start.sh`,
`README.md`, `dados/` real intacto (689 eventos). Pasta ~866 KB (< 80 MB).

## O que foi testado na v2 (2026-10-30, instâncias reais via HTTP API)

1. **Subida**: A (13337/13338/13336) + B (13347/13348/13346) com `SENDERME_FIXOS`
   cruzado; `/api/eu` com `precisa_login:true`, login `alice`/`bob` OK.
2. **Nomes distintos**: `/quem` com 2 presentes, `alice` ≠ `bob` (bug v1 não
   reproduziu; fix `nick_ts` + teste unitário velho-ignorado OK).
3. **Msg + multilinha**: `linha1\nlinha2\nlinha3` preservado nos dois lados;
   `join` dos dois lados visível.
4. **DM texto**: A→B só B vê (e A vê a própria); C (3ª instância, entrou depois)
   **não** recebe DM (nem texto nem arquivo).
5. **Comandos**: `/ajuda`, `/rede`, `/quem` OK; `/sair` retorna "removido, use
   Ctrl+C"; conflito `/apelido alice` bloqueado; `/apelido beto` propagou
   `* bob agora é beto`; `/calar` toggle filtrou e descalou; `/api/calados` OK.
6. **Arquivo global 100 KB**: upload A → B `pronto:true`, download bytes
   idênticos (`cmp` OK); C sincronizou metadados + conteúdo (`pronto:true`,
   `cmp` OK).
7. **Arquivo DM**: A→`@beto` só B vê com `dm:true`; C não vê.
8. **Limite 20 MB**: upload 21 MB rejeitado `413/“máx. 20 MB”`.
9. **Persistência**: `apelido.txt` salvo; cópia do HOME religa com
   `logado:true, precisa_login:false`, mesmo id, histórico carregado.
10. **Evicção**: 75 MB recentes → purga deixa 50 MB (2 mais novos); >48h apaga.
11. **Web**: `/` retorna HTML, `/bootstrap.min.css` 200 ~232 KB.
12. **`bash start.sh`**: com dados reais (689 eventos, `thomaskyn`) subiu,
    auto-login, web OK. `start.sh` força `SENDERME_HOME=$APP_DIR` (teste isolado
    usa `python3 senderme.py` direto com `SENDERME_HOME=/tmp/...`).

## Auditoria final (2026-10-30, antes da entrega)

- Compila (`py_compile`), sem `eval/exec/system/pickle`.
- Corrigidos: re-`/api/login` com outro nome emite evento `nick`; `nome` de
  arquivo sanitizado e validado + `sha256` hex.
- Borda OK: login vazio/longo/conflito case-insensitive, enviar sem login,
  comandos inválidos, `/dm`/`/calar` erros, `/sair`/`/limpar` removidos,
  upload sem file/vazio/>20MB (413), download 400/404, path traversal virou
  `evil.txt`, binário terminado em CRLF intacto, msg 3000→2000, XSS cru na API
  + `esc()` no cliente, evento adulterado/sig inválida/file 21MB/nome `../x`
  rejeitados, `nick_ts` velho ignorado.
- P2P OK: 5 MB multi-chunk idêntico em B e em C tardio; DM nunca vaza p/ C;
  3 presentes; persistência auto-login mesmo id; purga 75→50 MB; falha de bind
  TCP sai com mensagem (sem P2P fantasma).
- Pós-entrega (bug reportado pelo usuário: botão Entrar não fazia nada):
  `SyntaxError` por chave `}` sobrando no `onclick` do descalar (linha do
  `configs()`), validado com `node --check` na página servida; removido
  `sourceMappingURL` do `bootstrap.min.css` (404 do `.map`); rota desconhecida
  agora retorna 404 em vez de fechar a conexão.

## v1.1 (atraso longo, merge Lego, DM offline, update assinado, dist)

- Diagnóstico do "atraso longo": throttle da redelivery queimava antes da DM
  existir (tentativa sem pendente marcava 120 s); corrigido (só marca com pendente
  + ignora próprio id). Sockets com `TIMEOUT_SOCK=15 s` (nada trava: HTTP, gossip
  e redelivery). Peer exchange (`peers_req/peers` + `sementes`), `ping/pong` 5 s,
  limpeza de cadáveres, `receber_pub` rejeita própria chave, sem auto-dial.
  Browser com timeout/abort, `poll` imortal, texto mantido em falha, selo de estado.
- Merge Lego: `hist_req` com inventário `têm` (5000 mids); varredura de arquivos
  2/ciclo; DM offline via redelivery direta (sem gossip, dedupe por `mid`).
- Update: `VERSAO`, `CHAVE_DONO`, `dono/assinar_update.py` → `update-manifest.json`,
  protocolo `ver/meta/get/chunk`, auto-serve + auto-apply + exit 42 + loop no
  `start.sh`; nick transfere se dono offline; `presente()` respeita `leave`.
- Testes v1.1: redelivery confirmada após janela ("DMs pendentes entregues");
  update 1.0→1.1 fim-a-fim (meta servida, 7 chunks, sha OK, exit 42); reuso de
  nick pós-wipe (login livre + transferência, `(2)` só com dois online);
  regressão (msg/arquivo/DM/presentes); `dist/` idêntica ao projeto, sem
  `dados/`/`dono/` (368K).
- Debug real da redelivery: throttle queimava antes da DM existir (fix: só marca
  com pendente + ignora próprio id); auto-dial via seeds (fix: rejeita própria
  chave + nunca disca a si); `TIMEOUT_SOCK=15 s`; `update_get` de `docs/` era
  barrado pelo anti-traversal (fix: `nome_update_ok`); manifest re-assinado.

## O que já foi testado (2026-10-29, no PC de desenvolvimento)

Todos com instâncias reais, entradas/saídas por FIFO, saída capturada:

1. **Instância única** — geração da chave na 1ª execução, banner, `/ajuda`,
   `/quem`, mensagem normal, `/sair`, arquivos em `dados/` criados com
   `identidade.json` em `600`.
2. **Duas instâncias** (`13337`/`13347` + `SENDERME_FIXOS=127.0.0.1:...`):
   descoberta por fixo, `join` dos dois lados, mensagem nos dois sentidos,
   `/quem` (2 presentes), `/rede` (2 conexões por par), `/dm` (só o destino
   mostrou), `/apelido`, `/calar` (a pessoa calada deixou de aparecer), `/sair`
   → `leave` no outro lado.
3. **Três instâncias** — o C entrou **depois** e **sincronizou o histórico**
   (cabeçalho `* histórico sincronizado: N eventos das últimas 48h` + mensagens
   antigas), `/quem` com 3 presentes, **DM de A para B invisível para C**
   (e sem `dm` no `historico.jsonl` do C), `leave` do C propagado para A e B.
4. **Conflito de apelido** — C tentou entrar com `alice` (em uso) e foi
   **bloqueado** antes de escolher `carol`; `alice` tentou `/apelido bob`
   (em uso) e foi **bloqueado**; `/apelido ze` funcionou e o histórico dos
   outros mostrou o nome novo.
5. **Purga de 48 h** — `purgar()` chamada direto: evento de 60 h sai do
   arquivo e do `vistos`, o de 1 h fica.
6. **`bash start.sh`** — copiou para `/tmp`, rodou com `SENDERME_HOME`
   apontando para a pasta original, dados saíram na pasta certa e o `trap`
   limpou o `/tmp` (exit 0).

### Bugs encontrados e corrigidos nesses testes

- Nossos próprios eventos não passavam na verificação: `conferir_evento`
  consultava só `conhecidos` e não achava **a própria chave** → corrigido.
- `socket.socket` **não aceita atributos novos** (`AttributeError: '_lck'`):
  o trava-de-envio por socket foi movida para um dict global `envios_lck`.
- Histórico sincronizado perdia eventos de terceiros (chave ainda desconhecida
  → ficava em `pendentes` e era exibido depois, fora de ordem): agora o
  pacote `hist` **carrega as chaves públicas dos autores** (`pubs`).

## O que FALTA testar

1. **Rede real com 2 PCs do Mint.** Conferir firewall (`ufw` costuma vir
   inativo; se pedir permissão, permitir). Verificar **broadcast UDP 13338**
   (é o teste que os `SENDERME_FIXOS` não cobrem).
2. **Cópia para pendrive FAT32/NTFS** e `bash start.sh` com `noexec`.
3. **Sair e voltar** (rejoin) com gente online: deve mostrar `saiu` e depois
   `entrou` de novo.
4. Purga em uso real (esperar os 600 s ou chamar `purgar()`).

## Pendências / escolhas que podem virar decisão do usuário

- Cor de fundo/estilo do terminal: não especificado, usei cores ANSI simples
  (hora esmaecida, apelido colorido por hash do id, DM em magenta).
- Nomes exibidos em `/rede`: IP, porta e id curto (8 hex).
- Na sincronização, mostra o cabeçalho + **até 30 mensagens antigas** por
  lote (`MAX_HIST_EXIBIDO`); o resto fica só no arquivo/estado.
- `hist` é pedido **dos dois lados** de cada conexão — dá 2 cabeçalhos de
  sincronização quando os dois tinham coisa nova (cosmético, sem duplicar).
- Limite de texto por mensagem: 2000 chars (`MAX_TEXTO`), truncado na envio.
- Sem rate limit/antispam: rede de confiança, conforme `02-arquitetura.md`.
- `SENDERME_DEBUG=1` liga diagnósticos de conexão (dial/aceite/handshake).

## Constantes ajustáveis (`config.py`; `VERSAO`/chave/manifest em `senderme.py`)

```
PORTA_TCP=13337 PORTA_UDP=13338 PORTA_HTTP=13336 RETENCAO=48h TIMEOUT_OFFLINE=12s
JANELA_ENTRADA=90s JANELA_SAIDA=60s INTERVALO_ANUNCIO=3s INTERVALO_PURGA=600s
TIMEOUT_DIAL=10s MAX_QUADRO=8MB MAX_TEXTO=2000 MAX_SYNC=1000
MAX_ARQUIVO=20MB MAX_ARQUIVOS_TOTAL=60MB CHUNK_ARQ=512KB
```

## Como testar duas instâncias no mesmo PC (v2)

```bash
SENDERME_HOME=/tmp/sm-a SENDERME_PORTA=13337 SENDERME_UDP_PORTA=13338 SENDERME_HTTP=13336 \
  SENDERME_FIXOS=127.0.0.1:13347 python3 senderme.py
# em outro terminal:
SENDERME_HOME=/tmp/sm-b SENDERME_PORTA=13347 SENDERME_UDP_PORTA=13348 SENDERME_HTTP=13346 \
  SENDERME_FIXOS=127.0.0.1:13337 python3 senderme.py
# abra http://127.0.0.1:13336 e http://127.0.0.1:13346
```

## Resumo rápido para quem vai continuar

App P2P em Python 3 puro (sem deps): `senderme.py` (P2P + HTTP + página) +
`bootstrap.min.css` local + `start.sh` (copia p/ `/tmp`, `SENDERME_HOME` no
pendrive, abre browser). RSA-2048 próprio, ID = fingerprint. TCP 13337 P2P,
UDP 13338 descoberta, HTTP 127.0.0.1:13336 local. Flood por `mid`, sync 24h
(`hist` + `pubs`, persistência em lote), arquivo `file` com chunks 512 KB
(`file_req/chunk`, teto 60 MB + 24h), DM texto+arquivo direta, `/calar` por id,
nick `nick_ts` last-write-wins, login persistente (`apelido.txt`) + aba Configs.
Polling 0,7 s, data+hora `DD/MM HH:MM`. Dados no pendrive em `dados/`
(+`arquivos/`). Mint, 6–20 pessoas.

Estrutura (pós-lane D, out/2026): `config.py` (constantes) → `crypto.py`
(RSA/fingerprint) → `senderme.py` (estado + armazenamento + eventos/nicks +
processamento + TCP/UDP/manutenção + comandos web + formatação/API + HTTP +
main) → `pagina.py` (`PAGINA`, só dados, importada). Núcleo com estado fica
em `senderme.py` de propósito: os testes usam `import senderme` como casa do
estado (`suporte.py` lê/escreve `sm.*`, inclusive muta `sm.MAX_ARQUIVOS_TOTAL`),
e o assinador do dono prende `VERSAO` (regex) e `ARQUIVOS_UPDATE` (=7,
manifesto assinado) a este arquivo — ver `02-arquitetura.md`.

## v1.2 — retenção 24h, data+hora, sync mais rápido

- `RETENCAO` 48h → **24h** (uma constante cobre purga, sync, DM offline e arquivos).
- `hora_de` agora `DD/MM HH:MM` (antes só `HH:MM`).
- Polling do navegador 1,5 s → **0,7 s**.
- `tratar_hist` persiste o lote com **uma escrita** (`anexar_lote`;
  `processar(..., disco=False)`); P2P medido a 24 ms/msg, sync de 700 msgs <0,5 s.

## Lane D — refatoração modular, folhas extraídas (2026-10-30, sem commit)

- Extraído em 3 incrementos, verde entre eles (92 testes, exit 0 a cada passo):
  1. `crypto.py` (RSA/fingerprint puros; `gerar_chave` sem log, `senderme`
     avisa e delega); 2. `config.py` (portas/janelas/limites via env);
  3. `pagina.py` (`PAGINA` byte-idêntica: runtime igual ao monolito do HEAD).
- `senderme.py` virou ponto de entrada fino-compatível (~80 KB): re-exporta
  (`sm.*` intacto p/ testes e `dono/assinar_update.py`), mantém `VERSAO`
  (regex do assinador), `CHAVE_DONO`, `ARQUIVOS_UPDATE` (=7) e `os._exit(42)`
  literais; núcleo com estado não moveu (contrato dos testes + assinador).
  Novo: `python3 senderme.py --help` (uso/versão, sem subir servidor).
- `start.sh` copia os 4 `.py` (+css) p/ `/tmp`; `build_dist.sh` inclui os 4
  na `dist/` (376K, `cmp` byte-identical, sem `dados/`/`dono/`/`__pycache__`).
- Manifesto re-assinado a cada incremento pelo processo oficial
  (`python3 dono/assinar_update.py`, v1.2, 7 arquivos) — suíte exige bytes.
- Verificado: `py_compile`, 92 testes OK, 2 instâncias isoladas (login
  alice/bob, msg multilinha A→B, presentes 2/2), página servida == `PAGINA`,
  `node --check` no JS extraído OK, boot a partir de `dist/` via `start.sh`
  (id novo, `/api/eu` OK).
- **Pendente (dono, histórico 2026-10-30 — RESOLVIDO em 2026-10-31)**: estender
  `ARQUIVOS` em `dono/assinar_update.py` p/ os módulos + re-assinar. Feito na
  1.3: assinador lê `senderme_app/meta.py` (fonte única, 25 arquivos),
  manifesto re-assinado, update P2P íntegro para o runtime em pacote.
