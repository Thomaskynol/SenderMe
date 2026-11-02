# SenderMe — Requisitos do Produto (v2 navegador, 1.23)

> Decididos em conversa com o usuário. Tudo aqui é decisão fechada, não sugestão.
> v1 era terminal. v2 é **navegador**, modo terminal **removido**.

## O que é

Chat global com **texto multilinha + arquivos**, pelo **navegador**, funcionando
**apenas na rede local**. **Sem servidor central.** Cada participante é um peer
independente e ajuda os outros a propagar as mensagens — modelo descentralizado.

Tráfego em texto simples na rede local (sem criptografia): sem o
aplicativo não há interface para o chat, mas qualquer pessoa na mesma
rede pode observar os bytes.

## Plataforma

- **Linux Mint** (alvo; sem validação em pendrive físico/FAT até aqui —
  ver `04-migracao.md`).
- Grupo esperado: **6 a 20 pessoas simultâneas**.
- Uso: `bash start.sh` no terminal (vira servidor, fica aberto) + uso no navegador.
  Terminal fica aberto como servidor; **Ctrl+C = sair** (avisa a rede).

## Portas de rede

- **TCP 13337** — conversa P2P (mesma porta em todas as máquinas).
- **UDP 13338** — descoberta automática dos pares por broadcast.
- **TCP 13336** — interface web **local** (`http://127.0.0.1:13336`, só na máquina).
  Não dá para reaproveitar 13337 (protocolo P2P binário) nem 13338 (UDP).

## Identidade

- Apelido escolhido por cada um (livre, máx. 24) **+ ID fixo interno**, gerado na
  primeira execução e salvo no pendrive.
- O ID é a impressão digital da chave pública (fingerprint).
- **Salvo: não pede de novo.** Assim que salva o nome, entra direto nas próximas
  vezes. Troca só na **aba Configs**.
- Se o nome salvo estiver **em uso** por alguém online, pede outro na entrada.
- **Zerou e voltou com o mesmo nome**: pode usar (o dono antigo sumiu, a posse
  transfere; sem `(2)` e sem bloqueio).
- **Apelido repetido é bloqueado** antes de falar.
- Cada mensagem/arquivo é **assinado digitalmente** — a assinatura
  confere com a chave pública conhecida do autor (chaves locais, sem
  PKI; apelido livre, reutilizável por outra identidade nova).
- **Mudança de apelido**: histórico antigo mantém o apelido **da época**.
- Entrada e saída: **aviso para todos**. `join` só depois do **login** no navegador.
  `leave` no **Ctrl+C** do terminal servidor.

## Mensagens

- **Não dá para apagar nem editar.**
- **Multilinha**: `Enter` envia, `Shift+Enter` quebra linha.
- Limite **2000 caracteres** por mensagem de texto.
- Mostra **data e horário** (de quem enviou, formato `DD/MM HH:MM`).
- Ordem por chegada; relógios divergentes podem embaralhar — aceito.

## Arquivos

- Até **20 MB por arquivo**, **qualquer tipo** liberado.
- Vale para mensagem **global e DM**.
- Exibição: nome + tamanho + link **baixar** (navegador escolhe onde salva);
  imagem (png/jpg/gif/webp) com **preview**.
- Quem entra depois **sincroniza** os arquivos das últimas 24h.
- **Teto 60 MB acumulados** em `dados/arquivos/`: passou disso, **apaga os mais
  antigos primeiro**. Valem as duas regras juntas: **>24h OU >60MB apaga**.
- Pasta inteira (código + dados) deve ficar **abaixo de 80 MB**.

## Mensagem privada (DM)

- Texto ou arquivo, vai **somente** para o destino, direto, **sem criptografia
  extra** — não passa pelos outros peers, mas trafega legível na rede
  local (qualquer pessoa na mesma rede pode observar).
- **Os outros peers não guardam nem encaminham** a DM — mas isso é
  comportamento do protocolo, não segredo: não há garantia contra
  observação na rede.
- **DM alcança quem estava offline**: o remetente guarda e **entrega direto
  quando o destino volta** (sem passar por terceiros). Se o remetente sair
  antes, a DM se perde (aceito).
- **Contrato de entrega (1.20, inalterado desde 1.12, compat com 1.11/1.10)**: `/api/enviar` responde `estado` ∈
  {`entregue`, `guardada`, `somente_memoria`, `erro`} + `transmitida`
  (bool, valores 1.10 intactos) + `nivel` ∈ {`local`, `socket`} + `confirmado=false`
  + `peers` (nº de peers conectados). Semântica explícita: `transmitida=true`
  na DM = bytes entregues ao socket; nos demais (pública/comandos locais) =
  aceitação local (publicado/aceito; reenvio duplicaria). `nivel=socket` só
  na DM com bytes no socket; resto é `local`. `confirmado` é sempre falso —
  hoje nunca há confirmação, então nada afirma recebimento/leitura. Campos
  novos são opcionais (ausentes = backend antigo); antigos intactos.
  A UI limpa o campo só
  em `entregue`/`guardada` (texto fora das mãos com destino certo); em
  `somente_memoria`/`erro` o texto é **preservado** para não induzir reenvio
  nem apagar o que não foi salvo. Caso especial honesto: `transmitida=true`
  + `somente_memoria` (o peer recebeu, mas aqui não foi salvo) → aviso "Mensagem
  transmitida, mas NÃO salva no histórico. Texto mantido como cópia", sem
  alegar recebimento, e o reenvio **idêntico fica bloqueado** até o texto ser
  editado (evita duplicata no destino). Pública aceita localmente não induz
  difusão/entrega: sem peers → "Publicada localmente, sem peers conectados —
  só você vê por enquanto."; com N peers → "Publicada localmente para N
  peer(s) — sem confirmação de recebimento ou leitura."; DM no socket →
  "Enviada — sem confirmação de recebimento ou leitura.". Sem `estado` (peer antigo), vale o fallback
  legado por texto.

