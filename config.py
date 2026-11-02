#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SenderMe — constantes e ajustes (portas, janelas, limites).

Folha sem dependências do resto do app: só lê variáveis de ambiente.
`senderme.py` re-exporta estes nomes (contrato dos testes, que usam `sm.*`).

Fora daqui (de propósito): `VERSAO`, `CHAVE_DONO_*` e `ARQUIVOS_UPDATE`
têm fonte única em `senderme_app/meta.py` (`dono/assinar_update.py` lê a
versão e a lista de lá por regex/import, e o manifesto assinado fixa
`ARQUIVOS_UPDATE` byte a byte; incluir aqui todo runtime novo).
"""
import os

PORTA_TCP = int(os.environ.get("SENDERME_PORTA", "13337"))
PORTA_UDP = int(os.environ.get("SENDERME_UDP_PORTA", "13338"))
PORTA_HTTP = int(os.environ.get("SENDERME_HTTP", "13336"))
FIXOS = [s.strip() for s in os.environ.get("SENDERME_FIXOS", "").split(",") if s.strip()]

RETENCAO = 24 * 3600
TIMEOUT_OFFLINE = 12
JANELA_ENTRADA = 90
JANELA_SAIDA = 60
INTERVALO_ANUNCIO = 3
INTERVALO_PURGA = 600
TIMEOUT_DIAL = 10
MAX_QUADRO = 8 * 1024 * 1024
MAX_TEXTO = 2000
MAX_SYNC = 1000
MAX_PENDENTES = 500
JANELA_HELLO = 60
MAX_ARQUIVO = 20 * 1024 * 1024      # 20 MB por arquivo
MAX_ARQUIVOS_TOTAL = 60 * 1024 * 1024  # 60 MB acumulados
CHUNK_ARQ = 512 * 1024              # 512 KB por chunk P2P
TIPOS_EVENTO = ("msg", "join", "leave", "nick", "dm", "file")
MAX_MIDS_INV = 5000                 # mids no inventário de sync
INTERVALO_PING = 5                  # s entre pings nas conexões
TIMEOUT_SOCK = 15                # s: recv e send nunca travam para sempre
