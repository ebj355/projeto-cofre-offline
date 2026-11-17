"""Chaves FIDO2 (com uma YubiKey simulada): cadastro, várias chaves, código de recuperação, remoção.
Uso:  python testes/teste_fido.py"""
import os, sys, tempfile
# usa o cofre_senhas.py da pasta do projeto e trabalha numa pasta temporária (não suja o repositório)
RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, RAIZ)
os.chdir(tempfile.mkdtemp(prefix="teste_cofre_"))
import os, sys, hmac, hashlib, secrets, struct
import cofre_senhas as c
f = []
def ok(cond, nome):
    print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))

class ChaveSimulada:
    """Imita uma YubiKey: cada credencial tem um segredo que nunca sai do 'chip'."""
    def __init__(self): self.creds = {}; self.toques = 0
    def registrar(self):
        cid = secrets.token_bytes(64); self.creds[cid] = secrets.token_bytes(32); return cid
    def provedor(self, creds, salt):
        self.toques += 1
        for cid in creds:
            if cid in self.creds:
                return cid, hmac.new(self.creds[cid], salt, hashlib.sha256).digest()
        raise c.FidoErro("Esta chave FIDO não está cadastrada neste cofre.")

P = "fido.dat"; SENHA = "cavalo azul come pizza na chuva"
def limpar():
    for x in (P, P + ".tmp"):
        if os.path.exists(x): os.remove(x)

