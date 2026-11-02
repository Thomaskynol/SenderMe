#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SenderMe v2 — chat P2P na rede local com interface de navegador.

- Sem servidor central: cada participante propaga mensagens (gossip).
- Python 3 puro, só biblioteca padrão.
- Rede P2P: TCP 13337 (conversa) + UDP 13338 (descoberta).
- Interface web local: HTTP 127.0.0.1:13336 (só nesta máquina).

Ponto de entrada fino: a lógica mora em `senderme_app/` (um módulo por
responsabilidade). Este arquivo re-exporta o contrato público (`sm.*` usado
por testes e `dono/assinar_update.py`) e delega o estado mutável ao dono
(`senderme_app.estado`) via __getattr__/__setattr__ — nunca importe variável
mutável por valor a partir daqui.
"""
import os
import sys

from senderme_app import estado as _estado
from senderme_app.estado import L, agora, log, id_curto, ip_local
from senderme_app.meta import VERSAO, CHAVE_DONO_E, CHAVE_DONO_N, ARQUIVOS_UPDATE
from config import (CHUNK_ARQ, FIXOS, INTERVALO_ANUNCIO, INTERVALO_PING,
                    INTERVALO_PURGA, JANELA_ENTRADA, JANELA_HELLO,
                    JANELA_SAIDA, MAX_ARQUIVO, MAX_ARQUIVOS_TOTAL,
                    MAX_MIDS_INV, MAX_PENDENTES, MAX_QUADRO, MAX_SYNC,
                    MAX_TEXTO, PORTA_HTTP, PORTA_TCP, PORTA_UDP, RETENCAO,
                    TIMEOUT_DIAL, TIMEOUT_OFFLINE, TIMEOUT_SOCK,
                    TIPOS_EVENTO)
from crypto import _inv, _miller_rabin, _primo, assinar, conferir, fingerprint
from pagina import PAGINA
from senderme_app.persist import (_caminho, garantir_dados, ler_json,
                                  salvar_json, anexar_historico, anexar_lote,
                                  reescrever_historico, salvar_conhecidos,
                                  salvar_calados, carregar_identidade,
                                  carregar_conhecidos, carregar_historico,
                                  gerar_chave)
from senderme_app.eventos import (campo_assinatura, criar_evento,
                                  limpar_nome_arq, criar_evento_file,
                                  conferir_evento, guardar_pendente, pedir_pub,
                                  receber_pub, pedir_arquivo, processar,
                                  publicar, propagar, reconstruir, tratar_hist)
from senderme_app.presenca import (aplicar_nick, dono_do_apelido,
                                   apelido_exibido, apelido_de, silenciado,
                                   em_uso_online, presente, autor_silenciado,
                                   tem_conexao_minha, pode_exibir_saida,
                                   lista_presentes, texto_quem)
from senderme_app.arquivos import (caminho_bin, tem_arquivo,
                                   salvar_bytes_arquivo, ler_bytes_arquivo,
                                   total_arquivos, evento_por_mid,
                                   purgar_arquivos, servir_arquivo,
                                   receber_chunk)
from senderme_app.transporte import (enviar, ler_quadro, preparar_socket,
                                     fechar_socket)
from senderme_app.tcp import (msg_pub, registrar_conexao, ler_loop,
                              tratar_quadro, dialar, abrir_servidor,
                              loop_aceitar)
from senderme_app.udp import (campo_hello, montar_hello, tratar_hello,
                              thread_udp)
from senderme_app.manut import (alvos_de_discagem, anunciar_entrada,
                                anunciar_saida, ausentes, manutencao,
                                thread_manutencao, thread_purga,
                                dms_pendentes_para, tentar_entregar_dm)
from senderme_app.update import (ver_tupla, manifest_canonico,
                                 conferir_manifest, caminho_update_origem,
                                 tratar_ver, ler_manifest_local,
                                 empurrar_update, receber_update_meta,
                                 baixar_update, nome_update_ok, servir_update,
                                 receber_update_chunk, finalizar_update,
                                 recuperar_update)
from senderme_app.comandos import (AJUDA_TXT, validar_nick, fazer_login,
                                   trocar_apelido, toggle_calar,
                                   enviar_dm_para, enviar_dm_arquivo,
                                   publicar_arquivo_global, tratar_comando_web,
                                   achar_id, texto_rede, hora_de, cor_idx,
                                   evento_para_api, mensagens_para_api)
from senderme_app.http import (Handler, thread_http, _json, _parse_multipart)
from senderme_app.app import purgar, main, desligar
from senderme_app.diario import (RUN_ID, caminho_log, curto, iniciar as
                                 iniciar_diario, instalar_hook_threads,
                                 mascarar_ip, sanear_versao,
                                 registrar as registrar_diario)


class _Shim(__import__("types").ModuleType):
    """Compat `import senderme as sm`: funções resolvem no namespace normal;
    todo nome de estado mutável lê/escreve em senderme_app.estado (dono)."""

    def __getattr__(self, name):
        return getattr(_estado, name)

    def __setattr__(self, name, value):
        if name in _estado.__dict__:
            setattr(_estado, name, value)
        else:
            super().__setattr__(name, value)


sys.modules[__name__].__class__ = _Shim


if __name__ == "__main__":
    if "--help" in sys.argv or "-h" in sys.argv:
        print("SenderMe %s — chat P2P na rede local (Python 3, sem dependências)." % VERSAO)
        print("Uso: SENDERME_HOME=/tmp/sm-x SENDERME_FIXOS=127.0.0.1:<porta> python3 senderme.py")
        print("Web local: http://127.0.0.1:%d (login no navegador)." % PORTA_HTTP)
        sys.exit(0)
    try:
        main()
    except KeyboardInterrupt:
        desligar()
