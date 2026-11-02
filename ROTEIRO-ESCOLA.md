# SenderMe — Roteiro de laboratório na escola (2026-11-02, v1.23)

> Este roteiro é para o **responsável pelo teste** e vive na **raiz do
> repositório como `ROTEIRO-ESCOLA.md`** (unsigned: fora do manifesto
> assinado, fora do P2P). Versão de referência: **1.23**
> (ver `/api/eu` → `versao`). Se a versão na escola for outra, o passo a passo
> vale igual — só confira que **todos estão na mesma**.
>
> Distribuição para os amigos contém **SOMENTE os arquivos do aplicativo**
> (`dist/SenderMe`, build limpa). O roteiro **NÃO vai para `dist/` nem para
> os pendrives** — nenhum mecanismo em `build_dist.sh` copia roteiro
> (verificado: a allowlist só tem runtime + manifesto, 26 arquivos).
> Não há etapa de cópia para `dist/`; se o responsável quiser levar uma cópia
> à parte (impressa ou em outro pendrive), a cópia é manual e **nunca dentro
> de `dist/SenderMe`**:
>
> ```bash
> cp ROTEIRO-ESCOLA.md /onde/quiser/ROTEIRO-ESCOLA.md
> ```
>
> Kit escola (layout no pendrive — **só o app, sem roteiro**):
>
> ```text
> pendrive/
>   SenderMe/            <- cópia de dist/SenderMe (app assinado, zerado)
> ```
>
> Para montar: `bash build_dist.sh` (release, assinada) e copie **só** a pasta
> `dist/SenderMe`.

## 0. O que levar (checklist)

- [ ] Um pendrive por participante, cada um com o **kit escola** acima
      (pasta `SenderMe` limpa; sem roteiro no pendrive — o roteiro fica
      com o responsável).
- [ ] PCs com **Linux Mint** e `python3` instalado
      (`python3 --version` no terminal; se faltar: `sudo apt install python3`).
- [ ] Todos na **mesma rede local** (mesmo Wi-Fi ou mesmos cabos do laboratório).
- [ ] Papel ou editor para a **tabela de registro** (seção 6).
- [ ] Combinado com o **responsável pela rede/TI** da escola (seção 7):
      só ele mexe em firewall. Alunos não alteram nada.
- [ ] Relógios dos PCs mais ou menos certos (cada mensagem mostra a hora de
      quem enviou; relógios muito diferentes embaralham a ordem — aceito).

## 1. Preparar uma cópia por participante (sem clonar ninguém)

1. Copie **só** a pasta `dist/SenderMe` (zerada, sem `dados/`) para cada
   pendrive (ou pasta de cada PC). Não copie nenhum roteiro junto: a
   distribuição é só o app.
2. Confira que a cópia do app **não** tem `dados/` nem `dono/`:
   `ls` na pasta não deve mostrar essas pastas. Copiar `dados/` clona a
   identidade de outra pessoa (mesmo apelido + mesma chave).
3. **Nunca apague `dados/` de ninguém.** Se o pendrive/PC já tem uma
   instalação anterior com `dados/` (apelido + identidade + histórico da
   pessoa), **preserve**: ou reuse a mesma pasta (rode o `start.sh` dela —
   o update via rede/P2P cuida da versão, seção 8), ou guarde a pasta
   `dados/` à parte antes de colocar a cópia limpa. Apagar `dados/`
   destrói a identidade e o histórico — não há como recuperar.
4. Cada participante novo começa **zerado**: na 1ª execução escolhe o apelido e
   o app gera a identidade dele. Reusar um apelido antigo é permitido.

## 2. Iniciar e encerrar

Iniciar (terminal **na pasta do app**):

```bash
bash start.sh
```

- Use `bash start.sh`, não `./start.sh` (pendrive FAT não tem bit de
  execução; o script copia o app para `/tmp` por causa do `noexec`).
- O terminal fica como **servidor: deixe aberto** a aula inteira.
- O navegador abre sozinho em `http://127.0.0.1:13336`. Se não abrir,
  digite esse endereço no navegador. Essa página é **só da sua máquina**.
- Na 1ª vez, escolha o apelido. Depois entra direto (fica salvo).

Encerrar: **Ctrl+C** no terminal do servidor (avisa todo mundo que você
saiu). Fechar só a aba do navegador **não** sai do chat.

## 3. Verificar a versão (faça antes de testar)

1. No navegador, a versão aparece **ao lado do seu nome**.
2. Conferência exata (qualquer PC): abra `http://127.0.0.1:13336/api/eu`
   e leia `"versao"`. Esperado agora: `"versao": "1.23"`.
3. **Todos têm que estar na mesma versão.** Quem tem versão maior serve
   update sozinho para quem tem menor (seção 8) — numa aula, isso atrasa
   todo mundo. Se alguém divergir, atualize antes de começar.

## 4. Juntar 2 PCs: descoberta automática + plano B

1. Com 2 PCs rodando na mesma rede, cada um deve ver o outro entrar:
   aviso de `join`, nome no painel lateral, `/quem` mostra 2 presentes.
   Isso é a **descoberta automática** (UDP 13338) funcionando.
