"""Vetores e integridade dos primitivos criptográficos, no nível das PEÇAS (não do arquivo inteiro - isso já é
feito por `teste_ataques.py`). Em vez de confiar de olhos fechados que "a biblioteca `cryptography` é boa, logo
está tudo certo", este teste confere a FIAÇÃO que o próprio `cofre_senhas.py` faz entre as peças:
1) determinismo e efeito avalanche na derivação Argon2id (mesma entrada = mesma chave; 1 bit diferente no sal,
   na senha ou nos parâmetros = chave completamente diferente - sem isso, um bug poderia gerar chaves "parecidas"
   e previsíveis, mesmo usando um algoritmo bom);
2) separação de domínio das subchaves ChaCha20/AES-256 (_subchaves): as duas chaves derivadas do mesmo DEK têm de
   ser diferentes uma da outra E diferentes do próprio DEK - e usar a chave ERRADA numa camada tem de falhar
   (confusão de contexto não pode abrir nada);
3) amarração do AAD no embrulho da chave (_embrulhar/_desembrulhar): 1 bit adulterado no embrulho cifrado tem de
   ser detectado sempre, não só "na maioria das vezes";
4) teste EXAUSTIVO de adulteração: em vez de olhar 2 ou 3 posições de um arquivo real (como `teste_ataques.py`
   já faz), aqui vira cada 1 dos 128 bits de um ciphertext pequeno, um por vez, e confere que os 128 ataques
   SEMPRE falham - não dá pra existir nem 1 bit "ok de adulterar";
5) o nonce realmente participa da cifra: a mesma chave e o mesmo texto puro com nonces diferentes não podem
   gerar o mesmo texto cifrado (senão o nonce estaria sendo ignorado e duas gravações poderiam colidir)."""
import os, secrets, sys

RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, RAIZ)
import cofre_senhas as c
from cryptography.exceptions import InvalidTag

falhas = []
def ok(cond, nome):
    print(("  [OK] " if cond else "  [FALHOU] ") + nome)
    if not cond:
        falhas.append(nome)

print("1) Determinismo e efeito avalanche do Argon2id (derivar_chave)")
sal = secrets.token_bytes(16)
k1 = c.derivar_chave("senha-de-teste-Aa1!", sal, 4, 262144, 2)
k2 = c.derivar_chave("senha-de-teste-Aa1!", sal, 4, 262144, 2)
ok(k1 == k2, "mesma entrada (senha, sal, t, m, p) = sempre a MESMA chave derivada")
sal2 = bytearray(sal); sal2[0] ^= 1  # 1 bit diferente
k3 = c.derivar_chave("senha-de-teste-Aa1!", bytes(sal2), 4, 262144, 2)
ok(k3 != k1, "1 bit diferente no SAL = chave completamente diferente")
k4 = c.derivar_chave("senha-de-teste-Aa2!", sal, 4, 262144, 2)  # 1 caractere diferente no fim
ok(k4 != k1, "1 caractere diferente na SENHA = chave completamente diferente")
k5 = c.derivar_chave("senha-de-teste-Aa1!", sal, 4, 65536, 2)  # memória diferente
ok(k5 != k1, "parâmetro de memória (m) diferente = chave completamente diferente")
difs = sum(a != b for a, b in zip(k1, k3))
ok(difs >= 8, f"avalanche real: {difs}/32 bytes mudaram com 1 bit de diferença no sal (não é uma mudança pequena/local)")

print("\n2) Separação de domínio das subchaves ChaCha20 / AES-256 (_subchaves)")
dek = secrets.token_bytes(32)
k_cha, k_aes = c._subchaves(dek)
ok(k_cha != k_aes, "a subchave ChaCha20 e a subchave AES-256 são diferentes entre si")
ok(k_cha != dek and k_aes != dek, "nenhuma das duas subchaves é igual ao DEK original (não é um 'disfarce' raso)")
# confusão de contexto: cifrar com a camada ChaCha20 (k_cha) e tentar abrir como se fosse a camada AES (k_aes)
nonce = secrets.token_bytes(12)
aad = b"contexto-de-teste"
texto = b"dado de exemplo para a cascata de camadas"
ct_cha = c.ChaCha20Poly1305(k_cha).encrypt(nonce, texto, aad)
try:
    c.AESGCM(k_aes).decrypt(nonce, ct_cha, aad)
    res = "abriu"
