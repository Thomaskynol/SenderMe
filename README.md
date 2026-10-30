# SenderMe (v2 navegador)

Chat global com **texto multilinha + arquivos**, pelo **navegador**,
**só na rede local**. **Sem servidor central**: cada participante é um peer
e ajuda os outros a propagar. Quem não tem o aplicativo não vê nem ouve.

- Python 3 puro, **zero dependências** (só o `python3` do Mint).
- `senderme.py` + `bootstrap.min.css` (offline) + `start.sh`.
- Dados ficam **na pasta do app** (pendrive): mesma pessoa em qualquer PC.
- Assinatura RSA-2048 em cada mensagem/arquivo: ninguém se passa por outro.
- Histórico local **24 h** (data + hora `DD/MM HH:MM`), sincronizado para quem
  entra depois.
- Arquivos até **20 MB**, teto **60 MB** acumulados (apaga os mais antigos).
- Pasta inteira **< 80 MB**.

## Como usar

1. Copie a pasta `SenderMe` para o pendrive (FAT32/NTFS ok).
2. Abra o terminal **na pasta do app** e rode:

   ```bash
   bash start.sh
   ```

   O terminal fica como **servidor** (deixe aberto). O navegador abre sozinho
   em `http://127.0.0.1:13336`. (`bash`, não `./start.sh`: FAT não tem bit de
   execução; o script copia para `/tmp` por causa do `noexec`.)
3. Na 1ª vez escolha seu apelido. Depois **entra direto** (fica salvo).
   Se estiver em uso, pede outro. Troca só na aba **Configs**.
4. Pronto: mensagem de "entrou no chat" aparece após o login.

Para sair: **Ctrl+C** no terminal do servidor (avisa todo mundo).

## Versão e atualizações

- Versão atual: **1.2** (aparece ao lado do nome no navegador).
- Quem tem versão maior **serve automaticamente** para a rede; quem recebe
  **aplica sozinho e reinicia** (o terminal mostra "update aplicado").
- Updates são **assinados pela chave do dono** — sem assinatura válida nada
  é aplicado, e não há downgrade.
- Atenção: a **1.0 não recebe update pela rede** (atualize via pendrive).

## Passar para outro pendrive (jeito certo)

Nunca copie a pasta com `dados/` (clona sua identidade). Gere a build limpa:

```bash
python3 dono/assinar_update.py   # só o dono, após mudar a VERSAO
bash build_dist.sh               # gera dist/SenderMe zerada
```

Copie **`dist/SenderMe`** para o pendrive. O usuário novo começa zerado
(nova identidade) e pode reusar o apelido antigo.

## Mensagens e arquivos

- `Enter` envia, `Shift+Enter` quebra linha. Máx. 2000 caracteres de texto.
- Anexo: qualquer tipo até 20 MB. Imagem mostra preview + link baixar.
- Campo `@alvo` + texto/anexo = DM (só o destino vê).
- O que foi falado, ficou: sem apagar nem editar.

## Comandos (digitáveis + botões)

| Comando                 | O que faz                                            |
|-------------------------|------------------------------------------------------|
| `/dm @apelido mensagem` | mensagem privada                                     |
| `/quem`                 | quem está presente (também painel lateral)           |
| `/rede`                 | IP/porta dos pares (também aba Configs)              |
| `/apelido novo`         | troca apelido (também aba Configs)                   |
| `/calar @apelido`       | toggle ver a pessoa (também aba Configs)             |
| `/ajuda`                | lista os comandos                                    |

`/sair` e `/limpar` foram removidos (sair = Ctrl+C).

## Rede e firewall

- **TCP 13337** — conversa P2P. **UDP 13338** — descoberta. **TCP 13336** — web
  local (só `127.0.0.1`, não precisa liberar no firewall).
- Se ninguém aparecer, tente `SENDERME_FIXOS` (roteador bloqueando broadcast).

## Variáveis de ambiente

| Variável             | Efeito                                              |
|----------------------|-----------------------------------------------------|
| `SENDERME_HOME`      | pasta dos dados (o `start.sh` já define)            |
| `SENDERME_PORTA`     | TCP P2P (default 13337)                             |
| `SENDERME_UDP_PORTA` | UDP (default 13338)                                 |
| `SENDERME_HTTP`      | HTTP local (default 13336)                          |
| `SENDERME_FIXOS`     | pares fixos `ip:porta,ip:porta`                     |

```bash
SENDERME_FIXOS=192.168.0.5:13337,192.168.0.8:13337 bash start.sh
```

Duas instâncias no mesmo PC (teste):

```bash
SENDERME_HOME=/tmp/sm-a SENDERME_PORTA=13337 SENDERME_UDP_PORTA=13338 SENDERME_HTTP=13336 \
  SENDERME_FIXOS=127.0.0.1:13347 python3 senderme.py

SENDERME_HOME=/tmp/sm-b SENDERME_PORTA=13347 SENDERME_UDP_PORTA=13348 SENDERME_HTTP=13346 \
  SENDERME_FIXOS=127.0.0.1:13337 python3 senderme.py
# abra http://127.0.0.1:13336 e http://127.0.0.1:13346
```

## Onde ficam os dados

Em `dados/` na pasta do app:

| Arquivo            | Conteúdo                                            |
|--------------------|-----------------------------------------------------|
| `identidade.json`  | sua chave (**não copie a pasta**)                   |
| `historico.jsonl`  | eventos 24 h                                        |
| `conhecidos.json`  | chaves e apelidos conhecidos                        |
| `calados.json`     | silenciados                                         |
| `apelido.txt`      | apelido salvo (auto-login)                          |
| `arquivos/*.bin`   | conteúdos (teto 60 MB + 24 h)                       |

## Problemas comuns

- **Porta TCP ocupada** — já tem instância rodando; use portas diferentes.
- **Ninguém aparece** — mesma rede? firewall? tente `SENDERME_FIXOS`.
- **1ª execução demora** — gerando RSA-2048, uma vez só.