2. Aguarde até **30 segundos** — a descoberta tem intervalo de segundos.
3. Se ninguém aparecer, use o plano B (roteador bloqueando broadcast).
   Descubra o IP do colega (`hostname -I` no terminal dele; use o que
   começa com `192.168.` ou `10.`) e inicie assim:

```bash
SENDERME_FIXOS=192.168.0.5:13337 bash start.sh
```

   (troque pelo IP real do colega; vários IPs: separados por vírgula).
   Feche com Ctrl+C e rode de novo com a variável — ela só vale na partida.

## 5. Testes em ordem (expansão gradual)

Faça nesta ordem. Só avance quando o passo atual estiver verde nos 2 PCs.

**Passo 1 — mensagem pública (2 PCs).** A manda "ola turma" no campo
normal (Enter envia). Esperado: aparece nos dois, com data/hora
`DD/MM HH:MM`. Sem peers, o aviso é "Publicada localmente, sem peers
conectados — só você vê por enquanto": isso significa passo 4 falhou,
volte para ele.

**Passo 2 — DM (2 PCs).** No campo `@alvo` escreva **`@apelido`** do colega
(**com o `@`**, ex. `@bob`) + texto, ou digite `/dm @bob oi`.
Esperado: só o destino vê (e o remetente vê a própria). Detalhe
verificado aqui: sem o `@` o app responde "Uso: /dm @apelido mensagem"
e não envia — não é defeito, é o formato. DM não tem criptografia extra:
vale para a aula, mas não escrevam senhas reais no teste.

**Passo 3 — arquivo pequeno (2 PCs).** Anexe um `.txt` pequeno numa
mensagem global. Esperado: B vê nome + tamanho + link baixar; o conteúdo
chega igual. Limites: 20 MB por arquivo, 60 MB acumulados (acima disso o
app apaga os mais antigos).

**Passo 4 — desconexão e volta.** B aperta Ctrl+C, A manda uma mensagem
pública, B roda `bash start.sh` de novo. Esperado: B revê o aviso de
saída/entrada e **sincroniza o que perdeu** (histórico das últimas 24 h).

**Passo 5 — terceiro PC.** Entre com a cópia zerada dele. Esperado:
sincroniza o histórico, `/quem` mostra 3. **DMs antigas não aparecem
para ele** (DM nunca vai para terceiros) — esperado, não é defeito.

**Passo 6 — turma toda.** Entrem de 2 em 2 até 6–20. Se travar num
número, anote onde parou (seção 6) — esse é exatamente o dado que falta
(ver seção 10: carga real nunca foi testada).

## 6. Tabela de registro (uma linha por tentativa)

| Hora | Passo | Esperado | Observado | Logs (run-id) |
|---|---|---|---|---|
| | | | | |
| | | | | |

- **Logs (run-id):** em cada PC, abra o `logs/senderme.log` mais recente,
  copie o campo `"run"` (ex. `"run": "d2faa699d743"`) da hora do teste e
  cole aqui. É ele que liga a sua linha da tabela ao arquivo de log.
  Peers aparecem como `peer-1`, `peer-2`… (rótulo temporário daquela
  execução — não identifica ninguém fora dela).
