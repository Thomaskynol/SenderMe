#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SenderMe — update: aplicação/recuperação + compat.

Protocolo/transferência mora em senderme_app/update_proto.py (1.11);
os helpers fd-pinned puros moram em senderme_app/update_store.py
(1.12, folha só-stdlib, re-exportados abaixo para compat). Aqui ficam
a validação/contenção (_cadeia_segura/_eh_escape/_rm_arvore, lidas
junto do apply pela revisão TOCTOU), baixar_update,
aplicação/recuperação e os re-exports (tcp.py, senderme.py e testes
importam daqui). preboot.py segue autônomo (duplicação proposital).
"""
import errno
import hashlib
import json
import os
import stat as _stat
import threading
import time
from . import estado as S
from . import diario as D
from .estado import agora, log, id_curto
from .preboot import recuperar as _preboot_recuperar
from .update_store import (
    _abrir_base, _abrir_pai, _escrever_rel, _escrever_tudo,
    _fd_seguro_suportado, _ler_rel, _partes, _podar_pais_vazios_fd,
    _remover_rel, _substituir)
from .update_proto import (
    _COOLDOWN_REOFERTA, _META_SOCK, _ULTIMA_TENTATIVA,
    _caminho_marcador, _ha_recuperacao_pendente,
    caminho_update_origem, conferir_manifest, empurrar_update,
    ler_manifest_local, manifest_canonico, nome_update_ok,
    receber_update_chunk, receber_update_meta, servir_update,
    tratar_ver, ver_tupla)
from .transporte import enviar
from config import CHUNK_ARQ

# Uma só aplicação/recuperação de update por vez (A): finalizar e recuperar
# disputam este lock; o 2º a chegar aborta (finalizar) ou espera (recuperar).
_APPLY_LCK = threading.Lock()


def _base_real():
    try:
        return os.path.realpath(S.PASTA)
    except Exception:
        return S.PASTA


def _dentro_base(base_real, caminho):
    try:
        real = os.path.realpath(caminho)
    except Exception:
        return False
    return real == base_real or real.startswith(base_real + os.sep)


def _cadeia_segura(pasta, dest):
    """Contenção anti-symlink (fail closed, item 3).

    True só se dest está sob pasta, nenhum componente de pasta->dest
    (incl. final) é symlink, intermediários existentes são dirs reais e
    realpath(dest) segue dentro da base. Final inexistente é ok (será
    criado) se os pais são seguros e o realpath segue dentro. Rejeita
    symlink mesmo apontando p/ dentro.
    Papel atual: rejeição rápida de link pré-existente + detecção
    pós-operação. A contenção real contra troca concorrente entre check e
    uso está nas operações relativas a fds fixados (_abrir_pai/_substituir:
    renameat/openat O_NOFOLLOW relativo ao diretório original, que não
    resolve symlink trocado no meio). Exige alteração local concorrente
    nos diretórios da instalação; não há vetor remoto aqui.
    """
    try:
        if not isinstance(dest, str) or not isinstance(pasta, str):
            return False
        if not (dest == pasta or dest.startswith(pasta + os.sep)):
            return False
        base_real = os.path.realpath(pasta)
        try:
            real = os.path.realpath(dest)
        except Exception:
            return False
        if not (real == base_real or real.startswith(base_real + os.sep)):
            return False
        rel = os.path.relpath(dest, pasta)
        if rel in (".", ""):
            return True
        cur = pasta
        partes = rel.split(os.sep)
        for i, parte in enumerate(partes):
            if parte in ("", ".", ".."):
                return False
            cur = os.path.join(cur, parte)
            ultimo = (i == len(partes) - 1)
            try:
                st = os.lstat(cur)
            except FileNotFoundError:
                continue
            except OSError:
                return False
            if _stat.S_ISLNK(st.st_mode):
                return False
            if ultimo:
                if _stat.S_ISDIR(st.st_mode):
                    return False
                if not _stat.S_ISREG(st.st_mode):
                    return False
            else:
                if not _stat.S_ISDIR(st.st_mode):
                    return False
        return True
    except Exception:
        return False


def _eh_escape(e):
    """OSError de contenção symlink = alteração local concorrente suspeita.

    ELOOP (O_NOFOLLOW barrou um link) ou mensagem de "symlink" gerada
    pelos checks de cadeia. Nesse caso a reversão total de efeito externo
    nunca é afirmada: o journal fica para o boot. Erro comum (disco
    cheio, ENOENT) não cai aqui."""
    try:
        if isinstance(e, OSError) and e.errno == errno.ELOOP:
            return True
    except Exception:
        pass
    try:
        return isinstance(e, OSError) and "symlink" in str(e).lower()
    except Exception:
        return False


def baixar_update():
    with S.L:
        manifest = dict(S.update_manifest or {})
    arqs = manifest.get("arquivos", []) if isinstance(manifest, dict) else []
    for a in arqs:
        try:
            nome = str(a["nome"])
            total = (int(a["tamanho"]) + CHUNK_ARQ - 1) // CHUNK_ARQ or 1
        except Exception:
            continue
        # até 3 rodadas: chunks perdidos numa rodada são repedidos na
        # seguinte (queda temporária não aborta de primeira). Após
        # reconexão, servir_update responde a qualquer update_get — o
        # download retoma sem depender de nova oferta.
        for _ in range(3):
            with S.L:
                if not S.atualizando:
                    return
                slot = S.update_montando.get(nome)
                falt = [i for i in range(total)
                        if not (slot and i in slot.get("partes", {}))]
                if not falt:
                    break
                alvos = []
                for cs in S.conns.values():
                    alvos.extend(cs)
            for idx in falt:
                with S.L:
                    if not S.atualizando:
                        return
                ok = False
                for c in alvos[:4]:
                    try:
                        enviar(c, {"t": "update_get", "nome": nome, "idx": idx})
                        ok = True
                        break
                    except Exception:
                        pass
                if not ok:
                    time.sleep(1.0)
            # espera os chunks desta rodada (até 20 s por rodada)
            for _ in range(200):
                with S.L:
                    if not S.atualizando:
                        return
                    slot = S.update_montando.get(nome)
                    if slot and len(slot.get("partes", {})) >= slot.get("total", 1):
                        break
                time.sleep(0.1)
            else:
                continue
            break
        if os.environ.get("SENDERME_DEBUG"):
            with S.L:
                slot = S.update_montando.get(nome)
                got = len(slot.get("partes", {})) if slot else 0
            if got < total:
                log("update %s incompleto (%s/%s), segue" % (nome, got, total))
    if finalizar_update():
        time.sleep(0.5)
        os._exit(42)  # contrato com start.sh: 42 = update aplicado, reinicia


def _update_abortar(motivo):
    """Libera a flag e limpa montagem para permitir nova tentativa."""
    log("update abortado: %s" % motivo)
    # arquivo: só o evento (o motivo pode conter caminhos — fica no terminal).
    D.registrar("update_abortado")
    with S.L:
        S.atualizando = False
        S.update_montando.clear()


def _rm_arvore(raiz):
    """Remove árvore sem seguir symlink (item 3).

    Raiz que seja link/arquivo é unlink (não walk no alvo externo).
    Subdirs que sejam links são unlink (não rmdir, que falharia e deixaria).
    Caso normal (dirs reais) comporta-se como antes."""
    try:
        st = os.lstat(raiz)
    except OSError:
        return
    if _stat.S_ISLNK(st.st_mode) or not _stat.S_ISDIR(st.st_mode):
        try:
            os.unlink(raiz)
        except OSError:
            pass
        return
    for base, dirs, arqs in os.walk(raiz, topdown=False, followlinks=False):
        for n in arqs:
            p = os.path.join(base, n)
            try:
                os.unlink(p)
            except OSError:
                pass
        for n in dirs:
            p = os.path.join(base, n)
            try:
                if os.path.islink(p):
                    os.unlink(p)
                else:
                    os.rmdir(p)
            except OSError:
                pass
    try:
        os.rmdir(raiz)
    except OSError:
        pass


def recuperar_update():
    """Recuperação no boot (fallback; o start.sh já fez o pre-boot).

    Delega à fonte única em senderme_app/preboot.py (sem estado global).
    O marcador só sai com `faltando` vazio; em parcial, marcador+backup
    ficam para nova tentativa e app.main() não serve mistura (ver app.py).
    Serializada com finalizar_update via _APPLY_LCK (A).
    Retorna True se havia algo a recuperar."""
    with _APPLY_LCK:
        return bool(_preboot_recuperar(S.PASTA, log))


def finalizar_update():
    """Verifica tudo antes de gravar e aplica o pacote com staging+backup.

    Retorna True se aplicou (o chamador reinicia com exit 42) ou False se
    abortou. Em qualquer aborto a flag é liberada e arquivos já trocados são
    revertidos do backup — nunca deixa pacote meio novo/meio velho.
    Arquivos que saíram do conjunto assinado (ex. README/docs de releases
    antigas) ficam intocados no disco: o update só escreve o que está no
    manifesto novo e nunca apaga arquivos de usuário.
    Só uma aplicação por vez (A): se outra estiver em curso, aborta sem
    tocar no disco. Com recuperação pendente de tentativa anterior (B),
    aborta preservando marcador+backup para o boot recuperar."""
    if not _APPLY_LCK.acquire(blocking=False):
        log("update abortado: outra aplicação em curso")
        return False
    try:
        return _finalizar_update_protegido()
    finally:
        _APPLY_LCK.release()


def _finalizar_update_protegido():
    with S.L:
        manifest = S.update_manifest
        envelope = S.update_envelope
        mont = {k: {"total": v.get("total"),
                    "partes": dict(v.get("partes", {}))}
                for k, v in S.update_montando.items()}
    if not isinstance(manifest, dict):
        _update_abortar("sem manifesto")
        return False
    blobs = {}
    for a in manifest.get("arquivos", []):
        try:
            nome = str(a["nome"])
            slot = mont.get(nome)
            total = (int(a["tamanho"]) + CHUNK_ARQ - 1) // CHUNK_ARQ or 1
            if not slot or len(slot.get("partes", {})) < total:
                _update_abortar("incompleto (%s)" % nome)
                return False
            blob = b"".join(slot["partes"][i] for i in range(total))
            if len(blob) != int(a["tamanho"]):
                raise ValueError("tamanho")
            if hashlib.sha256(blob).hexdigest() != a["sha256"]:
                raise ValueError("hash")
            if not nome_update_ok(nome):
                raise ValueError("nome")
            blobs[nome] = blob
        except Exception:
            _update_abortar("corrompido (%s)" % (a,))
            return False
    staging = os.path.join(S.PASTA, ".upd-staging")
    backup = os.path.join(S.PASTA, ".upd-backup")
    marcador = _caminho_marcador()
    if _ha_recuperacao_pendente():
        # (B) journal anterior intacto: não apagar backup+marcador com uma
        # nova tentativa — o boot recupera primeiro, depois aceita oferta.
        _update_abortar("recuperação pendente em %s: nova tentativa "
                        "bloqueada" % marcador)
        return False
    if not isinstance(envelope, dict) or envelope.get("manifest") != manifest \
            or not isinstance(envelope.get("sig"), str):
        _update_abortar("sem envelope assinado para persistir")
        return False
    # Contenção symlink (item 3, ataque local): rejeita antes de tocar o
    # disco se algum destino escapa da base por link pré-existente (parent
    # ou final). Revalidações por arquivo no uso + pós-replace (abaixo)
    # cobrem troca posterior na janela TOCTOU (ver _cadeia_segura).
    for _nome in blobs:
        if not _cadeia_segura(S.PASTA, os.path.join(S.PASTA, _nome)):
            _update_abortar("caminho escapa por symlink (%s)" % _nome)
            return False
    if not _fd_seguro_suportado():
        # Fail closed documentado: sem dir_fd/O_NOFOLLOW (fora do Linux),
        # aborta sem tocar o disco em vez de prometer contenção anti-TOCTOU.
        _update_abortar("plataforma sem dir_fd/O_NOFOLLOW: update abortado "
                        "(fail closed)")
        return False
    novos = []  # arquivos que não existiam antes (para remover no rollback)
    bkp_ok = set()  # backups concluídos (tmp+replace); só estes restauram
    tinha_manifesto = False
    marcador_gravado = False
    root_fd = None
    try:
        # Base fixada por fd: todas as operações abaixo de S.PASTA são
        # relativas a descritores (openat/mkdirat/renameat O_NOFOLLOW).
        # Symlink trocado no meio do caminho não é resolvido — o conteúdo
        # cai no diretório original fixado e o pós-check denuncia a troca.
        # Arquivos na raiz (marcador/manifesto) não têm intermediário
        # abaixo da base e seguem por caminho absoluto.
        root_fd = _abrir_base(S.PASTA)
        try:
            _rm_arvore(staging)
            for nome, blob in blobs.items():
                p = os.path.join(staging, nome)
                if not _cadeia_segura(S.PASTA, p):
                    raise OSError("escape por symlink no staging: %s" % nome)
                _escrever_rel(root_fd, ".upd-staging/" + nome, blob)
                if not _cadeia_segura(S.PASTA, p):
                    raise OSError("escape por symlink no staging: %s" % nome)
            # backup do que existe hoje + marcador de aplicação (p/recuperação).
            # Cada backup é tmp+replace atômico: falha no meio da escrita deixa
            # só o .tmp (descartado), nunca backup parcial truncado — e a volta
            # restaura apenas backups concluídos (bkp_ok).
            _rm_arvore(backup)
            for nome in blobs:
                dest = os.path.join(S.PASTA, nome)
                if not _cadeia_segura(S.PASTA, dest):
                    raise OSError("escape por symlink: %s" % nome)
                try:
                    _st = os.lstat(dest)
                except FileNotFoundError:
                    novos.append(nome)
                    continue
                except OSError:
                    raise
                if _stat.S_ISLNK(_st.st_mode) \
                        or not _stat.S_ISREG(_st.st_mode):
                    raise OSError("escape por symlink: %s" % nome)
                bkp = os.path.join(backup, nome)
                if not _cadeia_segura(S.PASTA, bkp + ".tmp"):
                    raise OSError("escape por symlink no backup: %s" % nome)
                dado = _ler_rel(root_fd, nome)
                _escrever_rel(root_fd, ".upd-backup/" + nome + ".tmp", dado)
                if not _cadeia_segura(S.PASTA, bkp):
                    raise OSError("escape por symlink no backup: %s" % nome)
                _substituir(root_fd, ".upd-backup/" + nome + ".tmp",
                            ".upd-backup/" + nome)
                if not _cadeia_segura(S.PASTA, bkp):
                    raise OSError("escape por symlink no backup: %s" % nome)
                bkp_ok.add(nome)
            man_antigo = os.path.join(S.PASTA, "update-manifest.json")
            try:
                _st_man = os.lstat(man_antigo)
            except FileNotFoundError:
                _st_man = None
            except OSError:
                raise
            if _st_man is not None:
                if _stat.S_ISLNK(_st_man.st_mode) \
                        or not _stat.S_ISREG(_st_man.st_mode):
                    raise OSError("escape por symlink: update-manifest.json")
                if not _cadeia_segura(S.PASTA, man_antigo):
                    raise OSError("escape por symlink: update-manifest.json")
                dado = _ler_rel(root_fd, "update-manifest.json")
                bkp_manif = os.path.join(backup, "update-manifest.json")
                if not _cadeia_segura(S.PASTA, bkp_manif + ".tmp"):
                    raise OSError("escape por symlink no backup do manifesto")
                _escrever_rel(root_fd,
                              ".upd-backup/update-manifest.json.tmp", dado)
                if not _cadeia_segura(S.PASTA, bkp_manif):
                    raise OSError("escape por symlink no backup do manifesto")
                _substituir(root_fd,
                            ".upd-backup/update-manifest.json.tmp",
                            ".upd-backup/update-manifest.json")
                tinha_manifesto = True
            if not _cadeia_segura(S.PASTA, marcador + ".tmp") \
                    or not _cadeia_segura(S.PASTA, marcador):
                raise OSError("escape por symlink no marcador")
            # Marcador por fd fixado (item 1, corrida local no .tmp): o
            # conteúdo sai por openat O_NOFOLLOW relativo ao pai fixado
            # (link no final = ELOOP, fail closed) e a publicação por
            # renameat relativo; builtins.open/os.replace absolutos aqui
            # seguiam symlink trocado entre check e uso. Bytes idênticos
            # ao json.dump anterior (mesma leitura no boot).
            marcador_blob = json.dumps({"v": manifest.get("v"),
                                        "arquivos": sorted(blobs),
                                        "novos": sorted(novos),
                                        "tinha_manifesto": tinha_manifesto}
                                       ).encode("utf-8")
            _escrever_rel(root_fd, ".upd-pendente.json.tmp", marcador_blob)
            _substituir(root_fd, ".upd-pendente.json.tmp",
                        ".upd-pendente.json")
            marcador_gravado = True
            if not _cadeia_segura(S.PASTA, marcador):
                # .tmp trocado por link entre escrever e publicar: o
                # rename moveu o link, não o conteúdo — externo intacto,
                # mas o journal não é confiável (journal fica p/ o boot).
                raise OSError("escape por symlink no marcador")
            # troca: staged -> destino com pais fixados por fd (release pode
            # ter subdir nova: o pai é criado via mkdirat relativo ao fd).
            for nome in blobs:
                dest = os.path.join(S.PASTA, nome)
                _substituir(root_fd, ".upd-staging/" + nome, nome)
                if not _cadeia_segura(S.PASTA, dest):
                    raise OSError("escape por symlink na troca: %s" % nome)
            # persiste o envelope assinado (propagação A->B->C depende dele).
            # Mesma proteção do marcador (item 1, corrida local no .tmp):
            # openat O_NOFOLLOW + renameat relativos ao fd fixado; o
            # pós-check denuncia troca do .tmp entre escrever e publicar.
            _man_tmp = os.path.join(S.PASTA, "update-manifest.json.tmp")
            _man_dst = os.path.join(S.PASTA, "update-manifest.json")
            if not _cadeia_segura(S.PASTA, _man_tmp) \
                    or not _cadeia_segura(S.PASTA, _man_dst):
                raise OSError("escape por symlink no manifesto")
            _escrever_rel(root_fd, "update-manifest.json.tmp",
                          json.dumps(envelope,
                                     ensure_ascii=False).encode("utf-8"))
            _substituir(root_fd, "update-manifest.json.tmp",
                        "update-manifest.json")
            if not _cadeia_segura(S.PASTA, _man_dst):
                raise OSError("escape por symlink no manifesto")
        except Exception as e:
            escape = _eh_escape(e)
            if escape:
                log("troca concorrente de caminho detectada (alteração "
                    "local simultânea) ao gravar update (%r): gravação "
                    "abortada; reversão total não garantida, journal "
                    "preservado para o boot" % (e,))
            else:
                log("falha ao gravar update (%r): revertendo" % (e,))
            revert_ok = True
            for nome in blobs:
                try:
                    bkp = os.path.join(backup, nome)
                    dest = os.path.join(S.PASTA, nome)
                    # só backup concluído restaura: parcial (.tmp que não
                    # virou bkp) é descartado, destino íntegro não é tocado.
                    # Contenção (item 3, alteração local): nunca
                    # restaurar/remover por caminho com symlink — falha
                    # fechada p/ boot tentar de novo.
                    if nome in bkp_ok:
                        if not _cadeia_segura(
                                S.PASTA,
                                os.path.join(S.PASTA,
                                             ".upd-backup/" + nome)) \
                                or not _cadeia_segura(
                                    S.PASTA, dest + ".upd-tmp") \
                                or not _cadeia_segura(S.PASTA, dest):
                            raise OSError("escape por symlink no rollback: "
                                          "%s" % nome)
                        try:
                            _st_b = os.lstat(bkp)
                        except OSError:
                            raise
                        if _stat.S_ISLNK(_st_b.st_mode) \
                                or not _stat.S_ISREG(_st_b.st_mode):
                            raise OSError("escape por symlink no rollback: "
                                          "%s" % nome)
                        dado = _ler_rel(root_fd, ".upd-backup/" + nome)
                        _escrever_rel(root_fd, nome + ".upd-tmp", dado)
                        _substituir(root_fd, nome + ".upd-tmp", nome)
                        if not _cadeia_segura(S.PASTA, dest):
                            raise OSError("escape por symlink no rollback: "
                                          "%s" % nome)
                    elif nome in novos:
                        # remoção por pai fixado: se o caminho escapa
                        # (parent symlink), falha fechada sem tocar o
                        # externo — marca parcial p/ o boot (que recusa).
                        if not _cadeia_segura(S.PASTA, dest):
                            raise OSError("escape por symlink no rollback: "
                                          "%s" % nome)
                        try:
                            _remover_rel(root_fd, nome)
                        except FileNotFoundError:
                            pass
                        else:
                            _podar_pais_vazios_fd(root_fd, nome)
                except Exception as e2:
                    escape = escape or _eh_escape(e2)
                    revert_ok = False
            # Resto .tmp sai por unlink relativo ao fd fixado (nunca segue
            # link final); sem fd (falha antes de fixar a base), o unlink
            # absoluto remove no máximo o link, nunca o alvo externo.
            try:
                if root_fd is not None:
                    try:
                        _remover_rel(root_fd, "update-manifest.json.tmp")
                    except FileNotFoundError:
                        pass
                else:
                    os.remove(os.path.join(S.PASTA,
                                           "update-manifest.json.tmp"))
            except OSError:
                pass
            if not marcador_gravado:
                # Nada aplicado ainda (falha no staging/backup): sem
                # journal no boot — limpa restos como antes.
                _rm_arvore(staging)
                _rm_arvore(backup)
                if escape:
                    _update_abortar("gravação abortada por troca "
                                    "concorrente de caminho (alteração "
                                    "local simultânea), sem resto aplicado")
                else:
                    _update_abortar("falha de gravação revertida")
                return False
            if escape:
                # Journal fica p/ o boot mesmo com volta local completa:
                # efeito externo não é afirmável nem descartável aqui.
                _rm_arvore(staging)
                _update_abortar("gravação abortada por troca concorrente "
                                "de caminho (alteração local simultânea): "
                                "journal preservado para o boot, reversão "
                                "total não garantida")
                return False
            if revert_ok:
                # volta completa ao velho: o marcador só sai se removível;
                # se ele prender, mantém backup+marcador p/ o boot tentar
                # de novo (R3) em vez de fingir limpo sem resto.
                _rm_arvore(staging)
                marcador_ok = True
                for _rel in (".upd-pendente.json",
                             ".upd-pendente.json.tmp"):
                    try:
                        if root_fd is not None:
                            _remover_rel(root_fd, _rel)
                        else:
                            os.remove(os.path.join(S.PASTA, _rel))
                    except FileNotFoundError:
                        pass
                    except OSError:
                        marcador_ok = False
                if marcador_ok:
                    _rm_arvore(backup)
                else:
                    log("revertido ao velho mas não consegui remover %s: "
                        "mantendo backup p/ nova tentativa" % marcador)
            else:
                # volta parcial: mantém backup+marcador p/ recuperar no
                # boot; nunca afirma reversão total.
                _rm_arvore(staging)
                _update_abortar("falha de gravação com reversão parcial: "
                                "journal preservado para o boot")
                return False
            _update_abortar("falha de gravação revertida")
            return False
    finally:
        if root_fd is not None:
            try:
                os.close(root_fd)
            except OSError:
                pass
    # sucesso: marcador sai PRIMEIRO — kill daqui em diante encontra estado
    # novo coerente sem marcador (nada a desfazer); kill antes encontra
    # marcador+backup intactos (volta ao velho coerente). Ordem inversa
    # (backup antes do marcador) deixava janela mista sem backup p/ voltar.
    # R3: se o marcador não sair, NÃO apaga o backup nem finge sucesso —
    # volta False p/ não reiniciar sobre marcador preso (o próximo boot
    # desfaz p/ o velho coerente e o peer reenvia o update).
    try:
        os.remove(marcador)
    except FileNotFoundError:
        pass
    except OSError as e:
        log("update gravado mas não consegui remover %s (%r): sem reiniciar"
            % (marcador, e))
        with S.L:
            S.atualizando = False
            S.update_montando.clear()
        return False
    _rm_arvore(staging)
    _rm_arvore(backup)
    with S.L:
        S.atualizando = False
        S.update_montando.clear()
    log("update %s aplicado, reiniciando..." % manifest.get("v"))
    D.registrar("update_aplicado", versao=str(manifest.get("v"))[:16])
    return True
