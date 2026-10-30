# SenderMe — Arquitetura e Decisões Técnicas (v2 navegador, versão 1.1)

> Escolhas do desenvolvedor, alinhadas com `01-produto.md` (v2).
> Se mudar algo aqui, atualizar também `03-progresso.md`.

## Linguagem e runtime

- **Python 3 puro, só biblioteca padrão.** Zero dependências externas.
  - Pendrive roda em qualquer Mint sem instalar nada.
  - Medido: `senderme.py` ~69 KB + `bootstrap.min.css` ~228 KB. Pasta < 80 MB.
- Arquivos do app:
  - `senderme.py` — aplicativo inteiro (P2P + HTTP + página). `VERSAO = "1.1"`
    (ou `SENDERME_VERSAO` em teste) + `CHAVE_DONO` (pública do dono, embutida).
  - `bootstrap.min.css` — Bootstrap 5.3.3 local (offline, sem CDN).
  - `start.sh` — launcher (copia py+css para `/tmp`, `SENDERME_HOME`, abre browser,
    **loop: exit 42 = update aplicado, recopia e roda de novo**).
  - `README.md` — instruções de uso.
  - `update-manifest.json` — `{manifest, sig}` da release (gerado pelo dono).
  - `dono/` — `privada.json` (SECRETA, nunca distribuída) + `assinar_update.py`.
  - `dist/` — build limpa gerada por `build_dist.sh` (sem `dados/`, `dono/`).
  - `docs/` — esta documentação.

## Criptografia: assinaturas RSA-2048 em Python puro

- Implementação própria com `int`/`hashlib`/`secrets` (sem PyNaCl/cryptography).
- Geração: dois primos 1024 bits (Miller-Rabin 24 rodadas), `e = 65537`.
- Assinatura EMSA-PKCS1-v1_5 + SHA-256. Verificação ~1-2 ms.
- **ID = `sha256(n || e)[:40]`**. Chave em `dados/identidade.json` (`chmod 600`
  com try/except p/ FAT).

## Rede

- **TCP 13337 (P2P)**: quadros = 4 bytes big-endian + JSON UTF-8, limite 8 MB.
- **UDP 13338 (descoberta)**: broadcast a cada 3 s com hello **assinado**
  (`id`, `nick`, `porta TCP/UDP`, `ts`, `nonce`, `sig`). Unicast de reforço.
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
| POST | `/api/enviar {texto,para}` | slash ou msg; `para` sem `/` vira DM |
| POST | `/api/upload` | `file+texto+para` (global ou DM) |
| GET | `/api/arquivo/<mid>` | bytes (404 se expirado/baixando) |
| GET | `/api/rede`, `/api/ajuda`, `/api/calados` | telas da Configs |
| POST | `/api/calar {alvo}` | toggle |

## Armazenamento (`dados/` no pendrive)

| Arquivo | Conteúdo |
|---|---|
| `identidade.json` | chave (n,e,d) |
| `historico.jsonl` | eventos (msg/join/leave/nick/dm/file), purge 24h |
| `conhecidos.json` | id → pubkey + nick (TOFU) |
| `calados.json` | ids silenciados |
| `apelido.txt` | nick salvo (auto-login) |
| `arquivos/<mid>.bin` | conteúdo (teto 60 MB + 24h) |

- `SENDERME_HOME` = pasta original (start.sh). Rodando direto: pasta do script.

## Atualizações de versão (dono assina, peers aplicam sozinhos)

- `VERSAO = "1.1"` no código (`SENDERME_VERSAO` sobrescreve em teste).
- Chave do dono: RSA-2048 em `dono/privada.json` (secreta); pública embutida
  (`CHAVE_DONO_N/E`). `dono/assinar_update.py` gera `update-manifest.json`:
  `{manifest:{v, arquivos:[{nome,tamanho,sha256}]}, sig}` sobre o manifest
  canônico. Payload = tudo (`senderme.py`, `bootstrap.min.css`, `start.sh`,
  `README.md`, `docs/*`).
- Protocolo: após handshake, `ver {v}` dos dois lados. Quem tem maior empurra
  `update_meta` (1x por peer/versão); quem tem menor verifica `sig` com
  `CHAVE_DONO`, rejeita `v <= minha`, baixa chunks (`update_get`/`update_chunk`
  512 KB), confere `sha256` por arquivo, escreve em `SENDERME_HOME` e sai com
  código **42** → `start.sh` recopia e roda (sem `leave`, sem spam de join pela
  janela de 90 s). UI mostra "atualizando" (`/api/eu.atualizando`) e detecta a
  versão nova recarregando.
- Sem downgrade; manifest adulterado é rejeitado; peer 1.0 não participa
  (sem código de update) — bootstrap 1.0→1.1 via `dist/`.

## Build de distribuição

- `build_dist.sh` gera `dist/SenderMe/` com código + manifest (sem `dados/`,
  `dono/`, `__pycache__`), mostra árvore + tamanho (< 80 MB). Copiar **essa
  pasta** para o pendrive. `SENDERME_HOME` continua apontando p/ o pendrive.

## start.sh

```bash
APP_DIR=...; checa python3; mktemp -d /tmp/senderme-XXXX
cp senderme.py bootstrap.min.css -> $RUN_DIR
export SENDERME_HOME="$APP_DIR"
(sleep 2; xdg-open http://127.0.0.1:13336 &)  # abre sozinho
python3 "$RUN_DIR/senderme.py"  # foreground = servidor; Ctrl+C = sair
# loop: exit 42 = update aplicado -> recopia tudo e roda de novo
trap EXIT rm -rf $RUN_DIR
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
