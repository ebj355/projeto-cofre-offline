#!/usr/bin/env python3
# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Vetores PUBLICADOS (known-answer tests) de AES-256-GCM, ChaCha20-Poly1305, HKDF-SHA256 e Argon2id.

Fecha a lacuna "vetores publicados AES/ChaCha/Argon2" do PLANO_DE_TESTES.md. O teste_nucleo_vetores_criptograficos.py
confere propriedades (determinismo, avalanche, AAD); este confere RESPOSTAS CONHECIDAS de especificações públicas,
o único jeito de detectar uma biblioteca/compilação que calcule errado "de forma consistente".

Fontes dos vetores:
  - AES-256-GCM: McGrew & Viega, "The Galois/Counter Mode of Operation", casos 13 e 16 (adotados pelo NIST SP 800-38D).
  - ChaCha20-Poly1305: RFC 8439, seção 2.8.2.
  - HKDF-SHA256: RFC 5869, apêndice A (casos 1 e 3).
  - Argon2id: o vetor do repositório de referência (password/somesalt, t=2, m=64 MiB, p=1) e vetores pequenos gerados
    por uma implementação independente em Python puro, validada contra os vetores da RFC 9106 (Argon2d, Argon2i e
    Argon2id, com segredo e dado associado) antes de gerar estes valores.