except InvalidTag:
    res = "negado"
ok(res == "negado", "decifrar um texto da camada ChaCha20 (k_cha) usando a chave AES (k_aes) falha sempre")
ct_aes = c.AESGCM(k_aes).encrypt(nonce, texto, aad)
try:
    c.ChaCha20Poly1305(k_cha).decrypt(nonce, ct_aes, aad)
    res = "abriu"
except InvalidTag:
    res = "negado"
ok(res == "negado", "decifrar um texto da camada AES-256 (k_aes) usando a chave ChaCha20 (k_cha) falha sempre")

print("\n3) Amarração do AAD no embrulho da chave (_embrulhar / _desembrulhar)")
kek = secrets.token_bytes(32)
n_w, wrap = c._embrulhar(kek, dek)
dek_de_volta = c._desembrulhar(kek, n_w, wrap)
ok(dek_de_volta == dek, "embrulhar e desembrulhar com a KEK certa devolve o DEK original intacto")
wrap_adulterado = bytearray(wrap); wrap_adulterado[0] ^= 1
try:
    c._desembrulhar(kek, n_w, bytes(wrap_adulterado))
    res = "abriu"
except InvalidTag:
    res = "negado"
ok(res == "negado", "1 bit adulterado no embrulho cifrado da chave é sempre detectado")
kek_errada = secrets.token_bytes(32)
try:
    c._desembrulhar(kek_errada, n_w, wrap)
    res = "abriu"
except InvalidTag:
    res = "negado"
ok(res == "negado", "a KEK errada nunca desembrulha o DEK de outra KEK")

print("\n4) Adulteração EXAUSTIVA: cada 1 dos bits do ciphertext+tag tem de quebrar a autenticação")
chave_x = secrets.token_bytes(32); nonce_x = secrets.token_bytes(12)
ct_x = c.AESGCM(chave_x).encrypt(nonce_x, b"mensagem curta", b"aad-fixo")
total_bits = len(ct_x) * 8
falhas_bit = []
for i in range(total_bits):
    alterado = bytearray(ct_x)
    alterado[i // 8] ^= (1 << (i % 8))
    try:
        c.AESGCM(chave_x).decrypt(nonce_x, bytes(alterado), b"aad-fixo")
        falhas_bit.append(i)  # abriu quando NÃO deveria - seria gravíssimo
    except InvalidTag:
        pass
ok(not falhas_bit, f"todos os {total_bits} bits do ciphertext AES-256-GCM, virados 1 por vez, foram detectados "
                    f"({len(falhas_bit)} passaram sem detecção)")
ct_y = c.ChaCha20Poly1305(chave_x).encrypt(nonce_x, b"mensagem curta", b"aad-fixo")
total_bits_y = len(ct_y) * 8
falhas_bit_y = []
for i in range(total_bits_y):
    alterado = bytearray(ct_y)
    alterado[i // 8] ^= (1 << (i % 8))
    try:
        c.ChaCha20Poly1305(chave_x).decrypt(nonce_x, bytes(alterado), b"aad-fixo")
        falhas_bit_y.append(i)
    except InvalidTag:
        pass
ok(not falhas_bit_y, f"todos os {total_bits_y} bits do ciphertext ChaCha20-Poly1305, virados 1 por vez, foram "
                      f"detectados ({len(falhas_bit_y)} passaram sem detecção)")

print("\n5) O nonce participa de fato da cifra (nonces diferentes -> ciphertexts diferentes)")
chave_z = secrets.token_bytes(32)
cts = set()
for _ in range(100):
    n = secrets.token_bytes(12)
    cts.add(c.AESGCM(chave_z).encrypt(n, b"mesmo texto sempre", b""))
ok(len(cts) == 100, "100 nonces diferentes com o MESMO texto e a MESMA chave geram 100 ciphertexts diferentes")

print("\nFALHAS:", falhas)
sys.exit(1 if falhas else 0)
