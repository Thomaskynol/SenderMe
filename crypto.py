#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SenderMe — criptografia RSA-2048 em Python puro (só biblioteca padrão).

Folha sem dependências do resto do app: não importa nenhum outro módulo
do projeto. `senderme.py` re-exporta estes nomes (contrato dos testes e
de `dono/assinar_update.py`, que usam `sm.assinar`, `sm.conferir`, etc.).

- Geração: dois primos de 1024 bits (Miller-Rabin, 24 rodadas), `e = 65537`.
- Assinatura EMSA-PKCS1-v1_5 + SHA-256.
- ID = `sha256(n || e)[:40]` (impressão digital da chave pública).
"""
import hashlib
import secrets

_PEQUENOS = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53,
             59, 61, 67, 71, 73, 79, 83, 89, 97, 101, 103, 107, 109, 113)
_SHA256_DER = bytes.fromhex("3031300d060960864801650304020105000420")


def _miller_rabin(n, rodadas=24):
    if n < 2:
        return False
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(rodadas):
        a = secrets.randbelow(n - 3) + 2
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _primo(bits):
    while True:
        p = secrets.randbits(bits) | (1 << (bits - 1)) | (1 << (bits - 2)) | 1
        if any(p % q == 0 for q in _PEQUENOS):
            continue
        if _miller_rabin(p):
            return p


def _inv(a, m):
    g, x, old_g, old_x = m, 0, a, 1
    while g:
        q = old_g // g
        old_g, g = g, old_g - q * g
        old_x, x = x, old_x - q * x
    if old_g != 1:
        raise ValueError("não invertível")
    return old_x % m


def fingerprint(n, e):
    nb = n.to_bytes((n.bit_length() + 7) // 8, "big")
    eb = e.to_bytes(max(1, (e.bit_length() + 7) // 8), "big")
    return hashlib.sha256(nb + eb).hexdigest()[:40]


def gerar_chave():
    # Sem log aqui (folha pura): quem chama avisa o usuário.
    while True:
        p, q = _primo(1024), _primo(1024)
        if p == q:
            continue
        n = p * q
        try:
            d = _inv(65537, (p - 1) * (q - 1))
        except ValueError:
            continue
        if p < q:
            p, q = q, p
        return {"n": n, "e": 65537, "d": d}


def assinar(dados, chave):
    k = (chave["n"].bit_length() + 7) // 8
    t = _SHA256_DER + hashlib.sha256(dados).digest()
    ps = b"\xff" * (k - 3 - len(t))
    em = b"\x00\x01" + ps + b"\x00" + t
    s = pow(int.from_bytes(em, "big"), chave["d"], chave["n"])
    return s.to_bytes(k, "big")


def conferir(dados, assinatura, n, e):
    k = (n.bit_length() + 7) // 8
    if len(assinatura) != k:
        return False
    s = int.from_bytes(assinatura, "big")
    if s >= n or s < 0:
        return False
    t = _SHA256_DER + hashlib.sha256(dados).digest()
    esperado = b"\x00\x01" + b"\xff" * (k - 3 - len(t)) + b"\x00" + t
    try:
        obtido = pow(s, e, n).to_bytes(k, "big")
    except (ValueError, OverflowError):
        return False
    return secrets.compare_digest(obtido, esperado)