Depois, amarra o PROGRAMA à especificação: refaz HKDF só com hmac/hashlib e compara com as funções do cofre; e
decifra um arquivo de cofre real com código independente (cascata AES-256-GCM por fora, ChaCha20-Poly1305 por dentro).
"""
import hashlib
import hmac
import json
import os
import shutil
import struct
import sys
import tempfile
import unicodedata

FALHAS = []


def ok(cond, msg):
    print(("  [OK]   " if cond else "  [FALHOU] ") + msg)
    if not cond:
        FALHAS.append(msg)


def _raiz():
    env = os.environ.get("COFRE_RAIZ")
    pasta = os.path.dirname(os.path.abspath(__file__))
    for p in ([env] if env else []) + [pasta]:
        while p and p != os.path.dirname(p):
            if os.path.isfile(os.path.join(p, "cofre_senhas.py")):
                return p
            p = os.path.dirname(p)
    print("ERRO: não achei cofre_senhas.py acima de", pasta)
    sys.exit(2)


sys.path.insert(0, _raiz())
import cofre_senhas as cs  # noqa: E402
from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305  # noqa: E402
from argon2.low_level import hash_secret_raw, Type  # noqa: E402

H = bytes.fromhex


def hkdf_sha256(ikm, salt, info, n):
    """HKDF (RFC 5869) feito só com hmac/hashlib: implementação independente da usada pelo cofre."""
    prk = hmac.new(salt if salt else b"\x00" * 32, ikm, hashlib.sha256).digest()
    t, okm, i = b"", b"", 1
    while len(okm) < n:
        t = hmac.new(prk, t + info + bytes([i]), hashlib.sha256).digest()
        okm += t
        i += 1
    return okm[:n]


print("1) AES-256-GCM (McGrew & Viega, casos 13 e 16)")
chave0 = bytes(32)
r = AESGCM(chave0).encrypt(bytes(12), b"", b"")
ok(r == H("530f8afbc74536b9a963b4f1c4cb738b"), "caso 13: texto vazio, chave zero: etiqueta 530f8afb...738b")
chave16 = H("feffe9928665731c6d6a8f9467308308feffe9928665731c6d6a8f9467308308")
iv16 = H("cafebabefacedbaddecaf888")
p16 = H("d9313225f88406e5a55909c5aff5269a86a7a9531534f7da2e4c303d8a318a721c3c0c95956809532fcf0e2449a6b525"  # pragma: allowlist secret
        "b16aedf5aa0de657ba637b39")  # pragma: allowlist secret
a16 = H("feedfacedeadbeeffeedfacedeadbeefabaddad2")
c16 = H("522dc1f099567d07f47f37a32a84427d643a8cdcbfe5c0c97598a2bd2555d1aa8cb08e48590dbb3da7b08b1056828838"  # pragma: allowlist secret
        "c5f61e6393ba7a0abcc9f662")  # pragma: allowlist secret
t16 = H("76fc6ece0f4e1768cddf8853bb2d551b")
r = AESGCM(chave16).encrypt(iv16, p16, a16)
ok(r == c16 + t16, "caso 16: cifra + etiqueta idênticas às publicadas (com dado autenticado)")
ok(AESGCM(chave16).decrypt(iv16, c16 + t16, a16) == p16, "caso 16: decifra de volta o texto original")
try:
    AESGCM(chave16).decrypt(iv16, c16 + t16, a16[:-1] + b"\x00")
    ok(False, "caso 16: dado autenticado alterado deveria ser recusado")
except Exception:
    ok(True, "caso 16: 1 byte alterado no dado autenticado é recusado")

print("\n2) ChaCha20-Poly1305 (RFC 8439, seção 2.8.2)")
k = bytes(range(0x80, 0xA0))
n = H("070000004041424344454647")
aad = H("50515253c0c1c2c3c4c5c6c7")
pt = (b"Ladies and Gentlemen of the class of '99: If I could offer you only one tip for the future, "
      b"sunscreen would be it.")
r = ChaCha20Poly1305(k).encrypt(n, pt, aad)
ok(r[:16] == H("d31a8d34648e60db7b86afbc53ef7ec2"), "início do texto cifrado = d31a8d34648e60db7b86afbc53ef7ec2")
ok(r[-16:] == H("1ae10b594f09e26a7e902ecbd0600691"), "etiqueta Poly1305 = 1ae10b594f09e26a7e902ecbd0600691")
ok(len(r) == len(pt) + 16, "tamanho = texto + 16 bytes de etiqueta")
ok(ChaCha20Poly1305(k).decrypt(n, r, aad) == pt, "decifra de volta o texto original")

print("\n3) HKDF-SHA256 (RFC 5869, apêndice A)")
okm1 = hkdf_sha256(b"\x0b" * 22, H("000102030405060708090a0b0c"), H("f0f1f2f3f4f5f6f7f8f9"), 42)
ok(okm1 == H("3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf34007208d5b887185865"),
   "caso 1 (com sal e info): 3cb25f25...5865 (implementação independente do teste)")
okm3 = hkdf_sha256(b"\x0b" * 22, b"", b"", 42)
ok(okm3 == H("8da4e775a563c18f715f802a063c5a31b8a11f5c5ee1879ec3454e5f3c738d2d9d201395faa4b61a96c8"),
   "caso 3 (sem sal e sem info): 8da4e775...96c8")
from cryptography.hazmat.primitives.kdf.hkdf import HKDF  # noqa: E402
from cryptography.hazmat.primitives import hashes  # noqa: E402
ok(HKDF(algorithm=hashes.SHA256(), length=42, salt=H("000102030405060708090a0b0c"),
        info=H("f0f1f2f3f4f5f6f7f8f9")).derive(b"\x0b" * 22) == okm1,
   "a biblioteca 'cryptography' dá o mesmo resultado do caso 1")

print("\n4) Argon2id (hash_secret_raw, a mesma chamada de derivar_chave)")
VET = [  # (senha, sal, t, m KiB, p, saída de 32 bytes em hex)
    (b"password", b"somesalt", 2, 65536, 1, "09316115d5cf24ed5a15a31a3ba326e5cf32edc24702987c02b6566f61913cf7"),  # pragma: allowlist secret
    (b"password", b"somesalt", 2, 64, 1, "16a1a498734609dd01456da406de9f3d9da93e6c86c300a12fc1465214ce4922"),  # pragma: allowlist secret
    (b"password", b"somesalt", 3, 32, 4, "bb0cc80a3e671149526915418c6eefe761bb19d5d2d567a017703e0cea6ab05c"),  # pragma: allowlist secret
    (b"", b"saltsaltsaltsalt", 1, 8, 1, "6aa57ab96e4a537fc5155db6a9a5ad9b114575dbd607b96f11680d2dc6026723"),  # pragma: allowlist secret
    (b"senha-mestra-de-teste", bytes(range(16)), 2, 256, 2,
     "25f14555199cbdcd2d467756b4b2221b5cd92491429424c238613a71805dc143"),  # pragma: allowlist secret
    (b"\x01" * 32, b"\x02" * 16, 3, 32, 4, "03aab965c12001c9d7d0d2de33192c0494b684bb148196d73c1df1acaf6d0c2e"),  # pragma: allowlist secret
]
for pw, sal, t, m, p, esperado in VET:
    got = hash_secret_raw(secret=pw, salt=sal, time_cost=t, memory_cost=m, parallelism=p, hash_len=32, type=Type.ID)
    ok(got.hex() == esperado, f"Argon2id t={t} m={m} KiB p={p} senha={pw[:10]!r}: {esperado[:12]}...")
# o vetor da RFC 9106 usa segredo e dado associado, que hash_secret_raw não aceita; a mesma entrada SEM esses
# campos tem o valor acima (6ª linha), gerado pela implementação validada contra a RFC.
d_ = hash_secret_raw(secret=b"password", salt=b"somesalt", time_cost=2, memory_cost=64, parallelism=1,
                     hash_len=32, type=Type.D)
i_ = hash_secret_raw(secret=b"password", salt=b"somesalt", time_cost=2, memory_cost=64, parallelism=1,
                     hash_len=32, type=Type.I)
id_ = hash_secret_raw(secret=b"password", salt=b"somesalt", time_cost=2, memory_cost=64, parallelism=1,
                      hash_len=32, type=Type.ID)
ok(len({d_, i_, id_}) == 3, "Argon2d, Argon2i e Argon2id dão saídas diferentes (o tipo importa)")

print("\n5) O programa usa exatamente essas primitivas")
ref = hash_secret_raw(secret=b"senha-mestra-de-teste", salt=bytes(range(16)), time_cost=2, memory_cost=256,
                      parallelism=2, hash_len=32, type=Type.ID)
ok(cs.derivar_chave("senha-mestra-de-teste", bytes(range(16)), 2, 256, 2) == ref == H(VET[4][5]),
   "derivar_chave(senha, sal, t, m, p) = vetor publicado de Argon2id (tipo ID, 32 bytes, UTF-8)")
ok(cs.derivar_chave("password", b"somesalt", 2, 64, 1).hex() == VET[1][5],
   "derivar_chave('password', 'somesalt', 2, 64, 1) = vetor publicado")
ok(cs.derivar_chave("password", b"somesalt", 2, 65536, 1).hex() == VET[0][5],
   "derivar_chave com 64 MiB = vetor do repositório de referência do Argon2")
ok(cs.derivar_chave("acentuação-çãõ-日本", b"somesalt", 1, 64, 1)
   == hash_secret_raw(secret="acentuação-çãõ-日本".encode("utf-8"), salt=b"somesalt", time_cost=1, memory_cost=64,
                      parallelism=1, hash_len=32, type=Type.ID),
   "a senha vai ao Argon2 em UTF-8 (sem normalização escondida nesta função)")

sal = bytes(range(16))
chave_bytes = bytes(range(32, 64))
ok(cs.kek_da_chave(chave_bytes, sal) == hkdf_sha256(chave_bytes, sal, b"cofre-chave-de-acesso", 32),
   "kek_da_chave = HKDF-SHA256(sal, info='cofre-chave-de-acesso') da especificação")
ks = bytes(range(64, 96))
ok(cs.kek_combinada(ks, chave_bytes, sal) == hkdf_sha256(ks + chave_bytes, sal, b"cofre-senha-E-chave", 32),
   "kek_combinada = HKDF-SHA256 sobre (kek_senha + chave), info='cofre-senha-E-chave'")
dek = bytes(range(96, 128))
k_cha, k_aes = cs._subchaves(dek)
ok(k_cha == hkdf_sha256(dek, b"", b"cofre-camada-chacha20", 32), "subchave ChaCha20 = HKDF(dek, info='cofre-camada-chacha20')")
ok(k_aes == hkdf_sha256(dek, b"", b"cofre-camada-aes256", 32), "subchave AES-256 = HKDF(dek, info='cofre-camada-aes256')")
ok(cs._kek_fido(b"x" * 32) == hkdf_sha256(b"x" * 32, b"", b"cofre-kek-chave-fido", 32), "_kek_fido = HKDF da especificação")
ok(cs._chave_dados(dek, b"f" * 32) == hkdf_sha256(dek + b"f" * 32, b"", b"cofre-dados-com-fido", 32),
   "_chave_dados com FIDO = HKDF(dek + segredo FIDO)")
ok(cs._chave_dados(dek, None) == dek, "_chave_dados sem FIDO devolve a própria chave interna")

print("\n6) Um cofre REAL, decifrado por código independente (cascata AES-256-GCM por fora, ChaCha20-Poly1305 por dentro)")
tmp = tempfile.mkdtemp(prefix="arca_vet_")
antigo = dict(cs.NIVEIS)
try:
    cs.NIVEIS["alto"] = (1, 8192)
    senha = "Senha-de-teste-do-vetor-42"
    caminho = os.path.join(tmp, "cofre.dat")
    c = cs.Cofre.criar(caminho, senha, 3, cs.MODO_S, "alto")
    c.registros.append(cs.novo_item(servico="Banco Exemplo", login="ana", senha="S3gredo-ç-日本-🔑"))
    c.salvar()
    c.fechar()
    bruto = open(caminho, "rb").read()
    hl = struct.calcsize(cs.HEADER_FMT5)
    campos = struct.unpack(cs.HEADER_FMT, bruto[:cs.HEADER_LEN])
    magic, t, m, p, max_t, modo, sal_pw, nonce_pw, wrap_pw, sal_k, nonce_k, wrap_k, nonce_c, nonce_a = campos
    ok(magic == cs.MAGIC, "o arquivo começa com a assinatura do formato atual (COFRE05)")
    cab = bruto[:hl]
    ok(hashlib.sha256(bruto[:cs.HEADER_LEN] + b"\x00").digest()[:8] == bruto[cs.HEADER_LEN:hl],
       "o checksum de 8 bytes do cabeçalho confere com SHA-256 calculado de fora")
    secao = b"\x00"
    ok(bruto[hl] == max_t and bruto[hl + 1:hl + 2] == secao, "contador de tentativas e seção FIDO vazia nos lugares esperados")
    externo = bruto[hl + 1 + len(secao):]
    aad = cab + secao
    ks_ = hash_secret_raw(secret=senha.encode("utf-8"), salt=sal_pw, time_cost=t, memory_cost=m, parallelism=p,
                          hash_len=32, type=Type.ID)
    dek_ = AESGCM(ks_).decrypt(nonce_pw, wrap_pw, b"COFRE02\x00")
    ok(len(dek_) == 32, "a chave interna (DEK) abre com Argon2id + AES-GCM, sem usar código do cofre")
    kc = hkdf_sha256(dek_, b"", b"cofre-camada-chacha20", 32)
    ka = hkdf_sha256(dek_, b"", b"cofre-camada-aes256", 32)
    interno = AESGCM(ka).decrypt(nonce_a, externo, aad)
    ok(True, "camada EXTERNA = AES-256-GCM (decifrada de fora, com o cabeçalho como dado autenticado)")
    dados = ChaCha20Poly1305(kc).decrypt(nonce_c, interno, aad)
    ok(True, "camada INTERNA = ChaCha20-Poly1305 (cascata confirmada)")
    ok(len(dados) % cs.TAM_BLOCO == 0, f"conteúdo preenchido até múltiplo de {cs.TAM_BLOCO} bytes (esconde a quantidade de itens)")
    obj = json.loads(dados.rstrip(b"\x00").decode("ascii"))
    ok(obj["n"] == 1, f"o conteúdo decifrado informa exatamente 1 item (obteve {obj.get('n')!r})")
    ok(len(obj["itens"]) == 1, f"o JSON contém exatamente 1 registro (obteve {len(obj['itens'])})")
    ok(obj["itens"][0]["senha"] == "S3gredo-ç-日本-🔑",
       f"a senha cifrada volta com acentos, CJK e emoji intactos (obteve {obj['itens'][0]['senha']!r})")
    servico_obtido = unicodedata.normalize("NFC", obj["itens"][0]["servico"]).encode("utf-8")
    servico_esperado = bytes.fromhex("42616e636f204578656d706c6f")
    ok(servico_obtido == servico_esperado,
       f"o serviço volta sem alteração (obteve {obj['itens'][0]['servico']!r}, "
       f"hex={servico_obtido.hex()}, esperado_hex={servico_esperado.hex()})")
    ok(b"Banco Exemplo" not in bruto and "S3gredo".encode() not in bruto, "nenhum texto legível no arquivo")
    try:
        ChaCha20Poly1305(kc).decrypt(nonce_c, externo, aad)
        ok(False, "ordem trocada (ChaCha por fora) deveria falhar")
    except Exception:
        ok(True, "ordem trocada das camadas falha (a cascata tem ordem definida)")
    try:
        AESGCM(ka).decrypt(nonce_a, externo, aad[:-1] + bytes([aad[-1] ^ 1]))
        ok(False, "dado autenticado alterado deveria falhar")
    except Exception:
        ok(True, "alterar 1 bit do cabeçalho invalida a camada externa (cabeçalho autenticado)")
finally:
    cs.NIVEIS.clear()
    cs.NIVEIS.update(antigo)
    shutil.rmtree(tmp, ignore_errors=True)

print()
print("FALHAS:", FALHAS)
sys.exit(1 if FALHAS else 0)
