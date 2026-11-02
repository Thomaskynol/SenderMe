"""Defeito identidade/persistência: corrompido nunca é sobrescrito; falha de
gravação nunca alega sucesso. Escritos ANTES da correção (TDD red→green)."""
import json
import os
import unittest

import senderme as sm
from suporte import CasoIsolado, definir_eu


class IdentidadeCorrompida(CasoIsolado):
    def _arq_ident(self):
        return os.path.join(sm.DADOS, "identidade.json")

    def test_json_invalido_preserva_bytes_e_aborta(self):
        lixo = b"{json quebrado\xff"
        os.makedirs(sm.DADOS, exist_ok=True)
        with open(self._arq_ident(), "wb") as f:
            f.write(lixo)
        with self.assertRaises(SystemExit):
            sm.carregar_identidade()
        with open(self._arq_ident(), "rb") as f:
            self.assertEqual(f.read(), lixo)

    def test_incompleto_preserva_e_aborta(self):
        os.makedirs(sm.DADOS, exist_ok=True)
        bruto = {"n": "ab", "e": 65537}  # sem "d"/"id"
        with open(self._arq_ident(), "w", encoding="utf-8") as f:
            json.dump(bruto, f)
        with self.assertRaises(SystemExit):
            sm.carregar_identidade()
        with open(self._arq_ident(), encoding="utf-8") as f:
            self.assertEqual(json.load(f), bruto)

    def test_id_divergente_aborta(self):
        os.makedirs(sm.DADOS, exist_ok=True)
        with open(self._arq_ident(), "w", encoding="utf-8") as f:
            json.dump({"n": "ab", "e": 65537, "d": "cd", "id": "00" * 20}, f)
        with self.assertRaises(SystemExit):
            sm.carregar_identidade()

    def test_null_preserva_bytes_e_aborta(self):
        # R5: arquivo existente com JSON `null` NÃO é primeiro boot.
        os.makedirs(sm.DADOS, exist_ok=True)
        with open(self._arq_ident(), "w", encoding="utf-8") as f:
            f.write("null")
        with self.assertRaises(SystemExit):
            sm.carregar_identidade()
        with open(self._arq_ident(), encoding="utf-8") as f:
            self.assertEqual(f.read(), "null")

    def test_booleanos_preservam_e_abortam(self):
        for bruto in ("true", "false"):
            with self.subTest(bruto=bruto):
                os.makedirs(sm.DADOS, exist_ok=True)
                with open(self._arq_ident(), "w", encoding="utf-8") as f:
                    f.write(bruto)
                with self.assertRaises(SystemExit):
                    sm.carregar_identidade()
                with open(self._arq_ident(), encoding="utf-8") as f:
                    self.assertEqual(f.read(), bruto)

    def test_lista_e_escalar_preservam_e_abortam(self):
        for bruto in ('[]', '["x"]', '"abc"', '123'):
            with self.subTest(bruto=bruto):
                os.makedirs(sm.DADOS, exist_ok=True)
                with open(self._arq_ident(), "w", encoding="utf-8") as f:
                    f.write(bruto)
                with self.assertRaises(SystemExit):
                    sm.carregar_identidade()
                with open(self._arq_ident(), encoding="utf-8") as f:
                    self.assertEqual(f.read(), bruto)

    def test_objeto_vazio_preserva_e_aborta(self):
        os.makedirs(sm.DADOS, exist_ok=True)
        with open(self._arq_ident(), "w", encoding="utf-8") as f:
            f.write("{}")
        with self.assertRaises(SystemExit):
            sm.carregar_identidade()
        with open(self._arq_ident(), encoding="utf-8") as f:
            self.assertEqual(json.load(f), {})

    def test_falha_leitura_preserva_e_aborta(self):
        # R5: arquivo existe mas não pode ser lido -> SystemExit, sem sobrescrever.
        os.makedirs(sm.DADOS, exist_ok=True)
        with open(self._arq_ident(), "w", encoding="utf-8") as f:
            f.write('{"n": "ab"}')
        import builtins
        real_open = builtins.open

        def _falha(path, *a, **k):
            if isinstance(path, str) and path.endswith("identidade.json"):
                raise OSError("falha de leitura sintética")
            return real_open(path, *a, **k)

        from unittest import mock
        with mock.patch("builtins.open", side_effect=_falha):
            with self.assertRaises(SystemExit):
                sm.carregar_identidade()
        with open(self._arq_ident(), encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"n": "ab"})

    def test_ausente_cria_arquivo_600(self):
        ident = sm.carregar_identidade()
        self.assertIn("id", ident)
        st = os.stat(self._arq_ident())
        self.assertEqual(st.st_mode & 0o777, 0o600)

    def test_falha_ao_gravar_nao_alega_sucesso(self):
        # DADOS como arquivo regular: qualquer escrita falha.
        os.makedirs(sm.DADOS, exist_ok=True)
        os.replace(sm.DADOS, sm.DADOS + ".bak")
        try:
            with open(sm.DADOS, "wb") as f:
                f.write(b"x")
            self.assertFalse(sm.salvar_json("identidade.json", {"a": 1}))
            with self.assertRaises(SystemExit):
                sm.carregar_identidade()
            self.assertFalse(os.path.isfile(
                os.path.join(sm.DADOS, "identidade.json")))
        finally:
            os.remove(sm.DADOS)
            os.replace(sm.DADOS + ".bak", sm.DADOS)

    def test_salvar_json_retorna_sucesso_ou_falha(self):
        self.assertTrue(sm.salvar_json("x.json", {"a": 1}))
        with open(os.path.join(sm.DADOS, "x.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"a": 1})


if __name__ == "__main__":
    unittest.main()
