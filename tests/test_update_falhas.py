"""Falhas e recuperação do updater (Lane U, item 3).

Escopo honesto: tudo aqui roda em diretórios temporários com chave de
assinatura SINTÉTICA (gerada no teste, nunca dono/privada.json) e identidades
sintéticas. "Matar o processo" é simulado com KeyboardInterrupt (BaseException,
não capturada pelo `except Exception` do finalizar_update) no ponto exato da
gravação — o teste então zera o estado em memória (como um processo novo) e
chama recuperar_update(), que é o que app.main() faz no boot. Interrupção real
com SIGKILL entre processos + restart exit 42 é demonstrada no teste A→B→C
(test_update_e2e_abc.py); aqui o foco são os pontos de interrupção e o estado
após cada um.

Mecanismo de fixture da chave: a chave pública é embutida em
senderme_app/meta.py (CHAVE_DONO_N/E, lida por dono/assinar_update.py e usada
por conferir_manifest via senderme_app.estado). Nos testes, a chave sintética é
instalada com mock.patch em senderme_app.estado — ou seja, estes testes NÃO
são releases históricas, são fixtures documentadas.
"""
import hashlib
import json
import os
import unittest
from unittest import mock

import senderme as sm
from suporte import CasoIsolado, definir_eu, chave_teste


def instalar_chave_sintetica(tc):
    chave = chave_teste()
    n_hex = format(chave["n"], "x")
    p = mock.patch.multiple("senderme_app.estado", CHAVE_DONO_N=n_hex,
                            CHAVE_DONO_E=65537)
    p.start()
    tc.addCleanup(p.stop)
    return chave


def assinar_release(chave, versao, arquivos):
    manifest = {"v": versao, "arquivos": [
        {"nome": n, "tamanho": len(b),
         "sha256": hashlib.sha256(b).hexdigest()}
        for n, b in sorted(arquivos.items())]}
    sig = sm.assinar(sm.manifest_canonico(manifest), chave).hex()
    return {"manifest": manifest, "sig": sig}, manifest


def montar_no_estado(arquivos):
    for nome, blob in arquivos.items():
        sm.update_montando[nome] = {"total": 1, "partes": {0: blob},
                                    "ts": sm.agora()}


def gravar(pasta, nome, blob):
    p = os.path.join(pasta, nome)
    os.makedirs(os.path.dirname(p) or pasta, exist_ok=True)
    with open(p, "wb") as f:
        f.write(blob)


def ler(pasta, nome):
    with open(os.path.join(pasta, nome), "rb") as f:
        return f.read()


def preparar_update(novos, versao="99.0", chave=None):
    """Deixa estado pronto p/ finalizar_update; retorna (env, manif)."""
    assert chave is not None
    env, manif = assinar_release(chave, versao, novos)
    sm.update_manifest = manif
    sm.update_envelope = env
    sm.atualizando = True
    sm.update_montando.clear()
    montar_no_estado(novos)
    return env, manif


def reiniciar_como_boot():
    """Simula processo novo: memória zerada, arquivos no disco mantidos."""
    sm.atualizando = False
    sm.update_manifest = None
    sm.update_envelope = None
    sm.update_montando.clear()
    return sm.recuperar_update()


