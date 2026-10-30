# SenderMe — Progresso e Próximos Passos

> **Este é o documento de retomada.** Sessão nova sem memória: leia `01-produto.md`,
> depois `02-arquitetura.md`, e use este arquivo para continuar de onde parou.

## Situação atual (última atualização: 2026-10-30, v2 navegador pronta)

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

## Constantes ajustáveis (topo do `senderme.py`)

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

Estrutura de `senderme.py`: constantes → estado → crypto → armazenamento
(+arquivos) → eventos/nicks (fix) → processamento → TCP (+file) → UDP →
manutenção/purga → comandos web → formatação API → HTTP + página → main
(servidor, Ctrl+C = leave).

## v1.2 — retenção 24h, data+hora, sync mais rápido

- `RETENCAO` 48h → **24h** (uma constante cobre purga, sync, DM offline e arquivos).
- `hora_de` agora `DD/MM HH:MM` (antes só `HH:MM`).
- Polling do navegador 1,5 s → **0,7 s**.
- `tratar_hist` persiste o lote com **uma escrita** (`anexar_lote`;
  `processar(..., disco=False)`); P2P medido a 24 ms/msg, sync de 700 msgs <0,5 s.
