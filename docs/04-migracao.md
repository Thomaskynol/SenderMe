# SenderMe — Migração e distribuição (atualizado 2026-11-02, 1.23)

> Este manual vive só no repositório: não entra em `ARQUIVOS_UPDATE`,
> `dist/`, P2P nem no manifesto assinado. Referências a ele a partir de
> arquivos distribuídos (ex. README) indicam o repositório como fonte.
> Relatórios de rodada (`RELATORIO_*.md`) citados na matriz foram arquivados
> fora da árvore em `SenderMe-historico/relatorios/` (1.13).

## Matriz de migração (o que foi realmente testado)

| Origem → destino | Resultado | Evidência |
|---|---|---|
| 1.22 → 1.23 via P2P, restart automático (releases REAIS) | **OK** | base 1.22 do checkpoint `sender-me-pre-1.23-20261102T083256Z.zip` (manifesto 1.22 assinado, fora da árvore) + install 1.23 desta árvore, identidades sintéticas distintas, portas efêmeras, `SENDERME_FIXOS` cruzado, `SENDERME_NO_BROADCAST=1`, launcher emulado no exit 42: B "update v1.23 recebido, baixando 26 arquivos", "update 1.23 aplicado, reiniciando", relançado, `/api/eu` → 1.23 com id de B preservado, `update-manifest.json` A==B byte-idêntico (retransmite), pública A→B `{ok:true, estado:entregue, transmitida:true, nivel:local}` visível em B, segredos ausentes dos dois diários (`grep` exit 1); só PIDs próprios mortos, tmp removido |
| 1.21 → 1.22 via P2P, restart automático (releases REAIS) | **OK** | base 1.21 do checkpoint `sender-me-1.21-20261102T063725Z.zip` (manifesto 1.21 assinado, fora da árvore) + `dist/` 1.22 desta árvore, identidades sintéticas distintas, portas efêmeras, `SENDERME_FIXOS` cruzado, `SENDERME_NO_BROADCAST=1`: B "update v1.22 recebido, baixando 26 arquivos", "update 1.22 aplicado, reiniciando", launcher re-executou, `/api/eu` → 1.22 nos dois com id de B preservado, `update-manifest.json` A==B v1.22 byte-idêntico (retransmite), `TERCEIROS.md` A==B chegou em B, docs 1.21 de B preservados no disco (o update nunca apaga), pública A→B `{ok:true, estado:entregue, transmitida:true, nivel:local}` visível em B, segredo `d` ausente dos dois diários; só PIDs próprios mortos, tmp removido |
| 1.20 → 1.21 via P2P, restart automático (releases REAIS) | **OK** | instalação 1.20 do checkpoint `sender-me-1.20-20261101T155106Z.zip` (manifesto 1.20 assinado) + árvore 1.21, identidades sintéticas distintas, portas efêmeras, `SENDERME_FIXOS` cruzado, `SENDERME_NO_BROADCAST=1`: B "update v1.21 recebido, baixando 25 arquivos", aplicou, exit 42, launcher re-executou, `/api/eu` versao 1.21 nos dois com id de B preservado, `update-manifest.json` A==B v1.21 byte-idêntico (retransmite), docs 1.20 de B preservados no disco (o update nunca apaga), pública A→B `{ok:true, estado:entregue, transmitida:true}` visível em B, 0 canários nos dois diários; boot da `dist/` 1.21 limpa (`/api/eu` 1.21, identidade nova) |
| 1.11 → 1.12 via P2P, restart automático (releases REAIS) | **OK** | instalação 1.11 do checkpoint `sender-me-pre-1.12-20261101.zip` (manifesto 1.11 assinado, 27 arquivos) + `dist/` 1.12, identidades sintéticas distintas, portas efêmeras, `SENDERME_FIXOS` A→B, `SENDERME_NO_BROADCAST=1`: A aplicou (incl. `update_store.py` novo), exit 42, launcher re-executou, `/api/eu` versao 1.12 com id preservado, `update-manifest.json` A==B v1.12, 28/28 tamanhos+hashes OK, DM pós-restart `{ok:true, estado:entregue, transmitida:true, nivel:socket, confirmado:false, peers:1}`; kill -9 com `atualizando=true` → launcher **137** (≠42), sem marcador, preboot exit 0, boot 1.11 íntegro (id igual), retry aplica 1.12 **sem restart do servidor** (ver relatório 1.12 arquivado) |
| 1.10 → 1.11 via P2P, restart automático (releases REAIS) | **OK** | instalação 1.10 do checkpoint `sender-me-pre-1.11-20261101T061034Z.zip` (manifesto 1.10 assinado, 26 arquivos) + `dist/` 1.11, identidades sintéticas distintas, portas efêmeras, `SENDERME_FIXOS` A→B, `SENDERME_NO_BROADCAST=1`: A aplicou (incl. `update_proto.py` novo via R1), exit 42, launcher re-executou, `/api/eu` versao 1.11 com id preservado, `update-manifest.json` A==B v1.11, 27/27 tamanhos+hashes OK, DM pós-restart `{ok:true, estado:entregue, transmitida:true, nivel:socket, confirmado:false, peers:1}`; kill -9 com `atualizando=true` → launcher 137 (≠42), sem marcador, preboot exit 0, boot 1.10 íntegro (id igual), retry aplica 1.11 **sem restart do servidor** (re-oferta 1.11: marca só após envio confirmado + cooldown 10 s; limitação 1.10 resolvida) (ver relatório 1.11 arquivado) |
| 1.9 → 1.10 via P2P, restart automático (releases REAIS) | **OK** | instalação 1.9 do checkpoint `sender-me-pre-1.10-20261101.zip` (manifesto 1.9 assinado) + `dist/` 1.10, identidades sintéticas distintas, portas efêmeras, `SENDERME_FIXOS` A→B: A "update recebido", aplicou, exit 42, launcher re-executou, `/api/eu` versao 1.10 com id preservado, `update-manifest.json` A==B v1.10, DM pós-restart `{ok:true, estado:entregue, transmitida:true}`; kill -9 com `atualizando=true` → sem marcador, preboot exit 0, boot 1.9 íntegro, retry aplica 1.10 (ver relatório 1.10 arquivado). Limitação honesta **da 1.10 (resolvida na 1.11)**: o servidor só re-ofertava `update_meta` 1x por (peer, versão) — após interrupção no download, a re-oferta exigiu restart do servidor |
| 1.8 → 1.9 via P2P, restart automático (releases REAIS) | **OK** | instalação 1.8 do checkpoint `sender-me-pre-1.9-20261031.zip` (SHA `bd33683a…`, manifesto 1.8 assinado) + `dist/` 1.9, identidades sintéticas, portas efêmeras, assinatura REAL: A "update v1.9 recebido, baixando 26 arquivos", aplicou, exit 42, launcher re-executou, `/api/eu` versao 1.9 com nick+id preservados, `update-manifest.json` A==B, 26/26 tamanhos+hashes OK, DM pós-restart `{ok:true, estado:entregue}`; log "update 1.9 aplicado, reiniciando" |
|---|---|---|
| ≤1.2 (launcher 24176fa) → nova via P2P, restart automático | **FALHA** (limitação) | `test_migracao_legada`: launcher real do git aplica os arquivos mas o Python morre com `ModuleNotFoundError` (só copia `senderme.py`+css); launcher sai **0** apesar da falha. O código 1.2 também não persiste o envelope (`update-manifest.json` novo não é gravado), então o P2P 1.2→nova sempre termina em complementação manual |
| ≤1.2 (com seu manifesto 1.2) → 1.7, migração manual com envelope completo | **OK** | `test_migracao_manual` (fixture do git **com** `update-manifest.json` 1.2 verificado; cópia completa `ARQUIVOS_UPDATE`+manifesto montada dinamicamente; sig+versão+completude+hashes conferidos; `dados/` byte-igual, histórico legível, `/api/eu` na versão nova) |
| Peer migrado → OUTRO peer 1.2 via P2P | **OK (envelope sintético, ver nota)** | `test_migracao_manual` fase P2P: o migrado serve os arquivos reais com envelope coerente de teste (chave sintética — o teste nunca toca a chave real, ver nota); o cliente 1.2 verifica sig+hashes, aplica, e após o restart falho conhecido completa-se com o manifesto servido + boot novo (versão nova, envelope coerente, identidade própria preservada) |
| 1.6/1.7 → futura (launcher novo) | esperado OK (não executado entre releases reais) | launcher novo com re-exec do `start.sh` do disco no exit 42 (`start.sh:118`), pre-boot de recuperação antes de copiar/bootar (`start.sh:97`), cópia RUNTIME + `.py` novo inclusive em subdir (`start.sh:51-85`, R1b testado em `test_dist_boot`) e propagação de exit ≠42 (`start.sh:122`); hipótese, não fato |
| 1.6 → atual, byte-exata | **NÃO EXECUTÁVEL aqui** (limitação) | não há árvore 1.6 neste repo (só `24176fa` + árvore atual) para montar a base 1.6 byte-exata; P2P entre versões é coberto com versões sintéticas (`test_update_e2e_abc`, `test_update_subdir_novo`, chave sintética); o caminho manual da seção abaixo vale para qualquer base pré-atual |
| A → B → C (propagação com envelope) | **OK (chave sintética)** | `test_update_e2e_abc.CadeiaABC.test_b_recebe_de_a_e_c_recebe_de_b_com_restart_real` (P2P real + exit 42 + `start.sh` real A→B e B→C, com A fora do ar na fase B→C) + `test_update_fluxo.PropagacaoABC` (chamadas diretas + FakeSock, parte única) + `ChunkViaSocketReal` (chunk por socket real + framing); C verifica sig+hashes do que B serviu |
| Instalação limpa via `dist/` + `bash start.sh` | **OK** | `test_dist_boot.BootReal` (boot + `/api/eu`); build sem segredos. `test_dist_boot.BuildDist` e `test_update_dist` conferem código == manifesto assinado (26 arquivos, sem drift) |
| Qualquer origem → 1.8 via `SENDERME_VERSAO=1.8` | **NÃO É MIGRAÇÃO** (limitação) | `SENDERME_VERSAO` só troca o default em memória para testes; não existe snapshot histórico autêntico da 1.8 nesta sessão (nenhuma árvore 1.8 assinada anterior). Migração real exige release assinada (bump + `dono/assinar_update.py` oficial) |