def manifest_no_disco(pasta):
    try:
        with open(os.path.join(pasta, "update-manifest.json"),
                  encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _via_fd(dir_fd, nome):
    """Caminho aproximado p/ filtros de mock (somente Linux): resolve o
    fd do diretório via /proc; sem dir_fd, devolve o nome como veio.
    As trocas staged->destino e tmp+replace do updater usam nomes de um
    componente relativos a fds fixados (anti-TOCTOU); o filtro original
    por caminho absoluto é reconstruído aqui sem mudar o ponto de falha."""
    try:
        base = os.readlink("/proc/self/fd/%d" % (dir_fd,))
    except (OSError, TypeError):
        return os.fspath(nome)
    return base + "/" + os.fspath(nome)


def confere_coerencia(pasta, envelope):
    """Manifesto assinado corresponde aos arquivos no disco."""
    assert sm.conferir_manifest(envelope["manifest"], envelope["sig"])
    for a in envelope["manifest"]["arquivos"]:
        assert ler(pasta, a["nome"]) is not None
        assert (hashlib.sha256(ler(pasta, a["nome"])).hexdigest()
                == a["sha256"]), a["nome"]


class MorteAntesDaGravacao(CasoIsolado):
    def test_sem_marcador_boot_nao_faz_nada_e_arquivos_intactos(self):
        definir_eu("alice")
        gravar(self._tmp.name, "senderme.py", b"velho-1")
        gravar(self._tmp.name, "dados/identidade.json", b"ID-TESTE")
        self.assertFalse(reiniciar_como_boot())
        self.assertEqual(ler(self._tmp.name, "senderme.py"), b"velho-1")
        self.assertEqual(ler(self._tmp.name, "dados/identidade.json"),
                         b"ID-TESTE")
        self.assertFalse(sm.atualizando)

    def test_morte_durante_download_sem_marcador(self):
        """Kill antes do finalizar: nada foi gravado, boot é limpo."""
        definir_eu("alice")
        chave = instalar_chave_sintetica(self)
        env, _ = assinar_release(chave, "99.0", {"senderme.py": b"novo-1"})
        with mock.patch("senderme_app.update.baixar_update", lambda: None):
            sm.receber_update_meta(env)
        self.assertTrue(sm.atualizando)
        gravar(self._tmp.name, "senderme.py", b"velho-1")
        # "morte": processo some, outro assume com memória zerada
        self.assertFalse(reiniciar_como_boot())
        self.assertEqual(ler(self._tmp.name, "senderme.py"), b"velho-1")
        self.assertFalse(os.path.exists(
            os.path.join(self._tmp.name, ".upd-pendente.json")))


class MorteNoMeioDaAplicacao(CasoIsolado):
    def _base(self, chave, novos, velhos, manifesto_velho=None):
        definir_eu("alice")
        for nome, blob in velhos.items():
            gravar(self._tmp.name, nome, blob)
        gravar(self._tmp.name, "dados/identidade.json", b"ID-TESTE")
        if manifesto_velho is not None:
            with open(os.path.join(self._tmp.name, "update-manifest.json"),
                      "w", encoding="utf-8") as f:
                json.dump(manifesto_velho, f)
        return preparar_update(novos, chave=chave)

    def test_morte_no_meio_dos_replace_restaura_tudo(self):
        chave = instalar_chave_sintetica(self)
        novos = {"senderme.py": b"novo-1", "config.py": b"novo-2"}
        velhos = {"senderme.py": b"velho-1", "config.py": b"velho-2"}
        env_novo, _ = self._base(chave, novos, velhos)
        env_velho, _ = assinar_release(chave, "1.0", velhos)
        with open(os.path.join(self._tmp.name, "update-manifest.json"),
                  "w", encoding="utf-8") as f:
            json.dump(env_velho, f)
        real_replace = os.replace
        chamadas = []

        def morrer_no_2o(src, dst, *a, **k):
            # só conta os replaces da troca staged->destino (backup,
            # marcador e envelope usam tmp+replace próprio: src termina
            # em .tmp e acontece antes/depois da troca)
            if isinstance(src, str) and src.endswith(".tmp"):
                return real_replace(src, dst, *a, **k)
            chamadas.append(dst)
            if len(chamadas) == 2:
                real_replace(src, dst, *a, **k)
                raise KeyboardInterrupt("kill simulado no meio do replace")
            return real_replace(src, dst, *a, **k)

        with mock.patch("os.replace", side_effect=morrer_no_2o):
            with self.assertRaises(KeyboardInterrupt):
                sm.finalizar_update()
        # reboot
        self.assertTrue(reiniciar_como_boot())
        for nome, blob in velhos.items():
            self.assertEqual(ler(self._tmp.name, nome), blob, nome)
        env_disco = manifest_no_disco(self._tmp.name)
        self.assertEqual(env_disco, env_velho)  # manifesto coerente: velho
        confere_coerencia(self._tmp.name, env_disco)
        self.assertFalse(os.path.exists(
            os.path.join(self._tmp.name, ".upd-pendente.json")))
        self.assertFalse(sm.atualizando)
        self.assertEqual(ler(self._tmp.name, "dados/identidade.json"),
                         b"ID-TESTE")
        _ = env_novo

    def test_morte_apos_replace_antes_do_envelope_volta_tudo(self):
        chave = instalar_chave_sintetica(self)
        novos = {"senderme.py": b"novo-1"}
        velhos = {"senderme.py": b"velho-1"}
        self._base(chave, novos, velhos)
        env_velho, _ = assinar_release(chave, "1.0", velhos)
        with open(os.path.join(self._tmp.name, "update-manifest.json"),
                  "w", encoding="utf-8") as f:
            json.dump(env_velho, f)
        real_replace = os.replace

        def morrer_no_envelope(src, dst, *a, **k):
            # só o envelope (raiz/update-manifest.json.tmp); o backup do
            # manifesto antigo usa tmp+replace dentro de .upd-backup
            # (nome igual de um componente, dir_fd diferente: ver _via_fd)
            cheio = _via_fd(k.get("src_dir_fd"), src)
            if cheio.endswith("update-manifest.json.tmp") \
                    and ".upd-backup" not in cheio:
                raise KeyboardInterrupt("kill antes de persistir envelope")
            return real_replace(src, dst, *a, **k)

        with mock.patch("os.replace", side_effect=morrer_no_envelope):
            with self.assertRaises(KeyboardInterrupt):
                sm.finalizar_update()
        self.assertTrue(reiniciar_como_boot())
        self.assertEqual(ler(self._tmp.name, "senderme.py"), b"velho-1")
        env_disco = manifest_no_disco(self._tmp.name)
        self.assertEqual(env_disco, env_velho)
        confere_coerencia(self._tmp.name, env_disco)
        self.assertFalse(sm.atualizando)

    def test_morte_apos_envelope_antes_de_limpar_marcador_nao_mistura(self):
        """Janela crítica: arquivos novos + envelope novo no disco, marcador
        ainda presente. Recuperação deve voltar ao estado velho COERENTE
        (arquivos velhos + manifesto velho), nunca meio novo/meio velho."""
        chave = instalar_chave_sintetica(self)
        novos = {"senderme.py": b"novo-1"}
        velhos = {"senderme.py": b"velho-1"}
        self._base(chave, novos, velhos)
        env_velho, _ = assinar_release(chave, "1.0", velhos)
        with open(os.path.join(self._tmp.name, "update-manifest.json"),
                  "w", encoding="utf-8") as f:
            json.dump(env_velho, f)
        real_remove = os.remove

        def morrer_no_marcador(path):
            if path.endswith(".upd-pendente.json"):
                raise KeyboardInterrupt("kill antes de limpar marcador")
            return real_remove(path)

        with mock.patch("os.remove", side_effect=morrer_no_marcador):
            with self.assertRaises(KeyboardInterrupt):
                sm.finalizar_update()
        # no momento do kill: arquivos novos + envelope novo + marcador
        self.assertEqual(ler(self._tmp.name, "senderme.py"), b"novo-1")
        self.assertTrue(reiniciar_como_boot())
        self.assertEqual(ler(self._tmp.name, "senderme.py"), b"velho-1")
        env_disco = manifest_no_disco(self._tmp.name)
        self.assertEqual(env_disco, env_velho)
        confere_coerencia(self._tmp.name, env_disco)
        self.assertFalse(os.path.exists(
            os.path.join(self._tmp.name, ".upd-pendente.json")))

    def test_arquivo_novo_sem_backup_e_removido_na_recuperacao(self):
        chave = instalar_chave_sintetica(self)
        novos = {"senderme.py": b"novo-1", "modulo_novo.py": b"novo-m"}
        velhos = {"senderme.py": b"velho-1"}  # modulo_novo.py não existia
        self._base(chave, novos, velhos)
        real_replace = os.replace
        chamadas = []

        def morrer_depois_do_novo(src, dst, *a, **k):
            chamadas.append(dst)
            out = real_replace(src, dst, *a, **k)
            if os.fspath(dst).endswith("modulo_novo.py"):
                raise KeyboardInterrupt("kill logo após gravar arquivo novo")
            return out

        with mock.patch("os.replace", side_effect=morrer_depois_do_novo):
            with self.assertRaises(KeyboardInterrupt):
                sm.finalizar_update()
        self.assertTrue(os.path.exists(
            os.path.join(self._tmp.name, "modulo_novo.py")))
        self.assertTrue(reiniciar_como_boot())
        self.assertEqual(ler(self._tmp.name, "senderme.py"), b"velho-1")
        self.assertFalse(os.path.exists(
            os.path.join(self._tmp.name, "modulo_novo.py")))


class FalhaDeGravacaoAbortaLimpo(CasoIsolado):
    def test_disco_cheio_no_staging_aborta_sem_mudar_nada(self):
        definir_eu("alice")
        chave = instalar_chave_sintetica(self)
        novos = {"senderme.py": b"novo-1"}
        gravar(self._tmp.name, "senderme.py", b"velho-1")
        preparar_update(novos, chave=chave)
        real_os_open = os.open

        def sem_espaco_fd(path, flags, *a, **k):
            # staging agora grava por os.open relativo a fd fixado: o
            # filtro original (".upd-staging" no caminho) é reconstruído
            # via _via_fd; aberturas de diretório passam.
            if (flags & os.O_CREAT) and ".upd-staging" in _via_fd(
                    k.get("dir_fd"), path):
                raise OSError("disco cheio (simulado)")
            return real_os_open(path, flags, *a, **k)

        with mock.patch("os.open", side_effect=sem_espaco_fd):
            self.assertFalse(sm.finalizar_update())
        self.assertFalse(sm.atualizando)
        self.assertEqual(ler(self._tmp.name, "senderme.py"), b"velho-1")
        self.assertFalse(os.path.exists(
            os.path.join(self._tmp.name, ".upd-pendente.json")))

    def test_falha_no_replace_reverte_e_nao_prende_flag(self):
        definir_eu("alice")
        chave = instalar_chave_sintetica(self)
        novos = {"senderme.py": b"novo-1", "config.py": b"novo-2"}
        for nome, blob in (("senderme.py", b"velho-1"),
                           ("config.py", b"velho-2")):
            gravar(self._tmp.name, nome, blob)
        env_velho, _ = assinar_release(
            chave, "1.0", {"senderme.py": b"velho-1",
                           "config.py": b"velho-2"})
        with open(os.path.join(self._tmp.name, "update-manifest.json"),
                  "w", encoding="utf-8") as f:
            json.dump(env_velho, f)
        preparar_update(novos, chave=chave)
        real_replace = os.replace
        n = {"i": 0}

        def falhar_2o(src, dst, *a, **k):
            # conta só os replaces da troca staged->destino (backup,
            # marcador e envelope usam tmp+replace: src termina em .tmp)
            if isinstance(src, str) and not src.endswith(".tmp"):
                n["i"] += 1
                if n["i"] == 2:
                    raise OSError("disco cheio (simulado)")
            return real_replace(src, dst, *a, **k)

        with mock.patch("os.replace", side_effect=falhar_2o):
            self.assertFalse(sm.finalizar_update())
        self.assertFalse(sm.atualizando)
        self.assertEqual(ler(self._tmp.name, "senderme.py"), b"velho-1")
        self.assertEqual(ler(self._tmp.name, "config.py"), b"velho-2")
        self.assertEqual(manifest_no_disco(self._tmp.name), env_velho)
        # sem resto preso no boot seguinte
        self.assertFalse(reiniciar_como_boot())
        self.assertEqual(ler(self._tmp.name, "senderme.py"), b"velho-1")

    def test_falha_no_envelope_reverte_arquivos_e_manifesto(self):
        definir_eu("alice")
        chave = instalar_chave_sintetica(self)
        novos = {"senderme.py": b"novo-1"}
        gravar(self._tmp.name, "senderme.py", b"velho-1")
        env_velho, _ = assinar_release(chave, "1.0",
                                       {"senderme.py": b"velho-1"})
        with open(os.path.join(self._tmp.name, "update-manifest.json"),
                  "w", encoding="utf-8") as f:
            json.dump(env_velho, f)
        preparar_update(novos, chave=chave)
        real_os_open = os.open

        def falhar_envelope_fd(path, flags, *a, **k):
            # tmp do manifesto (backup em .upd-backup ou envelope na
            # raiz) agora é criado por os.open relativo a fd fixado.
            if os.fspath(path).endswith("update-manifest.json.tmp") \
                    and (flags & os.O_CREAT):
                raise OSError("disco cheio (simulado)")
            return real_os_open(path, flags, *a, **k)

        with mock.patch("os.open", side_effect=falhar_envelope_fd):
            self.assertFalse(sm.finalizar_update())
        self.assertFalse(sm.atualizando)
        self.assertEqual(ler(self._tmp.name, "senderme.py"), b"velho-1")
        self.assertEqual(manifest_no_disco(self._tmp.name), env_velho)

    def test_falha_no_meio_da_escrita_do_backup_preserva_original(self):
        """Regressão: backup gravado com truncamento in-place e morte no
        meio da escrita deixava backup parcial, e o `except` o restaurava
        por cima do destino íntegro. Backup deve ser tmp+replace atômico:
        parcial nunca vira backup, original permanece íntegro."""
        definir_eu("alice")
        chave = instalar_chave_sintetica(self)
        novos = {"senderme.py": b"novo-1"}
        gravar(self._tmp.name, "senderme.py", b"velho-1")
        preparar_update(novos, chave=chave)
        real_write = os.write

        def escrever(fd, dado, *a, **k):
            # backup tmp agora é escrito por os.write em fd fixado: o
            # filtro original (".upd-backup" no caminho) é reconstruído
            # via /proc; staging (.upd-staging) passa intacto.
            try:
                alvo = os.readlink("/proc/self/fd/%d" % (fd,))
            except (OSError, TypeError):
                alvo = ""
            if ".upd-backup" in alvo:
                real_write(fd, dado[:1])  # parcial, depois morre
                raise OSError("falha no meio do backup (simulado)")
            return real_write(fd, dado, *a, **k)

        with mock.patch("os.write", side_effect=escrever):
            self.assertFalse(sm.finalizar_update())
        self.assertFalse(sm.atualizando)
        self.assertEqual(ler(self._tmp.name, "senderme.py"), b"velho-1")
        self.assertFalse(os.path.exists(
            os.path.join(self._tmp.name, ".upd-pendente.json")))
        # boot seguinte não tem o que desfazer e mantém o original
        self.assertFalse(reiniciar_como_boot())
        self.assertEqual(ler(self._tmp.name, "senderme.py"), b"velho-1")


class PacoteRuimAborta(CasoIsolado):
    def test_chunk_faltando_aborta_sem_mudar_nada(self):
        definir_eu("alice")
        chave = instalar_chave_sintetica(self)
        novos = {"senderme.py": b"novo-1", "config.py": b"novo-2"}
        env, manif = assinar_release(chave, "99.0", novos)
        gravar(self._tmp.name, "senderme.py", b"velho-1")
        gravar(self._tmp.name, "config.py", b"velho-2")
        sm.update_manifest = manif
        sm.update_envelope = env
        sm.atualizando = True
        montar_no_estado({"senderme.py": b"novo-1"})  # config.py sem chunk
        self.assertFalse(sm.finalizar_update())
        self.assertFalse(sm.atualizando)
        self.assertEqual(ler(self._tmp.name, "senderme.py"), b"velho-1")

    def test_arquivo_adulterado_aborta_sem_mudar_nada(self):
        definir_eu("alice")
        chave = instalar_chave_sintetica(self)
        novos = {"senderme.py": b"novo-1"}
        env, manif = assinar_release(chave, "99.0", novos)
        gravar(self._tmp.name, "senderme.py", b"velho-1")
        sm.update_manifest = manif
        sm.update_envelope = env
        sm.atualizando = True
        montar_no_estado({"senderme.py": b"ADULTERADO"})
        self.assertFalse(sm.finalizar_update())
        self.assertFalse(sm.atualizando)
        self.assertEqual(ler(self._tmp.name, "senderme.py"), b"velho-1")

    def test_assinatura_invalida_ignorada_na_meta(self):
        definir_eu("alice")
        chave = instalar_chave_sintetica(self)
        env, _ = assinar_release(chave, "99.0", {"senderme.py": b"x"})
        env_ruim = {"manifest": {"v": "99.0", "arquivos": [
            {"nome": "senderme.py", "tamanho": 1,
             "sha256": "0" * 64}]}, "sig": env["sig"]}
        with mock.patch("senderme_app.update.baixar_update", lambda: None):
            sm.receber_update_meta(env_ruim)
        self.assertFalse(sm.atualizando)
        self.assertIsNone(sm.update_manifest)


class RecuperacaoParcialR3(CasoIsolado):
    """R3: marcador só sai com faltando vazio; backup fica p/ retry."""

    def _pendente(self, chave, novos, velhos):
        definir_eu("alice")
        for nome, blob in velhos.items():
            gravar(self._tmp.name, nome, blob)
        gravar(self._tmp.name, "dados/identidade.json", b"ID-TESTE")
        env_velho, _ = assinar_release(chave, "1.0", velhos)
        with open(os.path.join(self._tmp.name, "update-manifest.json"),
                  "w", encoding="utf-8") as f:
            json.dump(env_velho, f)
        preparar_update(novos, chave=chave)
        real_replace = os.replace

        def morrer_no_2o(src, dst, *a, **k):
            # backup/marcador usam tmp+replace (src termina em .tmp):
            # mata logo após o 1º replace da troca staged->destino.
            if isinstance(src, str) and src.endswith(".tmp"):
                return real_replace(src, dst, *a, **k)
            out = real_replace(src, dst, *a, **k)
            raise KeyboardInterrupt("kill no meio do replace")
        with mock.patch("os.replace", side_effect=morrer_no_2o):
            with self.assertRaises(KeyboardInterrupt):
                sm.finalizar_update()
        self.assertTrue(os.path.exists(
            os.path.join(self._tmp.name, ".upd-pendente.json")))
        return env_velho

    def test_falha_transitoria_mantem_marcador_e_segundo_boot_recupera(self):
        chave = instalar_chave_sintetica(self)
        novos = {"senderme.py": b"novo-1"}
        velhos = {"senderme.py": b"velho-1"}
        self._pendente(chave, novos, velhos)
        real_os_open = os.open

        def falhar_backup_fd(path, flags, *a, **k):
            # recovery lê o backup por os.open relativo a fd fixado
            # (sem seguir symlink); aberturas de diretório passam.
            if ".upd-backup" in _via_fd(k.get("dir_fd"), path) \
                    and not (flags & os.O_DIRECTORY):
                raise OSError("leitura transitória (simulada)")
            return real_os_open(path, flags, *a, **k)

        with mock.patch("os.open", side_effect=falhar_backup_fd):
            self.assertTrue(reiniciar_como_boot())
        # parcial: marcador fica, backup fica, instalado segue novo
        self.assertTrue(os.path.exists(
            os.path.join(self._tmp.name, ".upd-pendente.json")))
        self.assertTrue(os.path.isdir(
            os.path.join(self._tmp.name, ".upd-backup")))
        self.assertEqual(ler(self._tmp.name, "senderme.py"), b"novo-1")
        # falha sanada: segundo boot recupera integral
        self.assertTrue(reiniciar_como_boot())
        self.assertEqual(ler(self._tmp.name, "senderme.py"), b"velho-1")
        self.assertFalse(os.path.exists(
            os.path.join(self._tmp.name, ".upd-pendente.json")))
        self.assertFalse(os.path.exists(
            os.path.join(self._tmp.name, ".upd-backup")))

    def test_falha_ao_remover_marcador_mantem_backup(self):
        chave = instalar_chave_sintetica(self)
        novos = {"senderme.py": b"novo-1"}
        velhos = {"senderme.py": b"velho-1"}
        self._pendente(chave, novos, velhos)
        real_remove = os.remove

        def prender_marcador(path, *a, **k):
            if isinstance(path, str) and path.endswith(".upd-pendente.json"):
                raise OSError("sem permissão (simulado)")
            return real_remove(path, *a, **k)

        with mock.patch("os.remove", side_effect=prender_marcador):
            self.assertTrue(reiniciar_como_boot())
        self.assertTrue(os.path.exists(
            os.path.join(self._tmp.name, ".upd-pendente.json")))
        self.assertTrue(os.path.isdir(
            os.path.join(self._tmp.name, ".upd-backup")))
        self.assertTrue(reiniciar_como_boot())
        self.assertEqual(ler(self._tmp.name, "senderme.py"), b"velho-1")
        self.assertFalse(os.path.exists(
            os.path.join(self._tmp.name, ".upd-pendente.json")))

    def test_falha_ao_gravar_marcador_aborta_sem_resto(self):
        definir_eu("alice")
        chave = instalar_chave_sintetica(self)
        novos = {"senderme.py": b"novo-1"}
        gravar(self._tmp.name, "senderme.py", b"velho-1")
        preparar_update(novos, chave=chave)
        import senderme_app.update as upd_mod
        real_escrever = upd_mod._escrever_rel

        def sem_marcador(root_fd, rel, dados):
            # Falha de disco simulada na gravação do marcador (pós-1.10 o
            # marcador sai por _escrever_rel relativo a fd, não por
            # builtins.open absoluto).
            if rel.endswith(".upd-pendente.json.tmp"):
                raise OSError("disco cheio (simulado)")
            return real_escrever(root_fd, rel, dados)

        with mock.patch.object(upd_mod, "_escrever_rel",
                               side_effect=sem_marcador):
            self.assertFalse(sm.finalizar_update())
        self.assertFalse(sm.atualizando)
        self.assertEqual(ler(self._tmp.name, "senderme.py"), b"velho-1")
        self.assertFalse(os.path.exists(
            os.path.join(self._tmp.name, ".upd-pendente.json")))

    def test_finalizar_com_marcador_preso_nao_finge_sucesso(self):
        definir_eu("alice")
        chave = instalar_chave_sintetica(self)
        novos = {"senderme.py": b"novo-1"}
        gravar(self._tmp.name, "senderme.py", b"velho-1")
        preparar_update(novos, chave=chave)
        real_remove = os.remove

        def prender(path, *a, **k):
            if isinstance(path, str) and path.endswith(".upd-pendente.json"):
                raise OSError("sem permissão (simulado)")
            return real_remove(path, *a, **k)

        with mock.patch("os.remove", side_effect=prender):
            self.assertFalse(sm.finalizar_update())
        # gravou o novo mas sem limpar o marcador: backup fica, sem restart
        self.assertEqual(ler(self._tmp.name, "senderme.py"), b"novo-1")
        self.assertTrue(os.path.exists(
            os.path.join(self._tmp.name, ".upd-pendente.json")))
        self.assertTrue(os.path.isdir(
            os.path.join(self._tmp.name, ".upd-backup")))

    def test_preboot_nao_importa_senderme_app(self):
        import re
        caminho = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "senderme_app", "preboot.py")
        with open(caminho, encoding="utf-8") as f:
            src = f.read()
        for linha in src.splitlines():
            s = linha.strip()
            if s.startswith("import ") or s.startswith("from "):
                self.assertNotIn("senderme", s, linha)
                self.assertFalse(s.startswith("from ."), linha)


