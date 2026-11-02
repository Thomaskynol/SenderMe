#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SenderMe — pre-boot: recuperação de update interrompido (só stdlib).

Roda no start.sh ANTES de copiar o runtime p/ /tmp e ANTES de qualquer
`import senderme_app` (nunca importe senderme_app aqui: o conjunto em disco
pode estar misto após SIGKILL). Opera só sobre a pasta da instalação
(SENDERME_HOME = pasta do start.sh).

Contrato:
- sem .upd-pendente.json -> exit 0, nada a fazer.
- marcador + backups íntegros -> restaura tudo, remove marcador SOMENTE se
  nada faltar, remove backup só então, exit 0.
- faltando algo (backup ilegível/destino sem escrita) -> MANTÉM marcador e
  backup p/ nova tentativa, log acionável, exit 1 (o launcher não boota
  mistura; app.main tem a mesma guarda como fallback).
- falha ao remover o marcador -> mantém backup+marcador, exit 1.

`senderme_app/update.py:recuperar_update` delega para cá (fonte única da
lógica); aqui não há dependência do estado global.

Contenção symlink (item 3, alteração local): manifesto/paths de peers são
não-confiáveis; validar na borda. Nenhum restore/remove sai da pasta por
link (parent ou final, fail closed, mesmo apontando p/ dentro). A
contenção contra troca concorrente entre check e uso está nas operações
relativas a fds fixados (_abrir_pai/_substituir: openat/renameat
O_NOFOLLOW relativo ao diretório original). Em escape, conta como
faltando (mantém marcador+backup, sem tocar o externo). Sem suporte a
dir_fd/O_NOFOLLOW no SO, aborta com journal preservado (fail closed).
"""
import json
import os
import stat as _stat
import sys


def _dentro_base(base_real, caminho):
    try:
        real = os.path.realpath(caminho)
    except Exception:
        return False
    return real == base_real or real.startswith(base_real + os.sep)


def _cadeia_segura(pasta, dest):
    """Ver _cadeia_segura em update.py (duplicada aqui: preboot não pode
    importar senderme_app — disco pode estar misto). Papel: rejeição
    rápida de link pré-existente + detecção pós-operação; a contenção
    contra troca concorrente está nos fds fixados abaixo."""
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


def _fd_seguro_suportado():
    """dir_fd + O_NOFOLLOW + O_DIRECTORY (Linux). Sem isso, recuperação
    aborta com journal preservado (fail closed documentado)."""
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
    """rename com ambos os pais fixados (renameat relativo a fd):
    symlink trocado no meio não é resolvido."""
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


def nome_ok(nome):
    if not isinstance(nome, str) or not nome or len(nome) > 120:
        return False
    if nome.startswith("/") or "\\" in nome or "\r" in nome or "\n" in nome:
        return False
    partes = nome.split("/")
    if not partes or any(p in ("", ".", "..") for p in partes):
        return False
    return True


def _rm_arvore(raiz):
    """Remove sem seguir symlink (ver update._rm_arvore)."""
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
            try:
                os.unlink(os.path.join(base, n))
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


def _podar_pais_vazios_fd(root_fd, rel):
    """Remove dirs pais vazios até a base. rmdir relativo a fds fixados:
    não segue symlink (link falha ENOTDIR); para na 1ª falha."""
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


def _remover_novo_fd(pasta, root_fd, nome):
    """Remove destino de arquivo novo por pai fixado. Retorna True se o
    estado velho ("ausente") foi atingido; False se faltando."""
    if not _cadeia_segura(pasta, os.path.join(pasta, nome)):
        return False
    try:
        _remover_rel(root_fd, nome)
    except FileNotFoundError:
        pass  # já ausente = estado velho coerente
    except OSError:
        return False
    _podar_pais_vazios_fd(root_fd, nome)
    return True


def _recuperar_arquivos(pasta, root_fd, backup, arquivos, novos):
    """Restaura arquivos do backup (operações relativas a fds fixados).
    Retorna (restaurados, faltando). Escape vira faltando sem tocar o
    externo (fail closed)."""
    restaurados, faltando = 0, []
    for nome in arquivos:
        if not nome_ok(nome):
            continue
        orig = os.path.join(backup, nome)
        dest = os.path.join(pasta, nome)
        # Contenção (item 3, alteração local): qualquer link na cadeia ou
        # fora da base vira faltando sem tocar o externo (fail closed).
        if not _cadeia_segura(pasta, orig) \
                or not _cadeia_segura(pasta, dest):
            faltando.append(nome)
            continue
        try:
            _st_o = os.lstat(orig)
        except OSError:
            _st_o = None
        if _st_o is None or _stat.S_ISLNK(_st_o.st_mode) \
                or not _stat.S_ISREG(_st_o.st_mode):
            if nome in novos:
                # backup ausente p/ arquivo novo: o velho é "ausente".
                if _remover_novo_fd(pasta, root_fd, nome):
                    restaurados += 1
                else:
                    faltando.append(nome)
            else:
                faltando.append(nome)
            continue
        try:
            blob = _ler_rel(root_fd, ".upd-backup/" + nome)
            if not _cadeia_segura(pasta, dest) \
                    or not _cadeia_segura(pasta, dest + ".upd-tmp"):
                raise OSError("escape por symlink: %s" % nome)
            _escrever_rel(root_fd, nome + ".upd-tmp", blob)
            _substituir(root_fd, nome + ".upd-tmp", nome)
            if not _cadeia_segura(pasta, dest):
                raise OSError("escape por symlink: %s" % nome)
            restaurados += 1
        except OSError:
            if nome in novos:
                if _remover_novo_fd(pasta, root_fd, nome):
                    restaurados += 1
                else:
                    faltando.append(nome)
            else:
                faltando.append(nome)
    return restaurados, faltando


def _recuperar_manifesto(pasta, root_fd, backup, tinha_manifesto, faltando):
    """Volta do update-manifest.json. Leitura do backup por fd fixado;
    destino na raiz por caminho absoluto. Retorna nº de restaurados."""
    restaurados = 0
    bkp_manif = os.path.join(backup, "update-manifest.json")
    dest_manif = os.path.join(pasta, "update-manifest.json")
    if tinha_manifesto is True:
        if not _cadeia_segura(pasta, bkp_manif) \
                or not _cadeia_segura(pasta, dest_manif + ".upd-tmp") \
                or not _cadeia_segura(pasta, dest_manif):
            faltando.append("update-manifest.json")
        else:
            try:
                _st_bm = os.lstat(bkp_manif)
                if _stat.S_ISLNK(_st_bm.st_mode) \
                        or not _stat.S_ISREG(_st_bm.st_mode):
                    raise OSError("escape por symlink no manifesto")
                blob = _ler_rel(root_fd, ".upd-backup/update-manifest.json")
                # .upd-tmp por fd fixado (item 1, corrida local): openat
                # O_NOFOLLOW + renameat relativos; troca entre escrever e
                # publicar cai no pós-check (externo intacto, faltando).
                _escrever_rel(root_fd, "update-manifest.json.upd-tmp",
                              blob)
                _substituir(root_fd, "update-manifest.json.upd-tmp",
                            "update-manifest.json")
                if not _cadeia_segura(pasta, dest_manif):
                    raise OSError("escape por symlink no manifesto")
                restaurados += 1
            except OSError:
                faltando.append("update-manifest.json")
    elif tinha_manifesto is False:
        # O update criou o manifesto; a volta o remove. unlink em symlink
        # remove só o link (seguro); parent é a própria pasta (confiável).
        # Fail closed: se o destino final é link, mantém faltando p/ manual.
        if not _cadeia_segura(pasta, dest_manif):
            try:
                _st_dm = os.lstat(dest_manif)
            except FileNotFoundError:
                pass
            except OSError:
                faltando.append("update-manifest.json")
            else:
                try:
                    if _stat.S_ISLNK(_st_dm.st_mode):
                        faltando.append("update-manifest.json")
                    else:
                        try:
                            os.remove(dest_manif)
                        except FileNotFoundError:
                            pass
                        except OSError:
                            faltando.append("update-manifest.json")
                except OSError:
                    faltando.append("update-manifest.json")
        else:
            try:
                os.remove(dest_manif)  # o update o criou; some com a volta
            except FileNotFoundError:
                pass
            except OSError:
                faltando.append("update-manifest.json")
    else:
        try:
            _st_bm2 = os.lstat(bkp_manif)
        except OSError:
            _st_bm2 = None
        if _st_bm2 is not None and _cadeia_segura(pasta, bkp_manif) \
                and _cadeia_segura(pasta, dest_manif):
            try:
                if _stat.S_ISLNK(_st_bm2.st_mode) \
                        or not _stat.S_ISREG(_st_bm2.st_mode):
                    raise OSError("escape por symlink no manifesto")
                blob = _ler_rel(root_fd, ".upd-backup/update-manifest.json")
                # .upd-tmp por fd fixado (item 1, corrida local): openat
                # O_NOFOLLOW + renameat relativos; troca entre escrever e
                # publicar cai no pós-check (externo intacto, faltando).
                _escrever_rel(root_fd, "update-manifest.json.upd-tmp",
                              blob)
                _substituir(root_fd, "update-manifest.json.upd-tmp",
                            "update-manifest.json")
                if not _cadeia_segura(pasta, dest_manif):
                    raise OSError("escape por symlink no manifesto")
                restaurados += 1
            except OSError:
                faltando.append("update-manifest.json")
    return restaurados


def recuperar(pasta, log=None):
    """Tenta desfazer um update interrompido. Retorna True se havia marcador.

    O marcador só é removido com `faltando` vazio; backup só é removido
    depois do marcador. Em parcial, marcador+backup ficam p/ o próximo boot.
    """
    if log is None:
        def log(txt):
            print("[senderme] %s" % txt, flush=True)
    marcador = os.path.join(pasta, ".upd-pendente.json")
    try:
        _st_m = os.lstat(marcador)
    except FileNotFoundError:
        return False
    except OSError:
        return False
    # marcador que seja link não é lido (não segue p/ fora): mantém p/
    # intervenção manual em vez de interpretar JSON externo.
    try:
        if _stat.S_ISLNK(_st_m.st_mode):
            log("marcador é symlink (%s): mantendo p/ intervenção manual"
                % marcador)
            return True
    except OSError:
        return True
    if not _fd_seguro_suportado():
        log("plataforma sem dir_fd/O_NOFOLLOW: recuperação abortada "
            "(fail closed), journal preservado")
        return True
    try:
        root_fd = os.open(pasta, os.O_RDONLY | os.O_DIRECTORY)
    except OSError as e:
        log("não consegui fixar %s (%r): journal preservado" % (pasta, e))
        return True
    # Leitura por fd fixado (item 1, corrida local): link trocado entre o
    # lstat e a leitura vira ELOOP em vez de interpretar JSON externo.
    try:
        raw = _ler_rel(root_fd, ".upd-pendente.json")
    except FileNotFoundError:
        try:
            os.close(root_fd)
        except OSError:
            pass
        return False
    except OSError:
        try:
            os.close(root_fd)
        except OSError:
            pass
        log("marcador ilegível ou trocado por link (%s): mantendo p/ "
            "intervenção manual" % marcador)
        return True
    try:
        pend = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        try:
            os.close(root_fd)
        except OSError:
            pass
        # ilegível: não interpreta nem remove — preserva p/ intervenção
        # manual em vez de bootar com journal desconhecido no disco.
        log("marcador ilegível (%s): mantendo p/ intervenção manual"
            % marcador)
        return True
    if not isinstance(pend, dict) or not isinstance(pend.get("arquivos"), list):
        try:
            os.close(root_fd)
        except OSError:
            pass
        log("marcador inválido (%s): mantendo p/ intervenção manual"
            % marcador)
        return True
    backup = os.path.join(pasta, ".upd-backup")
    staging = os.path.join(pasta, ".upd-staging")
    novos = set(pend.get("novos") or [])
    tinha_manifesto = pend.get("tinha_manifesto")  # None = marcador antigo
    try:
        restaurados, faltando = _recuperar_arquivos(
            pasta, root_fd, backup, pend["arquivos"], novos)
        restaurados += _recuperar_manifesto(
            pasta, root_fd, backup, tinha_manifesto, faltando)
    finally:
        try:
            os.close(root_fd)
        except OSError:
            pass
    _rm_arvore(staging)
    if faltando:
        # R3: mantém marcador+backup p/ nova tentativa; nunca finge pronto.
        log("update interrompido: restaurei %d, FALTAM %s (backup em %s)"
            % (restaurados, faltando, backup))
        return True
    try:
        # unlink remove no máximo o link: se o marcador virou symlink na
        # janela final, não finge limpo — mantém backup+marcador p/ manual.
        if _stat.S_ISLNK(os.lstat(marcador).st_mode):
            log("marcador é symlink (%s): mantendo p/ intervenção manual"
                % marcador)
            return True
        os.remove(marcador)
    except OSError as e:
        # arquivos já voltaram, mas sem remover o marcador o próximo boot
        # tentaria de novo: mantém backup e pede nova tentativa, sem servir.
        log("recuperação pronta mas não consegui remover %s (%r): "
            "mantendo backup, tente de novo" % (marcador, e))
        return True
    _rm_arvore(backup)
    log("update interrompido: %d arquivos restaurados do backup" % restaurados)
    return True


def _marcador_restante(pasta):
    """lexists (não exists): symlink quebrado conta como pendente.

    exists retorna False para link quebrado e liberaria o boot sobre um
    marcador que recuperar() mandou preservar — fail closed exige lstat.
    Incerteza (OSError) também bloqueia: nunca servir mistura possível."""
    try:
        return os.path.lexists(os.path.join(pasta, ".upd-pendente.json"))
    except OSError:
        return True


def _anexar_preboot(pasta, teve, restante):
    """Uma linha JSON em logs/preboot.log quando o preboot agiu.

    Autônomo (stdlib, sem importar senderme_app): só campos seguros
    (bools; nunca caminhos/nomes). Teto 256 KiB com 1 backup; falha de
    log nunca quebra a recuperação (o resultado já foi p/ o terminal).
    Com SENDERME_SEM_LOG=1, nada é criado (item 2; só `os`, sem importar
    senderme_app p/ preservar a autonomia).
    """
    if os.environ.get("SENDERME_SEM_LOG"):
        return
    try:
        if not teve and not restante:
            return  # nada a fazer: sem linha (sem ruído por boot normal)
        d = os.path.join(pasta, "logs")
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            return
        p = os.path.join(d, "preboot.log")
        try:
            if os.path.isfile(p) and os.path.getsize(p) > 256 * 1024:
                try:
                    if os.path.isfile(p + ".1"):
                        os.remove(p + ".1")
                except OSError:
                    pass
                try:
                    os.replace(p, p + ".1")
                except OSError:
                    return
        except OSError:
            pass
        import time as _t
        linha = {"ts": int(_t.time()), "acao": "preboot",
                 "teve_marcador": bool(teve),
                 "recuperacao_restante": bool(restante)}
        try:
            with open(p, "a", encoding="utf-8") as f:
                f.write(json.dumps(linha, ensure_ascii=False) + "\n")
        except OSError:
            pass
    except Exception:
        pass


def main(argv):
    pasta = argv[1] if len(argv) > 1 else os.environ.get("SENDERME_HOME", ".")
    try:
        teve = recuperar(pasta)
    except Exception as e:  # falha inesperada: não bootar mistura
        print("[senderme] pre-boot: falha na recuperação (%r), "
              "não vou iniciar" % (e,), flush=True)
        return 1
    restante = _marcador_restante(pasta) if teve else False
    _anexar_preboot(pasta, teve, restante)
    if teve and restante:
        # parcial ou marcador preso (incl. symlink válido/quebrado e
        # conteúdo inválido): disco pode seguir misto, não servir.
        print("[senderme] pre-boot: recuperação pendente em %s "
              "(veja o log acima); não vou iniciar mistura" % pasta,
              flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