Hipóteses não testadas: restart real entre releases (ex. 1.6→1.7), loop
`baixar_update` (stall/timeout), Mint/FAT32 físico, broadcast da escola,
6–20 peers, auditoria cripto. Migração 1.6→atual byte-exata é impossível
neste repo (sem árvore 1.6 — ver linha da matriz). Testes de migração que
dependem de `git show 24176fa` **pulam** sem o histórico do git (ver
"Sem histórico do git" abaixo) — skip é limitação, não sucesso.

## Quando o restart manual é necessário (regra)

Após qualquer update, confira `/api/eu`: `versao` tem que ser a esperada.
Se não for, ou se o terminal mostrar falha mascarada, faça o caminho
manual (mesma seção abaixo, mesmos `dados/`):

- Base ≤1.2: **sempre manual** — o launcher antigo só copia
  `senderme.py`+CSS para `/tmp` e sai 0 mesmo quando o Python falha;
  nenhum ajuste no launcher novo conserta o processo antigo já em execução.
- Base 1.6: sem árvore 1.6 no repo não há prova byte-exata; se o P2P aplicar
  (exit 42) mas o servidor não voltar na versão nova, complete manual.
- Base atual: automático é o esperado (re-exec + pre-boot), ainda sem prova
  entre releases reais — na dúvida, o caminho manual abaixo sempre funciona
  e preserva `dados/`.

