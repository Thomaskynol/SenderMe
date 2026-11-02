#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SenderMe — versão, chave pública do dono e lista de arquivos do update.

Fonte única (single source) de:
- `VERSAO`: `dono/assinar_update.py` lê este arquivo por regex (mesmo padrão
  de antes, novo caminho) e o manifesto assinado fixa a versão.
- `ARQUIVOS_UPDATE`: start.sh, build_dist.sh e manifesto devem cobrir estes
  arquivos (há teste que confere); incluir aqui todo runtime novo.
"""
import os

VERSAO = os.environ.get("SENDERME_VERSAO", "1.23")
CHAVE_DONO_E = 65537
CHAVE_DONO_N = ("cfe2bc67e5d2ab9dd4532099ed1fa5fff0884a7fe8ba6c21447ddef5c943cb8f2bd03be95a159"
                "ae31b54d00fc7ab1e47465f3b998bcecec4cc0ecf9a7267045782347015e7eda1b890a6ac98a0a1f597d39"
                "432a526dcea33306efeff75805630bbabd28017d2d91826bf76583ced13c6a1146413820440ebfd03684b"
                "8a091ae74396eaf77c87e6be4486cc92eadb792d2f1e7c32530f2e5b278f9769c8831c4e941854aa9a50d8"
                "97004e32506baccd7efd0360bdb8f3a1bb6e7ba81e56d451e277adee2e7fc2945604305d0f1278b871998f"
                "0234faa11e5d8632234a2a15a212d445bbd3ae18d1ab79a9e31c39768e606fdb09290d04ba9a9f72950ee6"
                "c8927d")
ARQUIVOS_UPDATE = ["senderme.py", "config.py", "crypto.py", "pagina.py",
                   "bootstrap.min.css", "TERCEIROS.md", "start.sh",
                   # Só runtime: README/docs/roteiro ficam no repo, fora da
                   # dist e fora do conjunto assinado (instalação antiga
                   # mantém seus docs no disco; o update nunca os apaga).
                   "senderme_app/__init__.py", "senderme_app/meta.py",
                   "senderme_app/estado.py", "senderme_app/persist.py",
                   "senderme_app/presenca.py", "senderme_app/eventos.py",
                   "senderme_app/arquivos.py", "senderme_app/transporte.py",
                   "senderme_app/tcp.py", "senderme_app/udp.py",
                   "senderme_app/manut.py", "senderme_app/update.py",
                   "senderme_app/update_store.py",
                   "senderme_app/comandos.py", "senderme_app/http.py",
                   "senderme_app/app.py", "senderme_app/preboot.py",
                   "senderme_app/diario.py",
                   "senderme_app/update_proto.py"]
