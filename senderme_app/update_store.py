#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SenderMe — update_store: helpers fd-pinned puros (folha só-stdlib).

Extraído de senderme_app/update.py (1.12, Desenho A, sem mudar lógica):
só operações relativas a descritores fixados (openat/mkdirat/renameat
O_NOFOLLOW), sem nenhum estado global — tudo entra por parâmetro
(pasta/root_fd). Não importa senderme_app (folha); update.py importa
daqui e re-exporta (tcp.py/senderme.py/testes seguem via update).

Co-localização lógica: a validação/contenção (_cadeia_segura,
_fd_seguro_suportado é re-exportado daqui, _eh_escape, _rm_arvore) e o
apply/rollback seguem em update.py, onde a revisão TOCTOU os lê junto
do uso. preboot.py segue 100% autônomo (script direto, duplicação
proposital mantida — nunca importe este módulo lá: o disco pode estar
misto após SIGKILL).
"""
import os


def _fd_seguro_suportado():
    """dir_fd + O_NOFOLLOW + O_DIRECTORY (Linux): base do anti-TOCTOU.

    Sem isso, operações relativas a descritores não são possíveis e o
    update aborta sem tocar o disco (fail closed documentado). Vale no
    Linux em qualquer FS (ext4, FAT32, NTFS, exFAT)."""
    try:
        if getattr(os, "O_NOFOLLOW", None) is None:
            return False
        if getattr(os, "O_DIRECTORY", None) is None:
            return False
        for _fn in (os.open, os.mkdir, os.unlink, os.rmdir):
            if _fn not in os.supports_dir_fd:
                return False
        # os.replace aceita src/dst_dir_fd mas o CPython registra o
        # suporte em os.rename (mesma renameat): vale qualquer um.
        if os.replace not in os.supports_dir_fd \
                and os.rename not in os.supports_dir_fd:
            return False
        return True
    except Exception:
        return False


def _partes(rel):
    """Componentes de um caminho relativo à base (nomes já validados)."""
    try:
        partes = rel.split("/")
    except Exception:
        raise OSError("nome inválido (%r)" % (rel,))
    if not partes or any(p in ("", ".", "..") for p in partes):
        raise OSError("nome inválido (%r)" % (rel,))
    return partes


def _abrir_base(pasta):
    """fd fixado da base (O_RDONLY|O_DIRECTORY). Sem suporte: OSError."""
    if not _fd_seguro_suportado():
        raise OSError("plataforma sem dir_fd/O_NOFOLLOW: update abortado "
                      "(fail closed)")
    return os.open(pasta, os.O_RDONLY | os.O_DIRECTORY)


def _abrir_pai(root_fd, partes, criar=True):
    """Pai fixado por fd, sem seguir symlinks (openat O_NOFOLLOW por
    componente). Cria ausentes via mkdirat relativo (EEXIST vira
    reabertura; link no lugar = ELOOP, fail closed). Chamador fecha."""
    cur = os.dup(root_fd)
    try:
        for parte in partes:
            try:
                nxt = os.open(parte, os.O_RDONLY | os.O_DIRECTORY
                              | os.O_NOFOLLOW, dir_fd=cur)
            except FileNotFoundError:
                if not criar:
                    raise
                try:
                    os.mkdir(parte, 0o777, dir_fd=cur)
                except FileExistsError:
                    pass  # corrida benigna: reabre abaixo
                nxt = os.open(parte, os.O_RDONLY | os.O_DIRECTORY
                              | os.O_NOFOLLOW, dir_fd=cur)
            os.close(cur)
            cur = nxt
        return cur
    except Exception:
        try:
            os.close(cur)
        except OSError:
            pass
        raise


def _escrever_tudo(fd, dados):
    """Loop os.write até o fim (write parcial não é erro)."""
    vista = memoryview(dados)
    while vista:
        n = os.write(fd, vista)
        vista = vista[n:]


def _ler_rel(root_fd, rel):
    """Lê arquivo relativo à base fixada, sem seguir symlink (O_NOFOLLOW)."""
    partes = _partes(rel)
    pai = _abrir_pai(root_fd, partes[:-1], criar=False)
    try:
        fd = os.open(partes[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=pai)
    except Exception:
        try:
            os.close(pai)
        except OSError:
            pass
        raise
    try:
        blocos = []
        while True:
            b = os.read(fd, 65536)
            if not b:
                break
            blocos.append(b)
        return b"".join(blocos)
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.close(pai)
        except OSError:
            pass


def _escrever_rel(root_fd, rel, dados):
    """Escreve relativo à base fixada (pais via mkdirat; final com
    O_NOFOLLOW|O_CREAT: link no final = ELOOP, fail closed)."""
    partes = _partes(rel)
    pai = _abrir_pai(root_fd, partes[:-1], criar=True)
    try:
        fd = os.open(partes[-1], os.O_WRONLY | os.O_CREAT | os.O_TRUNC
                     | os.O_NOFOLLOW, 0o666, dir_fd=pai)
    except Exception:
        try:
            os.close(pai)
        except OSError:
            pass
        raise
    try:
        _escrever_tudo(fd, dados)
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.close(pai)
        except OSError:
            pass


def _substituir(root_fd, src_rel, dst_rel):
    """rename staged->dest com AMBOS os pais fixados (renameat relativo a
    fd). Symlink trocado no meio do caminho não é resolvido: o conteúdo
    cai no diretório original fixado, e o pós-check de cadeia denuncia a
    troca (erro detectado, externo intacto)."""
    src = _partes(src_rel)
    dst = _partes(dst_rel)
    fsrc = _abrir_pai(root_fd, src[:-1], criar=False)
    try:
        fdst = _abrir_pai(root_fd, dst[:-1], criar=True)
    except Exception:
        try:
            os.close(fsrc)
        except OSError:
            pass
        raise
    try:
        os.replace(src[-1], dst[-1], src_dir_fd=fsrc, dst_dir_fd=fdst)
    finally:
        try:
            os.close(fsrc)
        except OSError:
            pass
        try:
            os.close(fdst)
        except OSError:
            pass


def _remover_rel(root_fd, rel):
    """unlink relativo ao pai fixado (nunca segue link final)."""
    partes = _partes(rel)
    pai = _abrir_pai(root_fd, partes[:-1], criar=False)
    try:
        os.unlink(partes[-1], dir_fd=pai)
    finally:
        try:
            os.close(pai)
        except OSError:
            pass


def _podar_pais_vazios_fd(root_fd, rel):
    """Remove dirs pais vazios até a base (rollback de arquivo novo em
    subdir não deixa pasta vazia para trás). rmdir relativo a fds
    fixados: não segue symlink (link falha ENOTDIR); para na 1ª falha."""
    partes = _partes(rel)[:-1]
    for i in range(len(partes), 0, -1):
        avo = partes[:i - 1]
        try:
            if avo:
                gfd = _abrir_pai(root_fd, avo, criar=False)
            else:
                gfd = os.dup(root_fd)
        except OSError:
            break
        try:
            os.rmdir(partes[i - 1], dir_fd=gfd)
        except OSError:
            try:
                os.close(gfd)
            except OSError:
                pass
            break
        try:
            os.close(gfd)
        except OSError:
            pass