class SigkillRealRecuperaVersaoDoDisco(unittest.TestCase):
    """R2 em processo real: SIGKILL no meio da troca + reboot serve o disco.

    Lento (~10 s): dois start.sh reais, chave/identidades sintéticas em tmp,
    portas via bind, stub xdg-open, limpeza total. Cenário preservado da
    sonda (vermelho na 1.6: servia 9.9 com disco em 9.8).
    """

    def test_sigkill_na_troca_reboot_serve_versao_restaurada(self):
        import shutil
        import signal
        import sys
        import tempfile
        import time
        RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, os.path.join(RAIZ, "tests"))
        sys.path.insert(0, RAIZ)
        from test_update_e2e_abc import (montar_conteudo, escrever_instalacao,
                                         Processo)
        from crypto import assinar
        import senderme_app.update as upd_mod
        _bin = tempfile.TemporaryDirectory(prefix="sm-sigkill-bin-")
        self.addCleanup(_bin.cleanup)
        _xdg = os.path.join(_bin.name, "xdg-open")
        with open(_xdg, "w") as f:
            f.write("#!/bin/sh\nexit 0\n")
        os.chmod(_xdg, 0o700)
        velho_path = os.environ.get("PATH", "")
        os.environ["PATH"] = _bin.name + os.pathsep + velho_path
        self.addCleanup(os.environ.__setitem__, "PATH", velho_path)
        os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

        def envelope(conteudo, versao, chave):
            import hashlib
            m = {"v": versao, "arquivos": [
                {"nome": n, "tamanho": len(conteudo[n]),
                 "sha256": hashlib.sha256(conteudo[n]).hexdigest()}
                for n in sorted(conteudo)]}
            return {"manifest": m, "sig": assinar(
                upd_mod.manifest_canonico(m), chave).hex()}

        chave = chave_teste()
        velho = montar_conteudo("9.8", chave)
        novo = montar_conteudo("9.9", chave)
        alvo = (b'            for nome in blobs:\n'
                b'                dest = os.path.join(S.PASTA, nome)\n'
                b'                _substituir(root_fd, ".upd-staging/" + nome,'
                b' nome)\n')
        inj = (alvo + b'                if nome == "senderme_app/meta.py" '
               b'and os.environ.get("SM_AUDIT_PAUSE"):\n'
               b'                    with open(os.environ["SM_AUDIT_PAUSE"], "w") '
               b'as f:\n'
               b'                        f.write(str(os.getpid()))\n'
               b'                    import signal\n'
               b'                    os.kill(os.getpid(), signal.SIGSTOP)\n')
        self.assertIn(alvo, velho["senderme_app/update.py"])
        velho["senderme_app/update.py"] = velho[
            "senderme_app/update.py"].replace(alvo, inj, 1)
        inst_a = escrever_instalacao(novo, envelope(novo, "9.9", chave), "a")
        self.addCleanup(shutil.rmtree, inst_a, True)
        inst_b = escrever_instalacao(velho, envelope(velho, "9.8", chave), "b")
        self.addCleanup(shutil.rmtree, inst_b, True)
        marca = os.path.join(inst_b, "audit-paused")
        os.environ["SM_AUDIT_PAUSE"] = marca
        self.addCleanup(os.environ.pop, "SM_AUDIT_PAUSE", None)
        a = Processo(self, inst_a, "a")
        b = Processo(self, inst_b, "b", fixos="127.0.0.1:%d" % a.tcp)
        self.assertEqual(a.esperar_eu("a")["versao"], "9.9")
        self.assertEqual(b.esperar_eu("b")["versao"], "9.8")
        fim = time.time() + 60
        while time.time() < fim and not os.path.exists(marca):
            time.sleep(0.1)
        self.assertTrue(os.path.exists(marca), "pausa não atingida")
        with open(marca) as f:
            pid = int(f.read())
        os.kill(pid, signal.SIGKILL)
        b.proc.wait(timeout=30)
        self.assertTrue(os.path.exists(
            os.path.join(inst_b, ".upd-pendente.json")))
        a.fechar()
        os.environ.pop("SM_AUDIT_PAUSE", None)
        reiniciado = Processo(self, inst_b, "b")
        eu = reiniciado.esperar_eu("b")
        with open(os.path.join(inst_b, "senderme_app", "meta.py"),
                  encoding="utf-8") as f:
            texto = f.read()
        self.assertEqual(eu["versao"], "9.8")
        self.assertIn('"SENDERME_VERSAO", "9.8"', texto)


if __name__ == "__main__":
    unittest.main()