## Migração manual ≤1.2 → release atual (preserva identidade, histórico e envelope)

> Os passos valem para qualquer release assinada vigente (abaixo aparece a
> 1.23; "release nova" = a release assinada atual, nunca reutilizar versão).

Passos exatos, reproduzidos por `tests/test_migracao_manual.py` em cópia
isolada (fixture: `update-manifest.json` 1.2 do git `24176fa` + cada arquivo
listado nele, `dados/` sintético com histórico publicado pela API do app
antigo; o teste confere o envelope antigo antes, o envelope novo depois,
compara os bytes de `dados/` antes→depois e usa o migrado para atualizar
outro peer 1.2 via P2P):

0. De onde vem cada arquivo: da release nova (pendrive já atualizado,
   `dist/SenderMe`, ou arquivos aplicados via P2P — confira que
   `senderme_app/` existe na pasta). Nada vem de outro lugar; `dados/`
   nunca é copiado de outro pendrive nem apagado.
1. Feche o app antigo (`Ctrl+C` no terminal do servidor). Não pule este
   passo: o processo antigo continua executando o loop antigo mesmo depois
   de `start.sh` ser substituído no disco.
2. Garanta que `dados/` está intacto (opcional: copie `dados/` para backup
   antes de continuar).
3. Liste o conjunto completo SEM hardcode (outra release pode acrescentar
   arquivos, ex. `senderme_app/preboot.py`):
   `python3 -c "import senderme_app.meta as m; print('\n'.join(m.ARQUIVOS_UPDATE))"`
   mais `update-manifest.json`. Confira que a instalação antiga tem o SEU
   manifesto (`update-manifest.json` v1.2 do git `24176fa` — sem ele o peer
   migrado não teria de onde provar a release; R4).