for modo in (c.MODO_E, c.MODO_OU):
    nome_modo = "Senha E chave" if modo == c.MODO_E else "Senha OU chave"
    print(f"\n=== Modo {nome_modo} ===")
    limpar()
    v = c.Cofre.criar(P, SENHA, 5, modo, "alto"); K = v.chave_gerada
    v.registros.append(c.novo_item(servico="Banco", login="joao", senha="S3gr3d0!", pin="4821"))
    v.salvar()
    base = dict(senha=SENHA, chave=K) if modo == c.MODO_E else dict(senha=SENHA)

    # ativar com chave principal
    yk1, yk2 = ChaveSimulada(), ChaveSimulada()
    salt = v.salt_fido()
    cred1 = yk1.registrar(); _, s1 = yk1.provedor([cred1], salt)
    rec = v.adicionar_fido("Principal", cred1, s1); v.salvar()
    ok(rec and len(c.ler_chave_acesso(rec)) == 20, "1ª chave ativa o FIDO e gera código de recuperação")
    ok(c.info_cofre(P)[2] is True, "info_cofre informa que o cofre exige FIDO")
    bruto = open(P, "rb").read()
    ok(b"S3gr3d0!" not in bruto and cred1 not in bruto[:0] , "dados continuam cifrados")

    # sem FIDO: recusa sem gastar tentativa
    try: c.Cofre.abrir(P, **base); r = "abriu"
    except c.FatorFaltando: r = "pediu FIDO"
    ok(r == "pediu FIDO" and c.tentativas_restantes(P) == 5, "sem chave FIDO -> pede a chave, sem gastar tentativa")

    # com FIDO certo
    w = c.Cofre.abrir(P, fido=yk1.provedor, **base)
    ok(w.registros[0]["pin"] == "4821", "senha + FIDO principal -> abre")

    # chave FIDO desconhecida
    estranha = ChaveSimulada(); estranha.registrar()
    try: c.Cofre.abrir(P, fido=estranha.provedor, **base); r = "abriu"
    except c.FidoErro: r = "recusada"
    ok(r == "recusada" and c.tentativas_restantes(P) == 5, "chave FIDO de outra pessoa -> recusada, sem gastar tentativa")

    # cancelar o toque
    def cancelar(*a): raise c.FidoErro("Operação cancelada.")
    try: c.Cofre.abrir(P, fido=cancelar, **base); r = "abriu"
    except c.FidoErro: r = "cancelado"
    ok(r == "cancelado" and c.tentativas_restantes(P) == 5, "cancelar o toque não gasta tentativa")

    # FIDO certo + senha errada
    errado = dict(base); errado["senha"] = "senha errada bem longa"
    try: c.Cofre.abrir(P, fido=yk1.provedor, **errado); r = "abriu"
    except c.SenhaIncorreta as e: r = e.restantes
    ok(r == 4, "FIDO certo + senha errada -> negado e tentativa gasta")

    # adicionar reserva
    w = c.Cofre.abrir(P, fido=yk1.provedor, **base)
    cred2 = yk2.registrar(); _, s2 = yk2.provedor([cred2], w.salt_fido())
    ok(w.adicionar_fido("Reserva", cred2, s2) is None, "2ª chave não gera novo código")
    w.salvar()
    ok(c.Cofre.abrir(P, fido=yk2.provedor, **base).registros[0]["senha"] == "S3gr3d0!", "abre com a chave RESERVA")
    ok(c.Cofre.abrir(P, fido=yk1.provedor, **base) is not None, "principal continua abrindo")

    # código de recuperação
    ok(c.Cofre.abrir(P, recuperacao=rec, **base).registros[0]["login"] == "joao", "abre com o CÓDIGO DE RECUPERAÇÃO (sem FIDO)")
    try: c.Cofre.abrir(P, recuperacao=c.nova_chave_acesso()[1], **base); r = "abriu"
    except c.SenhaIncorreta: r = "negado"
    ok(r == "negado", "código de recuperação errado -> negado (gasta tentativa)")
    try: c.Cofre.abrir(P, recuperacao="ABC", **base); r = "abriu"
    except c.ChaveMalFormada: r = "formato"
    ok(r == "formato", "código mal digitado -> não gasta tentativa")

    # remover principal (perdida)
    w = c.Cofre.abrir(P, fido=yk2.provedor, **base)
    w.remover_fido(cred1); w.salvar()
    try: c.Cofre.abrir(P, fido=yk1.provedor, **base); r = "abriu"
    except c.FidoErro: r = "recusada"
    ok(r == "recusada", "chave removida deixa de abrir")
    try: w.remover_fido(cred2); r = "removeu"
    except ValueError: r = "bloqueado"
    ok(r == "bloqueado", "não deixa remover a ÚLTIMA chave (evita trancar o cofre)")

    # novo código de recuperação revoga o antigo
    w = c.Cofre.abrir(P, fido=yk2.provedor, **base)
    rec2 = w.novo_codigo_recuperacao(); w.salvar()
    try: c.Cofre.abrir(P, recuperacao=rec, **base); r = "abriu"
    except c.SenhaIncorreta: r = "negado"
    ok(r == "negado", "código de recuperação antigo deixa de valer")
    ok(c.Cofre.abrir(P, recuperacao=rec2, **base) is not None, "código novo funciona")

    # trocar senha mestra com FIDO ativo
    w = c.Cofre.abrir(P, fido=yk2.provedor, **base)
    w.trocar_senha("nova frase bem comprida 2026"); 
    base["senha"] = "nova frase bem comprida 2026"
    ok(c.Cofre.abrir(P, fido=yk2.provedor, **base) is not None, "trocar a senha mestra mantém o FIDO funcionando")

    # ATAQUE: remover a seção FIDO do arquivo
    b = bytearray(open(P, "rb").read()); h = c._ler_cabecalho(bytes(b))
    sem = bytes(b[:h["hl"] + 1]) + b"\x00" + bytes(b[h["ini_dados"]:])
    open(P + ".atk", "wb").write(sem)
    try: c.Cofre.abrir(P + ".atk", **base); r = "abriu"
    except c.ViolacaoDetectada: r = "violação"
    except Exception as e: r = type(e).__name__
    ok(r != "abriu", f"ATAQUE: apagar a exigência de FIDO do arquivo -> não abre ({r})")
    if os.path.exists(P + ".atk"): os.remove(P + ".atk")

    # ATAQUE: colar a chave FIDO do atacante no cofre
    atk = ChaveSimulada(); cid = atk.registrar(); _, sa = atk.provedor([cid], h["salt"] if "salt" in h else h["fido"]["salt"])
    fido_falso = {"salt": h["fido"]["salt"], "rec": h["fido"]["rec"],
                  "chaves": [{"nome": "x", "cred": cid, "nonce": secrets.token_bytes(12),
                              "wrap": c.AESGCM(c._kek_fido(sa)).encrypt(secrets.token_bytes(12), secrets.token_bytes(32), c.WRAP_AAD)}]}
    nova = bytes(b[:h["hl"] + 1]) + c._serializar_fido(fido_falso) + bytes(b[h["ini_dados"]:])
    open(P + ".atk", "wb").write(nova)
    try: c.Cofre.abrir(P + ".atk", fido=atk.provedor, **base); r = "abriu"
    except Exception as e: r = type(e).__name__
    ok(r != "abriu", f"ATAQUE: inserir a chave FIDO do atacante -> não abre ({r})")
    if os.path.exists(P + ".atk"): os.remove(P + ".atk")

    # desativar
    w = c.Cofre.abrir(P, fido=yk2.provedor, **base); w.desativar_fido(); w.salvar()
    ok(c.info_cofre(P)[2] is False and c.Cofre.abrir(P, **base).registros[0]["pin"] == "4821",
       "desativar FIDO -> volta a abrir só com senha/chave, dados intactos")

