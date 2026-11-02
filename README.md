<div align="center">

# SenderMe

**Um chat para quem está na mesma rede.**

Converse e compartilhe arquivos pelo navegador, sem servidor central e sem depender de serviços na internet.

![Python 3](https://img.shields.io/badge/Python-3-3776AB?logo=python&logoColor=white)
![Rede local](https://img.shields.io/badge/rede-local-16837B)
![Dependências Python](https://img.shields.io/badge/dependências%20Python-nenhuma-555555)
![Plataforma](https://img.shields.io/badge/plataforma-Linux-FCC624?logo=linux&logoColor=black)

[Começar](#começar) · [Funcionalidades](#funcionalidades) · [Segurança](#segurança-e-privacidade) · [Documentação](#documentação)

</div>

---

O **SenderMe** conecta pessoas em uma rede local, como um laboratório de informática. Cada pessoa executa sua própria instância e acessa a interface no navegador. Os participantes trocam informações diretamente pela rede, sem uma conta online ou um servidor central do aplicativo.

> **Antes de conversar:** o tráfego não é criptografado. Mesmo as mensagens privadas podem ser observadas por outras pessoas com acesso à rede. Não envie senhas ou informações sensíveis. Leia [Segurança e privacidade](#segurança-e-privacidade).

> **Versão atual: 1.23** (release assinada: 26 arquivos + manifesto verificado; ver [Progresso](docs/03-progresso.md)). Cada release tem número (`VERSAO` em `senderme_app/meta.py`); versão igual ou inferior é rejeitada, sem downgrade.

## Funcionalidades

- **Chat em grupo:** envie mensagens para os participantes conectados.
- **Mensagens privadas:** converse com um participante usando seu apelido.
- **Envio de arquivos:** compartilhe arquivos de até 20 MiB; imagens compatíveis recebem prévia na conversa.
- **Presença na rede:** veja as pessoas encontradas e o estado da conexão com o aplicativo local.
- **Histórico temporário:** eventos recentes são mantidos localmente por até 24 horas e podem ser sincronizados entre participantes.
- **Atualizações assinadas:** versões compatíveis podem receber uma release mais recente pela rede e retransmiti-la.
- **Portabilidade:** os dados ficam junto da instalação, permitindo levar sua identidade em um pendrive.

> A release 1.23 foi validada em laboratório (boot da distribuição limpa, P2P 1.22→1.23 com restart automático, suíte de 412 testes). Rede da escola, carga com vários participantes e uso em pendrives físicos ainda precisam de validação no ambiente de destino.

## Como funciona

1. Cada participante inicia sua própria cópia do SenderMe.
2. O aplicativo abre uma interface web **local**, acessada no próprio computador.
3. As instâncias tentam se descobrir pela rede local e trocar mensagens diretamente.

Não é necessário acessar a internet para usar o chat após preparar os arquivos, mas os computadores precisam conseguir se comunicar pela rede. Algumas redes ou firewalls podem bloquear a descoberta ou as conexões entre participantes.

## Começar

### Requisitos

- Linux, com **Python 3** e **Bash** disponíveis.
- Um navegador web moderno.
- Computadores conectados a uma rede que permita comunicação entre eles.

O aplicativo usa a biblioteca padrão do Python: não é necessário instalar dependências Python com `pip`.

### Iniciar

Com os arquivos do projeto ou uma cópia da distribuição no computador ou pendrive:

1. Abra um terminal na pasta do SenderMe.
2. Execute:

   ```bash
   bash start.sh
   ```

3. Deixe o terminal aberto enquanto usa o aplicativo. O navegador deve abrir automaticamente. Se isso não acontecer, acesse:

   **http://127.0.0.1:13336**

4. Na primeira execução, escolha um apelido. A geração da identidade pode levar alguns segundos.

Para encerrar o SenderMe, volte ao terminal e pressione **Ctrl+C**.

> Use `bash start.sh` ao executar a partir de um pendrive. Os sistemas FAT32, exFAT e NTFS, assim como montagens `noexec`, são alvos previstos, mas ainda precisam de teste físico no ambiente de destino.

### Preparar uma cópia para outra pessoa

Se você está trabalhando com o repositório, gere uma distribuição limpa:

```bash
bash build_dist.sh
```

Copie a pasta gerada **`dist/SenderMe/`** para o outro pendrive. Ao iniciá-la pela primeira vez, a outra pessoa terá sua própria identidade.

**Não copie sua pasta `dados/` para distribuir o aplicativo:** ela contém sua identidade e seu histórico. O build de release verifica o manifesto assinado e falha se os arquivos não corresponderem a ele. A assinatura de uma nova release é uma operação separada, realizada pelo responsável pelo projeto.

## Usando o chat

### Mensagens e arquivos

Digite uma mensagem e pressione **Enter** para enviá-la. Use **Shift+Enter** para inserir uma nova linha. O limite é de 2.000 caracteres por mensagem.

Para enviar um arquivo, selecione-o no campo **Anexo** e envie. Cada arquivo pode ter até **20 MiB**. O armazenamento local de arquivos tem limite acumulado de **60 MiB**; arquivos antigos podem ser removidos conforme a retenção e o limite do aplicativo.

Para enviar uma mensagem privada, preencha o campo de destino com `@apelido` ou use:

```text
/dm @apelido sua mensagem aqui
```

O aplicativo não confirma que o destinatário leu a mensagem. Uma mensagem privada é direcionada ao destinatário, mas **não é criptografada**.

### Comandos

| Comando | O que faz |
| --- | --- |
| `/dm @apelido mensagem` | Envia uma mensagem privada. |
| `/quem` | Lista participantes presentes. |
| `/rede` | Mostra informações sobre as conexões. |
| `/apelido novo` | Altera seu apelido. |
| `/calar @apelido` | Ativa ou desativa o silenciamento de uma pessoa. |
| `/ajuda` | Mostra a ajuda dentro do aplicativo. |

## Rede e portas

Por padrão, o SenderMe usa:

| Porta | Protocolo | Uso |
| --- | --- | --- |
| `13337` | TCP | Comunicação entre participantes. |
| `13338` | UDP | Descoberta de participantes na rede local. |
| `13336` | TCP | Interface web local, em `127.0.0.1`. |

Se ninguém aparecer, confirme que os computadores estão na mesma rede e que o firewall permite a comunicação necessária. Quando a descoberta automática não funcionar, é possível informar pares conhecidos:

```bash
SENDERME_FIXOS=192.168.0.5:13337,192.168.0.8:13337 bash start.sh
```

Substitua os endereços pelos IPs e portas reais dos participantes. As portas também podem ser configuradas pelas variáveis de ambiente abaixo.

<details>
<summary><strong>Variáveis de ambiente</strong></summary>

| Variável | Função | Padrão |
| --- | --- | --- |
| `SENDERME_PORTA` | Porta TCP de comunicação entre participantes. | `13337` |
| `SENDERME_UDP_PORTA` | Porta UDP de descoberta. | `13338` |
| `SENDERME_HTTP` | Porta da interface web local. | `13336` |
| `SENDERME_FIXOS` | Lista de pares `ip:porta`, separados por vírgulas. | Vazia |
| `SENDERME_HOME` | Pasta usada para dados e logs. | Pasta da instalação |
| `SENDERME_SEM_LOG` | Defina como `1` para desativar os logs em arquivo. | Logs ativados |
| `SENDERME_NO_BROADCAST` | Defina como `1` para suprimir o broadcast UDP em testes. | Broadcast ativado |

O `start.sh` define `SENDERME_HOME` como a pasta da instalação. Para testar duas instâncias no mesmo computador, use diretórios e portas diferentes; consulte [AGENTS.md](AGENTS.md) para os comandos de teste isolado.

</details>

## Atualizações

Uma instância com uma versão mais recente pode oferecer a atualização a um participante com versão anterior. O destinatário verifica a assinatura e os arquivos antes de aplicar a release. Quando o caminho é compatível, o aplicativo reinicia e pode retransmitir a atualização.

Não é necessário instalar cada versão intermediária nos caminhos compatíveis. A compatibilidade de atualizações deve ser verificada a cada release; em caso de falha, pode ser necessária uma migração manual.

Limitações conhecidas das versões iniciais de desenvolvimento, anteriores à primeira distribuição — são casos diferentes:

- **Base ≤1.2:** o launcher antigo copia só `senderme.py`+CSS para `/tmp` e sai 0 mesmo quando o Python falha (`ModuleNotFoundError`), sem persistir o envelope novo. O P2P aplica os arquivos mas **não auto-reinicia** — migração sempre manual. Reproduzido aqui com o `start.sh` real do commit `24176fa` (`tests/test_migracao_legada.py`).
- **Release 1.6:** o manifesto listava 25 arquivos e deixava `senderme_app/preboot.py` de fora (drift). Apontado em revisão externa com chaves sintéticas; **não há árvore 1.6 byte-exata neste repositório**, então esse caminho é marcado como não-executável na matriz.

Os detalhes e os caminhos testados estão na [matriz de migração](docs/04-migracao.md).

Antes de migrar uma instalação existente, preserve uma cópia de `dados/` e consulte a [matriz e as instruções de migração](docs/04-migracao.md). Não distribua sua identidade para outras pessoas.

## Dados e logs

O diretório `dados/` guarda informações da instalação, incluindo identidade, apelido, histórico e arquivos recebidos. Faça backup se quiser preservar sua identidade e suas conversas locais.

Os logs técnicos ficam em `logs/`, dentro da instalação. Os arquivos principais são `senderme.log` e suas cópias rotativas; `preboot.log` pode aparecer quando há recuperação de uma atualização. Para desativar a gravação em arquivo:

```bash
SENDERME_SEM_LOG=1 bash start.sh
```

Os logs foram projetados para evitar conteúdos de mensagens e outros dados sensíveis. Ainda assim, **revise os arquivos antes de compartilhá-los**. Não envie `dados/` junto com um relatório de erro: essa pasta inclui a chave da sua identidade e o histórico.

## Segurança e privacidade

- **Sem criptografia de transporte:** mensagens e arquivos podem ser observados na rede local. Isso também se aplica a mensagens privadas.
- **Identidades e assinaturas:** mensagens e arquivos são assinados para verificar a autoria em relação à chave conhecida. Isso não estabelece, por si só, a identidade real de uma pessoa: apelidos podem ser reutilizados e não há PKI.
- **Atualizações assinadas:** a assinatura ajuda a verificar a autenticidade da release; ela não torna as conversas confidenciais.
- **Interface local:** a API web escuta em `127.0.0.1`. Ela possui proteções para requisições de origem externa, mas não usa autenticação de cliente nem token por sessão.
- **Auditoria:** o projeto ainda não passou por auditoria externa de segurança ou criptografia.

Use o SenderMe em redes e contextos adequados a essas limitações. Não use o aplicativo para transmitir segredos.

## Solução de problemas

**O navegador não abriu.** Acesse manualmente `http://127.0.0.1:13336` e confira se o terminal do SenderMe continua aberto.

**Ninguém aparece.** Confirme a rede, o firewall e as portas TCP/UDP. Se necessário, tente `SENDERME_FIXOS` com o endereço de outro participante.

**A porta está ocupada.** Encerre a instância anterior ou configure portas diferentes. Uma interface em outra porta precisa ser acessada pelo endereço correspondente no navegador.

**A primeira inicialização está demorando.** A geração da chave de identidade pode levar algum tempo. Acompanhe as mensagens no terminal.

**A identidade está inválida.** Preserve uma cópia de `dados/` antes de qualquer alteração. Apagar a identidade gera outra e faz você perder a identidade anterior.

**A atualização falhou.** Preserve `dados/`, consulte os logs e veja [Migração e distribuição](docs/04-migracao.md). Versões antigas podem exigir atualização manual.

## Desenvolvimento e testes

```bash
python3 -m unittest discover -s tests -v
```

A suíte usa `unittest` (412 testes, verificado em 2026-11-02). Alguns testes têm requisitos adicionais, como Node.js, Chromium ou histórico Git específico; quando não estão disponíveis, podem ser pulados. Leia o resultado completo, incluindo `skipped`, para saber o que foi efetivamente executado.

O projeto usa Python da biblioteca padrão, interface HTML/CSS/JavaScript servida localmente e Bootstrap incluído para uso offline. O ponto de entrada é `senderme.py`; os módulos do aplicativo ficam em `senderme_app/`.

## Documentação

- [Produto](docs/01-produto.md) — objetivos e comportamento do aplicativo.
- [Arquitetura](docs/02-arquitetura.md) — componentes, rede e decisões técnicas.
- [Progresso](docs/03-progresso.md) — histórico do projeto e validações.
- [Migração e distribuição](docs/04-migracao.md) — atualização entre versões e recuperação.
- [Roteiro de teste na escola](ROTEIRO-ESCOLA.md) — roteiro para o responsável pelos testes.
- [Ideias para o futuro](docs/futuras_features.md) — funcionalidades consideradas para depois.
- [Instruções de desenvolvimento](AGENTS.md) — regras e orientações para trabalhar no repositório.

## Licença e terceiros

A licença do código do SenderMe **ainda não foi definida** pelo responsável pelo projeto.

O projeto inclui [Bootstrap](https://getbootstrap.com/) 5.3.3, distribuído sob licença MIT. Os avisos e o texto da licença desse componente estão em [TERCEIROS.md](TERCEIROS.md). A licença do Bootstrap se aplica ao Bootstrap e não define a licença do SenderMe.