4. Substitua os arquivos do app, NESTA ORDEM, sem tocar em `dados/`:
   a. todos os `ARQUIVOS_UPDATE` exceto `start.sh` (isto troca o
      `senderme.py` monolítico pelo entry fino e cria `config.py`,
      `crypto.py`, `pagina.py` e o pacote `senderme_app/`);
   b. `update-manifest.json` da release nova;
   c. POR ÚLTIMO o `start.sh` novo (só com o runtime já completo; o
      launcher novo aborta com erro se faltar arquivo, em vez de mascarar).
5. Confira ANTES de bootar (o teste faz o mesmo programa em Python):
   assinatura do manifesto com a chave pública embutida
   (`senderme_app/meta.py:CHAVE_DONO_*` via `senderme_app/update.py:manifest_canonico`
   + `crypto.conferir`), versão do manifesto == versão do código,
   todo `ARQUIVOS_UPDATE` presente no disco, e sha256+tamanho de cada
   arquivo do manifesto. Sem o passo 4b o manifesto permanece 1.2 e o hash
   de `senderme.py` não confere com o código novo (R4 em vermelho).
   Regra de divergência (usuário): **qualquer hash/tamanho que não bata =
   aborte, não boote mistura** — busque outra cópia com o dono. Só o dono
   resolve drift (bump de versão + re-assinatura oficial, nunca reutilizar
   a versão). A "tolerância a drift" existe SÓ no teste
   (`tests/test_migracao_manual.py`: arquivo byte-igual à árvore do repo em
   desenvolvimento segue com aviso; `senderme.py` em drift falha sempre) —
   ela acomoda o desenvolvimento, nunca é orientação de uso.
6. Rode `bash start.sh` (o novo, da release). Pronto — apelido, identidade
   e histórico continuam (mesmos `dados/`); `/api/eu` responde logado, com
   o mesmo nick/id e a versão nova; `/api/mensagens` mostra o histórico.
7. P2P (prova do envelope): com o migrado rodando, suba OUTRO peer 1.2
   apontando para ele (`SENDERME_FIXOS=127.0.0.1:<porta-tcp-do-migrado>`).
   O cliente verifica a assinatura, baixa os arquivos e aplica (exit 42);
   o restart automático falha como documentado (launcher antigo) — então
   complete copiando o `update-manifest.json` servido (já verificado) e
   bootando com o `start.sh` novo que o P2P trouxe. O segundo peer assume a
   versão nova com envelope coerente e identidade própria preservada.
   Nota honesta: o P2P do teste usa envelope de TESTE (chave sintética,
   mesmos arquivos e versão vigente) para não tocar a chave real; o
   teste nunca usa `dados/` real nem `dono/privada.json`.

Se o app abortar dizendo que `identidade.json` está inválido: **nada foi
apagado**. Faça backup do arquivo, corrija ou apague-o para gerar nova
identidade (a antiga será perdida).

## Caminho base com launcher novo → release atual (P2P automático ou manual)

Quem já está numa base com o launcher novo não precisa da migração manual
acima, salvo se preferir:

- Automático: o peer novo serve o envelope (`update-manifest.json` com
  sig+hashes); o cliente baixa, aplica com staging+backup+marcador e sai
  42; o launcher **re-executa o `start.sh` DO DISCO** (já novo,
  `start.sh:118`) em vez de reusar a lista velha, e o pre-boot do
  próximo ciclo desfaz update interrompido antes de copiar/bootar
  (`start.sh:97`), sem iniciar mistura. Testado entre releases de teste
  (chave sintética) em `test_update_e2e_abc`; entre releases reais é
  esperado, não executado.