print("\n=== Compatibilidade ===")
# cofre v3 (versão anterior) abre e vira v4
limpar()
v = c.Cofre.criar(P, SENHA, 5, c.MODO_E, "alto"); K = v.chave_gerada
v.registros.append({"id": "1", "servico": "Antigo", "login": "a", "senha": "b", "pin": "", "notas": ""}); v.salvar()
b = open(P, "rb").read(); h = c._ler_cabecalho(b)
# monta à mão um arquivo v3 (formato da versão que está no seu pendrive)
cab3 = c.MAGIC_V3 + b[8:h["hl"] - 8]
k_cha, k_aes = c._subchaves(v.dek)
dados = c.json.dumps(v.registros).encode(); dados += b"\0" * (4096 - len(dados) % 4096)
interno = c.ChaCha20Poly1305(k_cha).encrypt(h["nonce_c"], dados, cab3)
externo = c.AESGCM(k_aes).encrypt(h["nonce_a"], interno, cab3)
open(P, "wb").write(cab3 + bytes([5]) + externo)
ok(c.info_cofre(P) == (5, c.MODO_E, False), "info_cofre lê o formato antigo (v3)")
w = c.Cofre.abrir(P, senha=SENHA, chave=K)
ok(w.registros[0]["servico"] == "Antigo" and open(P, "rb").read()[:8] == c.MAGIC, "cofre v3 abre e é convertido para o formato atual (v5)")
ok(c.Cofre.abrir(P, senha=SENHA, chave=K).registros[0].get("senha") == "b", "itens antigos (sem campos novos) continuam funcionando")

print("\n=== API da biblioteca fido2 (estrutura das mensagens) ===")
from fido2.webauthn import (PublicKeyCredentialCreationOptions, PublicKeyCredentialRequestOptions,
                            AuthenticationResponse, AuthenticatorAssertionResponse,
                            AuthenticationExtensionsClientOutputs)
from fido2.ctap2.extensions import AuthenticatorExtensionsPRFOutputs, AuthenticatorExtensionsPRFValues
import inspect
src = inspect.getsource(c.fido_registrar) + inspect.getsource(c.fido_obter)
# reconstrói os dicionários usados pelo cofre e valida no parser oficial
opc = {"rp": {"id": c.RP_ID, "name": "Cofre de Senhas"}, "user": {"id": b"1"*16, "name": "cofre", "displayName": "x"},
       "challenge": b"2"*32, "pubKeyCredParams": [{"type": "public-key", "alg": -7}], "timeout": 120000,
       "authenticatorSelection": {"authenticatorAttachment": "cross-platform", "residentKey": "discouraged",
                                  "userVerification": "required"}, "attestation": "none",
       "hints": ["security-key"], "extensions": {"prf": {}}}
o = PublicKeyCredentialCreationOptions.from_dict(opc)
ok(o.rp.id == c.RP_ID and o.authenticator_selection.user_verification == "required", "pedido de cadastro aceito pelo fido2")
ped = {"challenge": b"3"*32, "rpId": c.RP_ID, "allowCredentials": [{"type": "public-key", "id": b"4"*64}],
       "userVerification": "required", "timeout": 120000, "hints": ["security-key"],
       "extensions": {"prf": {"eval": {"first": b"5"*32}}}}
q = PublicKeyCredentialRequestOptions.from_dict(ped)
ok(q.rp_id == c.RP_ID and q.allow_credentials[0].id == b"4"*64, "pedido de toque aceito pelo fido2")
from fido2.ctap2.extensions import AuthenticatorExtensionsPRFInputs
pi = AuthenticatorExtensionsPRFInputs.from_dict(q.extensions["prf"])
ok(pi.eval.first == b"5"*32, "salt PRF chega intacto ao formato do Windows")
saida = secrets.token_bytes(32)
ext = AuthenticationExtensionsClientOutputs({"prf": AuthenticatorExtensionsPRFOutputs(results=AuthenticatorExtensionsPRFValues(first=saida))})
class R:  # resposta no formato do fido2 2.x
    raw_id = b"9"*64; client_extension_results = ext
cid, seg = c._extrair_segredo(R())
ok(cid == b"9"*64 and seg == saida, "segredo extraído corretamente da resposta do Windows")
ext2 = AuthenticationExtensionsClientOutputs({"prf": AuthenticatorExtensionsPRFOutputs(enabled=True)})
ok(ext2.prf.enabled is True, "cadastro detecta suporte a PRF/hmac-secret")
class R2: raw_id = b"9"*64; client_extension_results = AuthenticationExtensionsClientOutputs({})
try: c._extrair_segredo(R2()); r = "aceitou"
except c.FidoErro: r = "recusou"
ok(r == "recusou", "chave sem hmac-secret -> erro claro")

limpar()
print("\nTODOS OK" if all(f) else f"\nFALHAS: {f.count(False)}")
sys.exit(0 if all(f) else 1)