## Histórico (merge estilo Lego)

- Quem entra depois **sincroniza** (últimas 24h, texto + metadados de arquivo;
  conteúdo puxado sob demanda).
- União por `mid`: cada evento existe uma vez — quem tem 17h–18h e quem tem
  18h–19h juntam tudo; mensagem que só um tem é aproveitada pelos outros.
- DMs nunca entram no sincronizado (vão só pela entrega direta acima).
- Cada PC grava em **arquivo local** e **apaga >24h** automaticamente.
- Dados ficam **no pendrive**, na pasta do app.

## Comandos do chat (híbrido: digitável + botões)

| Comando                 | O que faz                                           |
|-------------------------|-----------------------------------------------------|
| `/dm @apelido mensagem` | mensagem privada (texto; arquivo via anexo + `@`)   |
| `/quem`                 | lista quem está presente agora (também painel lateral) |
| `/rede`                 | IP/porta de cada par (também aba Configs)           |
| `/apelido novo`         | troca de apelido (também aba Configs)               |
| `/calar @apelido`       | toggle ver a pessoa (também aba Configs)            |
| `/ajuda`                | lista os comandos                                   |

Removidos na v2: `/sair` (agora Ctrl+C), `/limpar` (sem limpar tela).
Campo `@alvo` no formulário = DM. Anexo no formulário = arquivo.

## Atualizações de versão (assinadas pelo dono)

- Versão atual: **1.23** (26 arquivos; ver `03-progresso.md`). 1.11→1.12 testado entre
  releases reais (P2P + restart, ver `04-migracao.md`). Toda release tem número
  (`VERSAO` em `senderme_app/meta.py`).
- Quem tem versão maior **serve automaticamente** para quem tem menor na rede
  (oferta 1x por peer/versão em conexão viva, após envio confirmado; se o
  intervalo de 10 s suprimir a oferta com o peer ainda conectado, UMA nova
  tentativa sai ao fim do intervalo, sem precisar de novo anúncio).
- Quem recebe **aplica sozinho e reinicia** o servidor (sem perguntar).
- O pacote é **tudo** (código, CSS, README, docs) e é **assinado pela chave que
  só o dono tem** — sem assinatura válida, nada é aplicado; versão menor ou
  igual é rejeitada (sem downgrade). O envelope assinado é persistido para
  retransmissão (A→B→C).
- Exceções de migração (ver `04-migracao.md`): a **1.0 não tem código de
  update** — a ida 1.0→1.1 é **só via pendrive**; quem vem de **1.1–1.2** aplica
  o pacote mas precisa **rodar de novo `bash start.sh`** (launcher antigo só
  copia `senderme.py`+CSS e sai 0 mesmo com falha: não recopia os módulos
  novos nem propaga o erro).
- **Diário em arquivo (1.20)**: o app registra eventos técnicos em
  `logs/` na pasta do app (`senderme.log` rotativo: principal + 5 backups,
  ~6 MiB no total; `preboot.log` só quando o pre-boot age; `SENDERME_SEM_LOG=1`
  desliga tudo em arquivo, o terminal continua). Nunca guarda texto de
  mensagens/DMs, apelidos, nomes/conteúdo de arquivos, IPs completos, ids
  permanentes (peers saem como `peer-1`, `peer-2`… temporários por execução),
  dados arbitrários da rede (versões externas validadas), chaves, histórico
  nem caminhos pessoais — só horários, versão, tipos de evento, contadores
  e `/24` de IP. Coleta: copiar só a pasta `logs/` (nunca `dados/` junto).

## Passar para outro pendrive (jeito certo)

- **Nunca copiar `dados/`** (clona a identidade) **nem `dono/`** (vaza a chave).
- Jeito certo: o dono gera a pasta **`dist/SenderMe/`** com o script
  (`build_dist.sh`) — só código, zerada — e copia **essa pasta** para o pendrive.
- Usuário novo começa **zerado** (nova identidade na 1ª execução).

## Restrições de distribuição (pendrive)

- App mora **num pendrive** (alvos: FAT32/NTFS/exFAT, `noexec` — sem
  validação em dispositivo físico até aqui, ver `04-migracao.md`).
- **`start.sh`** copia o app para `/tmp` e executa de lá; dados continuam no
  pendrive (`SENDERME_HOME`). Abre o navegador sozinho (`xdg-open`).
- **Leve**: pasta inteira **< 80 MB** (código ~300 KB + arquivos até 60 MB).
- **Python 3 puro, zero dependências** (só o que já vem no Mint). Exceção só se
  algo for extremamente necessário (decisão: fica puro).
- **Bootstrap local** (`bootstrap.min.css` dentro da pasta, ~228 KB, offline).
  Sem CDN (rede local pode não ter internet).
