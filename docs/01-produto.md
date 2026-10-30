# SenderMe — Requisitos do Produto (v2 navegador, versão 1.1)

> Decididos em conversa com o usuário. Tudo aqui é decisão fechada, não sugestão.
> v1 era terminal. v2 é **navegador**, modo terminal **removido**.

## O que é

Chat global com **texto multilinha + arquivos**, pelo **navegador**, funcionando
**apenas na rede local**. **Sem servidor central.** Cada participante é um peer
independente e ajuda os outros a propagar as mensagens — modelo descentralizado.

Quem **não** tem o aplicativo **não vê nem ouve** o chat.

## Plataforma

- **Linux Mint**, apenas.
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
- Cada mensagem/arquivo é **assinado digitalmente** — ninguém se passa por outro.
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
  extra** — basta não ir para os outros.
- **Ninguém mais fica sabendo** que houve DM — nem mesmo para guardar/encaminhar.
- **DM alcança quem estava offline**: o remetente guarda e **entrega direto
  quando o destino volta** (sem passar por terceiros). Se o remetente sair
  antes, a DM se perde (aceito).

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

- Versão atual: **1.1**. Toda release tem número (`VERSAO` no código).
- Quem tem versão maior **serve automaticamente** para quem tem menor na rede.
- Quem recebe **aplica sozinho e reinicia** o servidor (sem perguntar).
- O pacote é **tudo** (código, CSS, README, docs) e é **assinado pela chave que
  só o dono tem** — sem assinatura válida, nada é aplicado; versão menor ou
  igual é rejeitada (sem downgrade).
- Exceção: a **1.0 não sabe verificar updates** (não tem o código) — a ida
  1.0→1.1 é **só via pendrive**; do 1.1 em diante vale o P2P.

## Passar para outro pendrive (jeito certo)

- **Nunca copiar `dados/`** (clona a identidade) **nem `dono/`** (vaza a chave).
- Jeito certo: o dono gera a pasta **`dist/SenderMe/`** com o script
  (`build_dist.sh`) — só código, zerada — e copia **essa pasta** para o pendrive.
- Usuário novo começa **zerado** (nova identidade na 1ª execução).

## Restrições de distribuição (pendrive)

- App mora **num pendrive** (FAT32/NTFS/exFAT, `noexec`).
- **`start.sh`** copia o app para `/tmp` e executa de lá; dados continuam no
  pendrive (`SENDERME_HOME`). Abre o navegador sozinho (`xdg-open`).
- **Leve**: pasta inteira **< 80 MB** (código ~300 KB + arquivos até 60 MB).
- **Python 3 puro, zero dependências** (só o que já vem no Mint). Exceção só se
  algo for extremamente necessário (decisão: fica puro).
- **Bootstrap local** (`bootstrap.min.css` dentro da pasta, ~228 KB, offline).
  Sem CDN (rede local pode não ter internet).
