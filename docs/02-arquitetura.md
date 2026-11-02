# SenderMe — Arquitetura e Decisões Técnicas (v2 navegador, 1.23)

> Escolhas do desenvolvedor, alinhadas com `01-produto.md` (v2).
> Se mudar algo aqui, atualizar também `03-progresso.md`.

## Linguagem e runtime

- **Python 3 puro, só biblioteca padrão.** Zero dependências externas.
  - Pendrive roda em qualquer Mint sem instalar nada.
  - Medido: `senderme.py` ~80 KB + `config.py`/`crypto.py`/`pagina.py` ~16 KB
    + `bootstrap.min.css` ~228 KB. Pasta < 80 MB.
- Arquivos do app (fonte única da lista: `ARQUIVOS_UPDATE` em
  `senderme_app/meta.py`; `start.sh`, `build_dist.sh`, assinador e testes
  conferem contra ela — 26 arquivos, só runtime (README/docs/roteiro fora
  do conjunto desde a lane redesign+dist; lista da 1.22 = 1.21 mais TERCEIROS.md):
  - `senderme.py` — ponto de entrada fino + compat `import senderme as sm`
    (re-exporta o contrato público; estado via delegação a `estado`).
  - `senderme_app/` — um módulo por responsabilidade: `meta` (versão, chave
    pública, lista do update), `estado` (dono único do estado mutável e
    locks; acesso sempre `S.x`), `persist` (identidade/histórico),
    `presenca` (apelidos/presença), `eventos` (validação/processo/sync),
    `arquivos` (anexos/chunks), `transporte`+`tcp`+`udp` (rede),
    `manut` (discagem/anúncios/redelivery), `update_proto`
    (protocolo/transferência do update: versão/manifesto, oferta com
    reoferta — inclusive a diferida 1.12 —, pedido e chunks) + `update`
    (manifesto/aplicação, 608 linhas) + `update_store` (folha só-stdlib,
    227 linhas: só os helpers fd-fixados puros — openat/mkdirat/renameat
    O_NOFOLLOW — extraídos de `update.py` sem mudar lógica, Desenho A da
    1.12; sem nenhum estado global e sem importar `senderme_app`;
    `update.py` importa daqui e re-exporta para compat; a validação/
    contenção (`_cadeia_segura`/`_eh_escape`/`_rm_arvore`) e o
    apply/rollback seguem em `update.py`, onde a revisão TOCTOU os lê
    junto do uso; `preboot.py` segue 100% autônomo, duplicação
    proposital — nunca importa este módulo, pois o disco pode estar
    misto após SIGKILL),
    `comandos`+`http` (lógica web e servidor), `app` (main/purga/desligar),
    `diario` (folha só-stdlib + `meta`: diário em arquivo, ver seção abaixo).
    Sem `from x import variavel-mutavel`, sem rebind que quebre alias
    (`purgar` muta in-place), sem circulares (3 imports adiados
    documentados: eventos↔manut, comandos→manut, tcp↔manut).
  - `config.py` — constantes e ajustes (portas, janelas, limites). Folha pura.
  - `crypto.py` — RSA-2048 próprio + fingerprint. Folha pura.
  - `pagina.py` — `PAGINA` (HTML+JS da interface). Só dados.
    (Não desmembrado em 1.3: duplo escape contido, offline OK; reavaliar se
    o JS crescer — ver decisão em `03-progresso.md`.)
  - `bootstrap.min.css` — Bootstrap 5.3.3 local (offline, sem CDN).
  - `start.sh` — launcher (copia o RUNTIME para `/tmp`, `SENDERME_HOME`, abre
    browser, **loop: exit 42 = update aplicado, recopia e roda de novo;
    outro código = falha propagada**; `trap` limpa `$RUN_DIR`).
  - `README.md` — instruções de uso (só repo: fora do conjunto assinado e da `dist/`).
  - `update-manifest.json` — `{manifest, sig}` da release (gerado pelo dono).
  - `dono/` — `privada.json` (SECRETA, nunca distribuída) + `assinar_update.py`
    (lê versão/lista de `senderme_app/meta.py`).
  - `dist/` — build limpa gerada por `build_dist.sh` (sem `dados/`, `dono/`,
    `docs/`, roteiro, checkpoints, logs).
  - `docs/` — esta documentação.

## Criptografia: assinaturas RSA-2048 em Python puro

- Implementação própria com `int`/`hashlib`/`secrets` (sem PyNaCl/cryptography).
- Geração: dois primos 1024 bits (Miller-Rabin 24 rodadas), `e = 65537`.
- Assinatura EMSA-PKCS1-v1_5 + SHA-256. Verificação ~1-2 ms.
- **ID = `sha256(n || e)[:40]`**. Chave em `dados/identidade.json` (`chmod 600`
  com try/except p/ FAT).
- Sem PKI: chaves de pares são aprendidas na primeira vista (TOFU,
  `conhecidos.json`) e apelidos são livres e reutilizáveis — a assinatura
  vincula o evento a uma chave, não a uma pessoa; trocar de identidade
  com o mesmo apelido é possível e esperado (ver transferência em
  `01-produto.md`).
- Tráfego P2P (TCP 13337/UDP 13338) sem TLS: quadros JSON em claro,
  observáveis por qualquer pessoa na mesma rede local.

## Rede

- **TCP 13337 (P2P)**: quadros = 4 bytes big-endian + JSON UTF-8, limite 8 MB.
- **UDP 13338 (descoberta)**: broadcast a cada 3 s com hello **assinado**
  (`id`, `nick`, `porta TCP/UDP`, `ts`, `nonce`, `sig`). Unicast de reforço.
  `SENDERME_NO_BROADCAST=1` suprime o broadcast (só testes; unicast preservado).
- **TCP 13336 (HTTP local)**: `ThreadingHTTPServer` em `127.0.0.1` (só a máquina).
  Serve página + API JSON. Não expõe para a LAN; P2P continua 13337/13338.
- Conexões TCP: dial nos dois sentidos, máx. 2 por par, dedupe por `mid`.
  Auto-reconexão ~10 s. Fallback `SENDERME_FIXOS=ip:porta,...` (sem descoberta;
  permite 2 instâncias no mesmo PC com portas diferentes).

## Descoberta sem broadcast + conexões saudáveis (fix atraso longo)

- Sintoma: após um tempo, mensagens demoravam muito (chegavam após recarregar);
  causa: descoberta dependia só de broadcast UDP (roteador/AP pode bloquear) e
  não havia tráfego em conexão ociosa (`ultimo_contato` parava) nem limpeza de
  sockets mortos (`conns` acumulava cadáveres).
- **Peer exchange**: após o handshake, cada lado manda `peers_req`; resposta
  `peers [[ip,porta],...]` (até 20) vai para `sementes` e entra na discagem.
  Funciona mesmo com broadcast bloqueado.
- **`ping`/`pong`** a cada 5 s em conexões vivas (atualiza `ultimo_contato`
  nos dois lados; `ler_loop` já atualiza em qualquer quadro).
- **Limpeza**: `fechar_socket` sempre com `pid` onde conhecido; `manutencao`
  varre `conns` removendo sockets fora de `sockets_vivos`.
- **Browser anti-travamento**: todo `fetch` com `try/catch` + timeout 15 s
  (`AbortController`); `poll` nunca morre; envio falho **mantém o texto** e mostra
  erro (antes a exceção deixava a mensagem presa sem explicação); `visibility`
  repuxa; selo de estado (online/atualizando) + auto-detect de versão nova.
- **Avisos UI sem duplicata (item 2)**: login com `msg` de aviso exibe sem
  trocar de aba; falha real de rede preserva o texto digitado; aviso de
  "não consegui salvar" some sozinho no próximo poll limpo (sem acumular
  faixas). Testes: `tests/test_pagina_avisos.py` (9 testes: JS servido via
  `node --check` + sondas com DOM simulado).

## Propagação (gossip/flood) + arquivos

- Evento novo é repassado a todos (exceto origem), dedupe por `mid`.
- `mid = sha256(campo_assinatura)` onde campo =
  `tipo|de|nick|ts|txt|nonce[|para][|nome|tamanho|sha256]`.
  `para` presente em DM (texto ou arquivo). `arq` presente em `file`.
  Formato antigo continua válido (sem `arq`).
- `hist_req` → `hist`: últimas 24h, máx. 1000 eventos, **sem DM** (nem texto nem
  arquivo). `hist` traz `pubs` (chaves dos autores) para validar na hora.
  O receptor persiste o lote com **uma única escrita** (`anexar_lote`).
- **Merge Lego por inventário**: `hist_req` leva `têm:[mids]` (até 5000); o outro
  responde só com o que falta (até 1000) + `pubs`. Sem inventário (peer antigo),
  cai para janela dos últimos 1000. Os dois lados pedem ao conectar → união
  total por `mid`, qualquer faixa de horário.
- Conteúdo de arquivo: após `hist`, puxa faltantes imediatos (até 20) + varredura
  de 2 por ciclo de `manutencao` até convergir (teto 60 MB manda).
- Tipos: `msg`, `join`, `leave`, `nick` (propagados), `dm` (direto),
  **`file`** (metadados propagados; conteúdo via pull).
- **Arquivo global**: evento `file` (pequeno, assinado; `nome` sanitizado via
  `basename`, sem `/`, `\`, CR/LF, máx. 120; `sha256` hex validado no recebimento) propaga por gossip.
  Conteúdo **não** vai no evento. Quem recebe e não tem o `.bin` manda
  `file_req {mid}`; quem tem responde `file_chunk {mid,idx,total,dados_b64}`
  em chunks de **512 KB** (base64 ~700 KB < 8 MB). Remonta, confere
  `sha256`, salva em `dados/arquivos/<mid>.bin`, chama purga.
- **Arquivo DM**: evento + chunks enviados **direto** pela conexão do destino
  (nunca gossip, nunca sync). Guardado local nos dois lados.
- **DM para offline (redelivery direta)**: DM nunca vai em `hist` nem por gossip.
  O remetente reenvia as DMs recentes (até 20 por destino, 24h, throttle 120 s)
  quando o destino volta (nova conexão, hello, join). Receptor deduplica por
  `mid`. Terceiros nunca guardam DM.
- `file_req` com throttle 30 s por `mid`; `montando` expira em 10 min.
  Sync: após `hist`, pede os `file` faltantes (últimos 20).

## Detalhes de comportamento (inclui fixes do bug de nome)

- **Bug v1 "nome igual"**: `aplicar_nick` aceitava qualquer evento sem olhar `ts`
  → mensagem velha revertia nick atual. **Fix v2**: `nick_ts[id]` last-write-wins;
  `aplicar_nick(id,novo,antigo,ts)` ignora se `ts < nick_ts[id]`. Hello e eventos
  passam `ts`; `conhecidos.json` usa `ts=0`. `em_uso_online` + sufixo `(2)` mantidos.
- **Entrada/saída**: `join` só se `logado`. `manutencao` anuncia na 1ª conexão
  após login. Detecção de saída: 12 s sem hello e sem TCP → `leave` (`txt`=id).
  Janelas 90 s (join) / 60 s (leave). `Ctrl+C` publica `leave` próprio + 0,6 s.
- **Nick table com transferência**: `nick_dono` é first-wins **só entre online**.
  Se o dono está offline, reivindicação mais nova transfere a posse (zerei e
  voltei com o mesmo nome funciona, sem `(2)`). `(2)` só desempata dois
  **online** simultâneos (histórico de quem saiu mostra o nome puro, sem
  retroagir sufixo). Login continua bloqueando nome de quem está online.
- **`/calar`**: por **id**, em `dados/calados.json`. Filtra na API, mas propaga e
  guarda (histórico global).
- **DM**: `para`=id destino. Só processa se `para==eu` ou `de==eu`.
  Diretas, **sem criptografia adicional**: a assinatura prova autoria, não dá
  confidencialidade (não apresentar como E2E).
- **Purga**: `historico.jsonl` append-only; a cada 10 min descarta >24h e reescreve;
  `vistos` reconstruído. `purgar_arquivos()`: apaga `.bin` >24h, depois os mais
  antigos até `total <= 60 MB`. Evento mantém metadados (vira "expirado").
- Sem rate limit/antispam (rede de confiança 6-20).

## Interface web (substitui o terminal)

- Página única embutida (`PAGINA`), Bootstrap local, JS puro, polling **0,7 s**
  em `GET /api/mensagens?depois=<mid>` (50 iniciais, depois incremental, máx. 200).
- Layout: abas **Chat / Configs**; Chat = lateral presentes + centro mensagens +
  `textarea` (Enter envia, Shift+Enter quebra) + anexo + campo `@alvo`;
  Configs = trocar apelido, meu ID, rede, calados, ajuda. Login em modal se sem
  `apelido.txt` (re-login igual retorna ok; diferente vira troca com evento
  `nick`). XSS escapado no cliente (`esc()` em todos os campos).
- Comandos híbridos: `/dm /quem /rede /apelido /calar /ajuda` digitáveis +
  botões (DM ao lado do nome, descalar na Configs). `/sair`/`/limpar` removidos:
  digitá-los retorna aviso "use Ctrl+C".
- Upload `POST /api/upload` multipart (parser próprio, limite 26 MB, rejeita
  >20 MB com 413). Download `GET /api/arquivo/<mid>` com `Content-Disposition`
  + preview `<img>` p/ png/jpg/gif/webp.

## API HTTP (localhost)

| Método | Rota | Uso |
|---|---|---|
| GET | `/`, `/bootstrap.min.css` | página e CSS |
| GET | `/api/eu` | `{id,nick,logado,precisa_login}` |
| POST | `/api/login {nick}` | 1º login (valida, salva `apelido.txt`, `join`) |
| POST | `/api/nick {nick}` | troca (evento `nick`) |
| GET | `/api/mensagens?depois=` | `{eventos[],presentes[]}` filtrado de calados |
| POST | `/api/enviar {texto,para}` | slash ou msg; `para` sem `/` vira DM; responde `estado` ∈ {entregue,guardada,somente_memoria,erro} + `transmitida` (1.10) |
| POST | `/api/upload` | `file+texto+para` (global ou DM) |
| GET | `/api/arquivo/<mid>` | bytes (404 se expirado/baixando) |
| GET | `/api/rede`, `/api/ajuda`, `/api/calados` | telas da Configs |
| POST | `/api/calar {alvo}` | toggle |

- Servidor só em `127.0.0.1` (não é defesa completa sozinho). Política do
  gate (`_origem_ok` em `senderme_app/http.py`, aplicado às rotas POST
  mutantes: `/api/login`, `/api/nick`, `/api/enviar`, `/api/calar`,
  `/api/upload` — rota POST desconhecida responde 404 JSON após o gate —
  e, desde o item 4, também a **GET/HEAD**: leitura fora da origem é 403
  sem vazar bytes da interface (na 1.9, HEAD nunca leva corpo — Achado 3:
  status+headers com o `Content-Length` do GET, zero bytes; GET negado segue
  403 JSON sem conteúdo sensível); `curl`/scripts sem `Origin`/`Referer` e com
  `Host` loopback correto continuam passando):
  | Caso | Resultado | Motivo |
  |---|---|---|
  | Sem `Origin`/`Referer` (curl, scripts) + `Host` loopback na porta efetiva ou ausente | passa | cliente local não-navegador; bloquear não daria ganho (shell local já é a máquina) |
  | `Host` ausente + sem `Origin`/`Referer` (HTTP/1.0) | passa | cliente local sem cabeçalho |
  | `Host` inválido, externo ou de outra porta (mesmo sem `Origin`/`Referer`) | 403 sem efeito | trava DNS-rebinding; `Host` é conferido sempre que presente |
  | `Origin`/`Referer` da página servida (`http://` + MESMO host do `Host` + MESMA porta efetiva do servidor) | passa | mesma origem da página; `::1`, `127.0.0.1` e `localhost` NÃO equivalem entre si (Achado D: cruzado é 403) |
  | `Referer` local mesma-origem (sem `Origin`) | passa | navegação/proxy que só manda `Referer` |
  | Origem externa (`http://site-malicioso.test`, `Referer` externo) | 403 sem efeito | host não-loopback nunca é o frontend |
  | Loopback em **outra porta** | 403 sem efeito | outra origem no navegador (a porta efetiva `server_address[1]` é exigida; porta ausente vale 80 → 403) |
  | `Origin: null` (file://, iframe sandbox, privacidade) | 403 sem efeito | nunca é o nosso frontend |
  | Esquema fora de `http` (inclui `https`, pois o servidor só serve http), URL malformada, porta inválida/fora de faixa, userinfo (`http://evil.com@127.0.0.1`) | 403 sem efeito | hostname aparente não é o host real |
  | `Origin` e `Referer` inconsistentes entre si | 403 sem efeito | os dois são conferidos de forma independente |
  Testado com HTTP real (porta efêmera, `SENDERME_HOME` tmp, identidade
  sintética): os casos acima + fluxo login/envio/upload com a origem do
  frontend. `Origin: null` via navegador real nem chega ao servidor
  (o próprio Chromium bloqueia `data:`→loopback no client-side); o 403 do
  gate para `null` segue como defesa em profundidade, provado via HTTP
  direto. POST em rota desconhecida passa pelo gate (origem cruzada dá
  403) e responde 404 JSON `{"ok":false}` (antes: sem resposta). Verbo não
  implementado com `Host`/origem cruzada passa pelo gate antes do 501, sem
  vazar. Sem token/sessão, não há mitigação completa a alegar.
- **Ameaça residual documentada (não é proteção completa)**: o gate só
  impede que página de outra origem use o navegador como ponte. Script
  local (sem `Origin`) passa de todo jeito, clique coagido no próprio
  frontend tem efeito, e não há autenticação de cliente nem token por
  sessão — localhost+porta não prova qual programa local originou a
  requisição. Não apresentar como barreira contra app local malicioso.
  (Testes: `tests/test_origem.py` + `tests/test_csrf.py` fixam que
  outra-porta-loopback é 403, que alias loopback cruzado na MESMA porta
  é 403 (Achado D), que uso consistente do mesmo alias passa e que
  `Referer` externo isolado é rejeitado.)
- **`transmitida` + bloqueio de reenvio (1.10)**: `enviar_dm_para`/
  `tratar_comando_web` retornam `(ok, msg, estado, transmitida)` com
  `com_estado=True` (compat: 2-tupla sem ele); `/api/enviar` expõe
  `transmitida` no JSON. A UI (`pagina.py`, `btnEnviar`) trata
  `transmitida=true`+`somente_memoria` com aviso sem alegar recebimento,
  mantém o texto e desabilita o envio idêntico até editar
  (`ultimoNaoSalvo`+`atualizarBloqueio()`). Testes: `tests/test_dm.py` (24),
  extensão `+Transmitida` em `tests/test_api_contrato.py`,
  `tests/test_pagina_avisos.py` (22).

## Armazenamento (`dados/` no pendrive)

| Arquivo | Conteúdo |
|---|---|
| `identidade.json` | chave (n,e,d), `chmod 600`; corrompido/ilegível = aborta
  com erro, **sem sobrescrever**; falha ao gravar = aborta, sem alegar sucesso |
| `historico.jsonl` | eventos (msg/join/leave/nick/dm/file), purge 24h |
| `conhecidos.json` | id → pubkey + nick (TOFU) |
| `calados.json` | ids silenciados |
| `apelido.txt` | nick salvo (auto-login) |
| `arquivos/<mid>.bin` | conteúdo (teto 60 MB + 24h) |

- `SENDERME_HOME` = pasta original (start.sh). Rodando direto: pasta do script.

## Atualizações de versão (dono assina, peers aplicam sozinhos)

- `VERSAO = "1.23"` em `senderme_app/meta.py` (`SENDERME_VERSAO` sobrescreve
  em teste; **não conta como release** — ver `04-migracao.md`). Chave do dono: RSA-2048 em `dono/privada.json` (secreta);
  pública embutida (`CHAVE_DONO_N/E` em `meta.py`). `dono/assinar_update.py`
  lê versão e lista de `meta.py` e gera `update-manifest.json`:
  `{manifest:{v, arquivos:[{nome,tamanho,sha256}]}, sig}` sobre o manifest
  canônico. Payload = tudo (26 arquivos, só runtime: raiz + `senderme_app/`;
  README/docs/roteiro ficam no repo, fora do conjunto desde a lane redesign+dist).
- Protocolo: após handshake, `ver {v}` dos dois lados. Quem tem maior empurra
  `update_meta` (marca 1x por peer/versão em conexão viva, só após envio
  confirmado; falha nunca marca; morte da conexão de entrega reoferta no
  próximo `ver`; `ver` repetida após falha recente respeita cooldown de 10 s —
  e, se o cooldown suprimir a oferta com o peer ainda conectado, ou o envio
  falhar com o peer ainda conectado, UMA tentativa diferida sai ao fim do
  intervalo, revalidando peer/socket/versão e cancelada no disconnect);
  `CHAVE_DONO`, rejeita `v <= minha`, baixa chunks (`update_get`/`update_chunk`
  512 KB), confere `sha256` por arquivo, aplica com staging+backup e sai com
  código **42** → `start.sh` recopia e roda (sem `leave`, sem spam de join pela
  janela de 90 s). UI mostra "atualizando" (`/api/eu.atualizando`) e detecta a
  versão nova recarregando.
- Aplicação recuperável: verifica-tudo-antes-de-gravar, depois
  `.upd-staging/` → backup atômico em `.upd-backup/` (tmp+`os.replace`
  por arquivo; a volta restaura só backups concluídos) → marcador `.upd-pendente.json`
  → `os.replace` por arquivo → persiste o **envelope** `{manifest, sig}` em
  `update-manifest.json` (sem ele o peer atualizado não retransmite) →
  limpa staging/backup/marcador. Falha em qualquer ponto: reverte do backup
  e libera a flag (nova tentativa possível). Boot com marcador: restaura do
  backup (`recuperar_update`). Sem atomicidade prometida além disso (FAT32).
- Contenção anti-symlink (item 3, fail closed): antes de gravar, cada path do
  manifesto passa por `os.lstat` em todos os componentes — destino final
  symlink, intermediário não-diretório real ou escape do app são rejeitados
  sem escrever nada; remoção de árvore nunca segue symlink. Limites honestos:
  check-uso não é atômico (TOCTOU: troca concorrente entre checar e gravar
  ainda pode passar; sem `openat2`/`RESOLVE_IN_ROOT` na stdlib) e FAT32 não
  tem symlink (proteção vale no ext4/tmp do runtime). Testes:
  `tests/test_update_symlink.py` (6 testes).
- Janela dos temporários (Opção B, 1.10, sem módulo novo): `.upd-pendente.json.tmp`,
  `update-manifest.json.tmp` e (preboot) `update-manifest.json.upd-tmp` eram
  abertos por caminho absoluto antes do `replace` — troca concorrente ali
  passava. Agora saem por `openat` fd-relativo `O_NOFOLLOW` a partir do pai
  fixado + pós-cheque antes de promover; em corrida detectada, erro honesto
  (False + journal preservado, sem alegar "revertida") e o boot recupera pelo
  marcador. Testes: `tests/test_update_marcador_tmp.py` (3 testes, gancho por
  basename no `os.open` O_CREAT).
- Sem downgrade; manifest adulterado é rejeitado; peer 1.0 não participa
  (sem código de update) — bootstrap 1.0→1.1 via `dist/`. Clientes ≤1.2 não
  reiniciam sozinhos o pacote modular (launcher antigo): migração manual em
  `04-migracao.md`.

## Build de distribuição

- `build_dist.sh` gera `dist/SenderMe/` com código + manifest (sem `dados/`,
  `dono/`, `docs/`, roteiro, checkpoints, logs, `__pycache__`), mostra árvore + tamanho (< 80 MB). Copiar **essa
  pasta** para o pendrive. `SENDERME_HOME` continua apontando p/ o pendrive.
- Gate de release (item 1): sem `--dev`, a build verifica assinatura, versão
  código==manifesto, conjunto == `ARQUIVOS_UPDATE`==manifesto==allowlist e
  tamanho/hash dos BYTES da dist final — qualquer drift reprova com erro em
  stderr e exit != 0, sem anunciar release. Com `--dev`, o drift vira aviso
  e a saída sai marcada como DEV, nunca "OK" (desenvolvimento/testes apenas).
- Re-assinar (`python3 dono/assinar_update.py`, só o dono) é só para NOVA
  versão com conteúdo diferente — rebuild byte-idêntico passa no gate sem
  re-sign; qualquer byte diferente exige bump de versão (nunca reutilizar)
  + re-assinatura oficial.

## start.sh

```bash
APP_DIR=...; checa python3 e senderme.py; export SENDERME_HOME="$APP_DIR"
RUNTIME="<.py do pacote>"      # mesma fonte: ARQUIVOS_UPDATE em meta.py (teste confere)
trap limpar EXIT HUP INT TERM  # rm -rf $RUN_DIR
(sleep 2; xdg-open http://127.0.0.1:13336 &)  # abre sozinho
while true; do
  preboot.py "$APP_DIR"        # desfaz update interrompido; parcial sai !=0 e não boota
  # (1.9) preboot.py DUPLICA de propósito o mínimo do recovery (nunca importa
  # senderme_app: no boot o pacote pode estar parcial/misturado; 629 linhas
  # (sob a meta de 700 — não é exceção, e sim autonomia proposital); roda
  # partilhado criaria dependência de boot, e kill entre arquivos mataria a
  # recuperação no meio). Mensagem de
  # rollback honesta: nada afirma "reversão total" de efeito externo — em troca
  # concorrente detectada, erro + journal preservado p/ o boot decidir.
  RUN_DIR=$(mktemp -d)
  cp $RUNTIME -> $RUN_DIR      # + .py novo (inclusive subdir, R1b) + css; falta arquivo = erro
  python3 "$RUN_DIR/senderme.py"; code=$?; limpar
  [ "$code" -eq 42 ] && exec bash "$APP_DIR/start.sh"  # update: re-exec do NOVO em disco
  exit "$code"   # falha propagada (nunca vira 0)
done
```

## Variáveis de ambiente

| Variável | Efeito |
|---|---|
| `SENDERME_HOME` | pasta de dados (pendrive) |
| `SENDERME_PORTA` | TCP P2P (13337) |
| `SENDERME_UDP_PORTA` | UDP (13338) |
| `SENDERME_HTTP` | HTTP local (13336) |
| `SENDERME_FIXOS` | pares fixos `ip:porta,...` |
| `SENDERME_VERSAO` | sobrescreve `VERSAO` (testes de update) |
| `SENDERME_NO_BROADCAST` | `=1` suprime o broadcast UDP (testes; unicast preservado) |
| `SENDERME_SEM_LOG` | `=1` desliga o diário em arquivo (terminal continua) |

## Diário em arquivo (logs, 1.20)

- `senderme_app/diario.py` — folha só-stdlib (só importa `meta`; `estado`
  é lido de forma adiada para não criar ciclo). Habilitado por padrão.
- Caminho: `<SENDERME_HOME>/logs/senderme.log` (pasta da instalação —
  nunca o `/tmp` copiado pelo `start.sh`). Formato: uma linha JSON por
  evento (`ts`, `run`, `versao`, `evento` + campos seguros).
- Limites: rotativo principal + 5 backups (`senderme.log` + `.1`…`.5`,
  6 arquivos, ~6 MiB no total). Decisão 1.19 (item 5e): mantido `BACKUPS=5`
  no código; o que mudou foi o texto (antes dizia "× 5" para 6 arquivos).
  Falha de log nunca derruba o chat (retorna False + 1 aviso no terminal).
  Como o `logging` engole exceções de write/flush/rotação, o handler próprio
  (`_ArquivoSeguro`) captura a falha e `registrar()` a reporta.
- Privacidade: allowlist `CAMPOS_PERMITIDOS` + validação por campo (blacklist
  de nomes não basta: dado da rede pode chegar em campo "inocente" — ex.
  string arbitrária como versão em `tratar_ver` vira `invalida`). Peers saem
  como rótulo temporário por execução (`peer-1`, `peer-2`… via `curto()`; o
  id permanente nunca vai para o arquivo nem é derivável entre execuções).
  Nunca vão para o arquivo: texto de mensagens/DMs, apelidos, nomes/conteúdo
  de arquivos, IPs completos, ids permanentes, chaves, histórico, caminhos
  pessoais, queries/corpos HTTP, `str(exc)`/payloads — só rótulos fixos,
  contadores, nomes de tipos de exceção e IP mascarado (`/24`; resto `***`).
- Threads: `instalar_hook_threads()` (no boot) registra `thread_falha` só com
  tipo da exceção + nome sanitizado da thread; o traceback completo vai só
  para o terminal. Limite: não cobre o que mata o processo (`os._exit`,
  SIGKILL, segfault) nem a thread principal (`sys.excepthook`).
- Preboot: `preboot.py` segue autônomo (nunca importa `senderme_app`) e
  anexa 1 linha JSON em `logs/preboot.log` só quando agiu (teve marcador
  ou restou recuperação; boot normal não escreve nada). Teto 256 KiB + 1
  backup; só bools, nunca caminhos. `SENDERME_SEM_LOG=1` desliga também o
  `preboot.log` (checagem só com `os`, autonomia preservada).