- Anote o **texto exato** de qualquer erro (ex. "Uso: /dm…", "Sem conexão
  com…", "Publicada localmente…") em vez de "não funcionou".

## 7. Se ninguém aparecer: portas bloqueadas (diagnóstico, sem mexer)

Sintomas: `/quem` mostra só você; nenhum `join` chega; `SENDERME_FIXOS`
também não resolve.

Diagnóstico que aluno pode fazer (nada disso muda o PC):

1. Mesma rede? Compare os IPs (`hostname -I`): os inícios têm que ser
   iguais (ex. todos `192.168.0.x`).
2. O servidor subiu? `http://127.0.0.1:13336/api/eu` responde?
   Se não, leia o erro do terminal (ex. "porta ocupada" = já tem uma
   instância rodando; feche a outra).
3. `SENDERME_FIXOS` com o IP certo + porta `13337` foi tentado (seção 4)?
4. Anote tudo na tabela e **chame o responsável pela rede/TI**.
   Só ele pode liberar ou mudar firewall. O que pedir a ele: liberar na
   rede local o **TCP 13337** (conversa) e o **UDP 13338** (descoberta).
   A página **TCP 13336 é só local** (`127.0.0.1`) e não precisa de
   liberação — não peça para "abrir a 13336 no firewall".

## 8. Se aparecer update no meio da aula (com limites honestos)

- Quem tem versão maior **serve sozinho**; quem recebe **aplica e o
  servidor reinicia** (o terminal mostra "update aplicado"). Depois,
  confira `/api/eu` → `versao` em todos.
- **Limites das versões antigas** (ver `docs/04-migracao.md`):
  quem vem da **1.0** não recebe nada pela rede — atualize **via
  pendrive** (copie a pasta nova, mantendo `dados/`). Quem vem da
  **1.1–1.2** baixa e aplica, mas o launcher antigo não sabe reiniciar:
  após aplicar, **rode de novo `bash start.sh`** (o novo já está no
  disco) sem apagar `dados/`.
- Regra de segurança: **qualquer hash/tamanho que não bata = aborte**,
  não boote mistura — busque outra cópia com o dono. Só o dono resolve
  (nova versão + assinatura oficial; versão nunca é reutilizada).

## 9. Coleta de logs (sem vazar identidade nem histórico)

Onde ficam (na **pasta do app**, não no `/tmp`):

- `logs/senderme.log` + `logs/senderme.log.1` … `.5` (rodízio: principal +
  5 backups, ~1 MB cada, ~6 MB no total). É o diário do app.
- `logs/preboot.log` (+ `logs/preboot.log.1` quando existir; teto 256 KiB,
  1 backup) — só existem se o pre-boot agiu numa recuperação de update;
  boot normal não cria nada.
- Copie **os que existirem** na hora da coleta (se só há `senderme.log`,
  é porque ainda não rodou o suficiente para girar — normal).

Como copiar para o professor:

1. Feche o app (Ctrl+C).
2. Copie **só a pasta `logs/`**. Nunca copie `dados/` junto
   (`identidade.json` = chave privada; `historico.jsonl` = conversas;
   `arquivos/` = conteúdos; `apelido.txt`, `conhecidos.json`,
   `calados.json` também identificam).
3. Confira antes de entregar: a cópia tem que ter **só** arquivos
   `*.log` e `*.log.1` — se vier `identidade.json` ou `historico.jsonl`
   no meio, apague e copie de novo.

O que pode aparecer nos logs: **horários, versão, tipo de evento
técnico** (`boot`, `peer_conectou`, `rede_tcp_ok`…), contadores, portas,
um id de execução (`run`) e rótulos temporários de peer (`peer-1`…).
O que **nunca** vai para o log: texto de mensagens/DMs, apelidos, nomes
ou conteúdo de arquivos, IPs completos (no máximo `192.168.0.0/24`), ids
permanentes, dados arbitrários da rede, chaves, caminhos pessoais.
Verificado aqui: busca por apelidos, textos de teste e versões hostis de
protocolo nos logs voltou **0 ocorrências** (seção 10).

Como apagar: apague os arquivos `logs/senderme.log*` e
`logs/preboot.log*` (o app recria). Para **não gerar log** numa
execução: `SENDERME_SEM_LOG=1 bash start.sh` (o terminal continua
normal, e nem o `preboot.log` é criado; o teste da seção 10 usou o
padrão, com log ligado).

Anotação de reprodução (cole junto dos logs): hora, quem participava,
passo do roteiro, texto exato do erro/aviso, `run-id` da seção 6 e se
usou `SENDERME_FIXOS` ou descoberta automática.

## 10. O que foi testado aqui × o que falta na escola (honesto)

**Testado aqui (2026-11-01, neste PC — base do roteiro):** suíte completa
(353 testes, 0 falhas, exit 0 — incl. 2 peers sintéticos via `curl`),
`dist/` refeita da árvore + boot da dist via `start.sh` real,
P2P real 1.19→1.20 (base 1.19 do checkpoint pré-1.20, chave do dono,
loopback, `SENDERME_NO_BROADCAST=1`, `SENDERME_FIXOS` cruzado, **só via
`curl` (sem navegador)**) + carga da página de login em Chromium headless
real (perfil tmp isolado: exit 0, DOM com `<title>SenderMe</title>`, 0
`uncaught` — interação com botões/campos não exercida). Comandos e exits
verdadeiros:

- `/api/eu` nos dois: `"versao": "1.20"`, login OK; `/quem` com 2 presentes
  dos dois lados.
- Pública A→B: `estado=entregue`, chegou em B.
- DM com `/dm @bob …`: `estado=entregue`, `transmitida=true`,
  `nivel=socket`, chegou em B. DM sem `@`: `estado=erro`, "Uso: /dm
  @apelido mensagem" — formato exigido, não defeito.
- Arquivo global pequeno: chegou em B com o nome certo.
- Logs: `logs/senderme.log` criado nos dois; 0 ocorrências de
  apelidos/textos de teste/versões hostis de protocolo; 1ª linha
  `{"evento": "boot", …}`; peers como `peer-N` (sem id permanente).
- P2P 1.19→1.20: B servido por A, update aplicado com restart (exit 42 no
  launcher), `/api/eu` → `"versao": "1.20"` nos dois.
- Exits e evidência: ver `docs/03-progresso.md` (entrada 1.20) e os logs
  da rodada fora da árvore.
- Processos de outros lanes em execução **não foram tocados**.

**Pendente na escola (NÃO afirmado — é o que a aula vai descobrir):**
Linux Mint real; pendrive físico FAT32/NTFS/exFAT com `noexec`;
`bash start.sh` real com abertura automática do navegador; navegador
real (aqui só `curl` — interação com botões/campos não foi exercida);
broadcast UDP na rede escolar; 6–20 pessoas simultâneas; auditoria de
segurança/cripto. Qualquer linha acima que a aula conseguir (ou não)
deve ir para a tabela da seção 6.