- Manual (mesmos passos da seção anterior a partir de uma base com launcher
  novo):
  copiar `ARQUIVOS_UPDATE` (menos `start.sh`) + `update-manifest.json` +
  `start.sh` por último, conferir sig+versão+hashes, rodar o novo
  `start.sh` nos mesmos `dados/`. Funciona porque a base com launcher novo
  já tem o pacote modular; só atualiza o conteúdo e o envelope.

## Por que o launcher antigo não serve

O processo `bash start.sh` antigo continua executando o loop antigo mesmo
depois de `start.sh` ser substituído no disco: ele recopia só `senderme.py`+CSS
para `/tmp` e o código novo não acha `config`/`senderme_app` (`ModuleNotFoundError`).
Além disso ele termina com exit 0, escondendo a falha. O launcher novo
(revisão conferida contra o `start.sh` final da árvore) copia o RUNTIME
inteiro **mais** qualquer `.py` novo no disco, inclusive em subdiretório
de `senderme_app/` (`start.sh:51-85`, R1b com regressão em `test_dist_boot`;
lista conferida contra `senderme_app/meta.py` por teste comportamental),
roda o pre-boot de recuperação antes de cada boot
(`start.sh:97`), re-executa o `start.sh` do disco no exit 42
(`start.sh:118`, em vez de reusar o shell/lista velhos) e propaga
qualquer exit ≠42 (`start.sh:122`). Nenhum ajuste no launcher novo
conserta o processo antigo já em execução — por isso a migração manual acima.

## Distribuição e assinatura

- Release no disco: código+manifesto **1.23 assinada**
  (`update-manifest.json`, 26 arquivos, sig True). Docs 1.23 (README +
  docs 01–03, com entrada 1.23 em `03-progresso.md` e linha 1.22→1.23 na
  matriz acima; este manual e AGENTS.md fora do manifesto).
  Registro datado: 1.22 (26 arquivos) e 1.21 (25 arquivos) foram as releases
  anteriores, cada uma superada por bump + re-assinatura.
- Registro datado (releases superadas): 1.20, 1.19 e 1.18 (29 arquivos),
  1.17, 1.16, 1.15 e 1.14 (28 arquivos), 1.11 (27 arquivos), 1.10 e 1.9
  (26 arquivos), 1.8, 1.7 (26 arquivos, incl. `senderme_app/preboot.py`),
  1.6/1.5/1.4/1.3 (25 arquivos). Cada uma foi assinada pelo processo oficial
  no dia da release e superada pela seguinte por bump + re-assinatura
  (nunca reutilizar versão — mesma versão é rejeitada pelos peers).
- Testes usam **chave sintética** em dirs temporários; nunca a chave real,
  nunca `dados/` real.
- Regras: versão maior serve, igual/inferior rejeitada (testado, inclusive
  com manifestos assinados pela chave sintética); assinatura inválida,
  arquivo adulterado, pacote incompleto e erro de gravação abortam sem deixar
  pacote misto (staging+backup+rollback, testado).

## Sem histórico do git (skips — limitação, não sucesso)

`test_migracao_legada` e `test_migracao_manual` montam a base ≤1.2 via
`git show 24176fa:<arquivo>` (manifesto 1.2 oficial + cada arquivo dele).
Sem esse commit no clone, ambos **pulam via `skipTest`**:

- `test_migracao_legada`: `start_antigo()` retorna `None` → pula o teste
  inteiro (launcher antigo real + migração manual na mesma cópia).
- `test_migracao_manual`: `montar_fixture_antiga()` retorna `None` → pula
  no teste principal e na fase P2P (envelope 1.2, preservação de `dados/`,
  retransmissão).

O que se perde sem o git: toda a cobertura ≤1.2→atual. Ambientes afetados:
`dist/` (sem `.git`), clones rasos sem o commit, tarballs exportados. Na
árvore de desenvolvimento (com `.git`) ambos executam — é o caso validado.

Avaliado bundle de fixtures sanitizadas (2026-10-31): seriam ~100 KB
(`senderme.py` 1.2 com 92 KB + `start.sh`/README/docs pequenos; o
`bootstrap.min.css` 1.2 é byte-igual ao atual, sha256 `26db49…cad`,
dispensaria duplicação; manifesto/sig 1.2 são públicos, sem segredos, com
procedência `git show 24176fa` + hashes). Escolhido **não incluir**: exige
reescrever o carregamento dos 2 testes E2E mais delicados por um benefício
só fora da árvore de desenvolvimento. Reavaliar se a suíte precisar rodar
a partir de `dist/`.
