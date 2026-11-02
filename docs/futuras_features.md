# SenderMe — funcionalidades futuras

**Estado:** ideias escolhidas para discutir e modelar depois. Elas **não fazem parte da rodada atual** de melhorias da interface existente, revisão, organização e distribuição.

Este documento registra intenções, não uma especificação pronta nem autorização para implementar agora. Antes de cada funcionalidade, definir com o dono a experiência, as regras e os testes. Verificar o estado atual do projeto, pois algumas capacidades podem já existir parcialmente.

## Conexão e participantes

1. **Indicador de conexão com a rede.** Distinguir a interface conectada ao servidor local da conexão com outros participantes; mostrar uma situação compreensível quando não houver peers.
2. **Ajuda de conexão dentro do app.** Orientar o usuário quando colegas não aparecerem e estudar uma forma mais simples de conectar a um endereço conhecido. Não prometer conexão se a rede bloquear o tráfego.
3. **Perfil e presença mais claros.** Melhorar a apresentação de participantes e seus estados de presença, considerando atrasos e quedas de rede.
4. **Cartão de diagnóstico.** Apresentar dados técnicos úteis, como versão, situação dos serviços e quantidade de peers, sem expor chaves, histórico ou outros dados sensíveis.

## Mensagens e conversas

5. **Estados mais claros para mensagens e DMs.** Diferenciar armazenamento local, espera, transmissão e confirmação, conforme o que o sistema realmente souber. A confirmação de recebimento depende de suporte no protocolo; não confundir bytes enviados com mensagem recebida ou lida.
6. **Conversas privadas separadas.** Organizar DMs em conversas próprias; o formato visual e a navegação (lista, abas ou outra opção) ainda serão decididos.
7. **Menções com `@apelido`.** Permitir mencionar um participante e dar destaque à menção; definir comportamento quando houver homônimos ou mudanças de apelido.
8. **Contador de mensagens não lidas.** Indicar conteúdo não visto no chat geral e nas conversas privadas; definir quando uma mensagem passa a ser considerada lida.
9. **Responder a uma mensagem específica.** Referenciar a mensagem original, incluindo comportamento quando ela não estiver mais disponível.
10. **Reações com emojis.** Adicionar e remover reações e definir como serão sincronizadas entre peers.
11. **Busca no histórico.** Pesquisar mensagens disponíveis localmente, com escopo, filtros e limites definidos na modelagem.
12. **Silenciar por conversa.** Definir o que será silenciado, como mensagens e notificações, e a relação com o recurso atual de silenciar usuários.

## Arquivos e imagens

13. **Estado visível de transferências.** Mostrar, quando possível, disponibilidade, transferência, progresso, falha e nova tentativa. Diferenciar transferência entre peers do download final gerenciado pelo navegador.
14. **Colar imagens no chat.** Permitir colar imagens diretamente na composição, com prévia e respeitando os limites de tamanho e as capacidades do navegador.
15. **Arrastar e soltar arquivos.** Facilitar a seleção de anexos, mostrando o que será enviado e permitindo cancelar antes do envio.

## Interface e controles

16. **Botão para sair na interface.** Estudar uma forma clara e segura de encerrar a sessão/servidor pelo navegador, além do modo atual pelo terminal.
17. **Tema claro/escuro e ajustes visuais.** Permitir mudar a aparência e, se desejado, ajustar a apresentação. O redesenho da interface existente desta rodada não significa que esses controles configuráveis já tenham sido aprovados para implementação.

## Decisões ainda em aberto

- Navegação das conversas privadas: lista lateral, abas ou outro formato.
- Confirmações: recebimento pelo dispositivo, leitura/visualização ou outros estados, inclusive privacidade.
- Retenção do histórico: a versão 1.20 documenta 24 horas; decidir se será mantida, ampliada ou configurável.
- Comportamento de menções, reações e não lidas quando pessoas estiverem offline ou usarem versões diferentes.
- Limites de arquivos e armazenamento, efeitos no pendrive e o que acontece quando o conteúdo expira ou é removido.
- Notificações: definir se e como serão adicionadas junto com menções ou conversas, permissões e privacidade.

## Contexto a preservar quando forem modeladas

O SenderMe é um chat P2P em rede local, sem servidor central, executado em Python com biblioteca padrão. A distribuição e as atualizações são assinadas e precisam continuar funcionando nos pendrives, incluindo compatibilidade com versões anteriores quando suportada.

Na versão 1.20, as DMs não têm criptografia de ponta a ponta; não prometer confidencialidade. O histórico e os dados ficam no dispositivo. Dados de usuários, identidade e chaves privadas não devem entrar na distribuição, nos testes de terceiros ou em pacotes de revisão.

A ordem de implementação e o escopo de cada etapa serão definidos depois, considerando os resultados do teste presencial na escola.

