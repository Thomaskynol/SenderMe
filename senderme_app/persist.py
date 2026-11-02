#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SenderMe — persist (extraído de senderme.py sem mudar lógica)."""
import os
import json
from . import estado as S
from . import diario as D
from .estado import agora, log
from .presenca import aplicar_nick
from config import RETENCAO
from crypto import fingerprint
from crypto import gerar_chave as _gerar_chave


def _caminho(nome):
    return os.path.join(S.DADOS, nome)


def garantir_dados():
    try:
        os.makedirs(S.DADOS, exist_ok=True)
        os.makedirs(S.DIR_ARQ, exist_ok=True)
    except OSError:
        return False
    return True


def ler_json(nome, padrao):
    try:
        with open(_caminho(nome), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return padrao


def salvar_json(nome, obj):
    """Grava JSON com tmp+replace. Retorna True se persistiu, False se falhou
    (chamador crítico deve checar; nunca alegar sucesso sem conferir)."""
    garantir_dados()
    with S._disco:
        try:
            tmp = _caminho(nome) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False)
            os.replace(tmp, _caminho(nome))
        except Exception:
            D.registrar("persist_falha", op="salvar", arq=nome)
            return False
    return True


def anexar_historico(ev):
    garantir_dados()
    with S._disco:
        try:
            with open(_caminho("historico.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        except Exception:
            D.registrar("persist_falha", op="anexar", arq="historico.jsonl")
            return False
    return True


def anexar_lote(evs):
    """Grava vários eventos com uma única abertura de arquivo (sync em lote)."""
    if not evs:
        return True
    garantir_dados()
    with S._disco:
        try:
            with open(_caminho("historico.jsonl"), "a", encoding="utf-8") as f:
                f.write("".join(json.dumps(ev, ensure_ascii=False) + "\n"
                                for ev in evs))
        except Exception:
            D.registrar("persist_falha", op="anexar_lote", arq="historico.jsonl")
            return False
    return True


def reescrever_historico():
    garantir_dados()
    with S._disco:
        try:
            tmp = _caminho("historico.jsonl") + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                for ev in S.historico:
                    f.write(json.dumps(ev, ensure_ascii=False) + "\n")
            os.replace(tmp, _caminho("historico.jsonl"))
        except Exception:
            D.registrar("persist_falha", op="reescrever", arq="historico.jsonl")
            return False
    return True


def salvar_conhecidos():
    """Retorna True se persistiu (repasse do bool de salvar_json)."""
    saida = {}
    for idp, d in S.conhecidos.items():
        saida[idp] = {"n": format(d["n"], "x"), "e": d["e"], "nick": d.get("nick", "")}
    return salvar_json("conhecidos.json", saida)


def salvar_calados():
    """Retorna True se persistiu (repasse do bool de salvar_json)."""
    return salvar_json("calados.json", sorted(S.calados))


def carregar_identidade():
    """Distingue ausente (1ª execução) de inválido/ilegível (nunca sobrescreve).

    - Arquivo inexistente: gera, grava e retorna; se a gravação falhar,
      aborta com SystemExit (não alega identidade salva).
    - Arquivo existente porém inválido/incompleto/ilegível: preserva os bytes
      e aborta com SystemExit acionável (nada é sobrescrito)."""
    caminho = _caminho("identidade.json")
    ausente = False
    try:
        with open(caminho, encoding="utf-8") as f:
            bruto = json.load(f)
    except FileNotFoundError:
        bruto, ausente = None, True
    except (OSError, ValueError, UnicodeError) as e:
        raise SystemExit(
            "identidade.json existe mas não consegui ler (%s). Nada foi "
            "alterado: confira disco/permissão, faça backup do arquivo e "
            "corrija ou apague-o para gerar nova identidade." % (e,))
    if ausente:
        chave = gerar_chave()
        idp = fingerprint(chave["n"], chave["e"])
        doc = {"n": format(chave["n"], "x"), "e": chave["e"],
               "d": format(chave["d"], "x"), "id": idp}
        if not salvar_json("identidade.json", doc):
            raise SystemExit(
                "não consegui gravar identidade.json em %s: identidade NÃO "
                "foi salva (disco cheio ou sem permissão?)." % caminho)
        try:
            os.chmod(caminho, 0o600)
        except OSError:
            pass
        return {"n": chave["n"], "e": chave["e"], "d": chave["d"], "id": idp}
    try:
        if not isinstance(bruto, dict):
            raise ValueError("conteúdo não é um objeto JSON")
        n = int(bruto["n"], 16)
        e = int(bruto["e"])
        d = int(bruto["d"], 16)
        idp = fingerprint(n, e)
    except (KeyError, ValueError, TypeError, AttributeError) as ex:
        raise SystemExit(
            "identidade.json inválido ou incompleto (%s). Arquivo preservado "
            "em %s: faça backup, corrija ou apague-o para gerar nova "
            "identidade (a antiga será perdida)." % (ex, caminho))
    if bruto.get("id") and bruto["id"] != idp:
        raise SystemExit(
            "identidade.json corrompido (id não confere). Arquivo preservado "
            "em %s." % caminho)
    return {"n": n, "e": e, "d": d, "id": idp}


def carregar_conhecidos():
    bruto = ler_json("conhecidos.json", {})
    for idp, d in (bruto or {}).items():
        try:
            S.conhecidos[idp] = {"n": int(d["n"], 16), "e": int(d["e"]),
                               "nick": d.get("nick", "")}
            if d.get("nick"):
                aplicar_nick(idp, d["nick"], ts=0)
        except Exception:
            continue


def carregar_historico():
    bruto = []
    try:
        with open(_caminho("historico.jsonl"), encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    ev = json.loads(linha)
                except Exception:
                    continue
                if isinstance(ev, dict):
                    bruto.append(ev)
    except FileNotFoundError:
        return []
    limite = agora() - RETENCAO
    bruto = [e for e in bruto if e.get("ts", 0) >= limite]
    bruto.sort(key=lambda e: (e.get("ts", 0), e.get("mid", "")))
    return bruto


def gerar_chave():
    log("Gerando chave RSA-2048 (primeira execução, alguns segundos)...")
    return _gerar_chave()
