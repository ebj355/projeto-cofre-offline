"""MENSAGENS DE ERRO DA CHAVE FIDO (sem precisar da chave física nem do Windows).

`_msg_fido()` traduz o erro do Windows/FIDO numa frase que diz o PRÓXIMO PASSO. Confere os casos que a chave real
produz, principalmente os de uma MÁQUINA/CHAVE LIMPA (chave nova, ainda sem PIN) e os de PIN com problema:
 - chave SEM PIN configurado -> orienta a criar o PIN (e não 'tente de novo');
 - PIN BLOQUEADO (erros demais) -> avisa que só desbloqueia redefinindo a chave (apaga as credenciais dela) e manda usar
   a segunda chave ou o código de recuperação; NÃO pode soar como 'PIN errado, tente de novo' (insistir bloqueia mais);
 - PIN errado, cancelou, tempo esgotado, chave que não é a cadastrada, recurso ausente e erro desconhecido;
 - nenhuma mensagem mostra o código técnico na frente, e nenhuma é vazia nem estoura erro."""
import importlib.util, os, re, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "6_ferramentas_dos_testes"))
import _resultado; _resultado.registrar(__file__)          # grava resultados/resultado_nucleo_fido_mensagens.txt

CAMINHO_PROG = os.path.abspath(os.path.join(AQUI, "..", "..", "cofre_senhas.py"))
spec = importlib.util.spec_from_file_location("c", CAMINHO_PROG)
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
FAL = []


def ok(cond, msg):
    """Imprime [OK]/[FALHOU] (o executor procura estes marcadores) e guarda as falhas."""
    print(("  [OK]   " if cond else "  [FALHOU] ") + msg, flush=True)
    if not cond:
        FAL.append(msg)


try:
    from fido2.client import ClientError
except ImportError:
    print("  (pulado) biblioteca fido2 não instalada neste Python: nada a conferir")
    print("\nTODOS OK")
    sys.exit(0)

ERR = ClientError.ERR


def msg(codigo, causa):
    """Mensagem para um ClientError com o código e a causa dados."""
    return c._msg_fido(ClientError(codigo, cause=causa if isinstance(causa, BaseException) else Exception(causa)))


print("== chave nova, sem PIN configurado")
for causa in ("CTAP2_ERR_PIN_NOT_SET", "PIN not set", "pin is not configured", "0x35 pin not set"):
    m = msg(ERR.OTHER_ERROR, causa)
    ok("não tem PIN" in m and "Crie um PIN" in m, f"'{causa}' -> orienta a CRIAR o PIN")
    ok("BLOQUEADO" not in m and "não confere" not in m, f"'{causa}' -> não confunde com PIN errado/bloqueado")

print("== PIN bloqueado")
for causa in ("CTAP2_ERR_PIN_BLOCKED", "PIN blocked", "PIN_AUTH_BLOCKED", "pin locked", "0x32 pin"):
    m = msg(ERR.OTHER_ERROR, causa)
    ok("BLOQUEADO" in m and "APAGA" in m and "recuperação" in m, f"'{causa}' -> avisa do bloqueio, do que apaga e do plano B")
    ok("tente de novo" not in m.lower(), f"'{causa}' -> NÃO manda tentar de novo (insistir só piora)")

print("== PIN errado")
for causa in ("CTAP2_ERR_PIN_INVALID", "incorrect pin", "wrong pin", "0x8010006b pin"):
    m = msg(ERR.OTHER_ERROR, causa)
    ok("PIN da chave não confere" in m, f"'{causa}' -> PIN errado")

print("== outros casos")
ok("cancelou" in msg(ERR.OTHER_ERROR, "operation cancelled by user").lower(), "usuário cancelou")
ok("cancelou" in msg(ERR.OTHER_ERROR, "0x800704c7").lower(), "cancelamento do Windows (0x800704c7)")
ok("a tempo" in msg(ERR.TIMEOUT, "x"), "tempo esgotado: manda tocar na chave")
ok("não é a cadastrada" in msg(ERR.DEVICE_INELIGIBLE, "x"), "chave que não é a deste cofre")
ok("recurso necessário" in msg(ERR.CONFIGURATION_UNSUPPORTED, "x"), "chave sem o recurso hmac-secret/PRF")
m = msg(ERR.BAD_REQUEST, "algo desconhecido")
ok("BAD_REQUEST" in m and not m.startswith("BAD_REQUEST"), "erro desconhecido: código técnico só entre parênteses, no fim")
m = c._msg_fido(OSError("dispositivo removido"))
ok("Encaixe a chave" in m and "OSError" in m, "erro que não é do FIDO: manda encaixar a chave")
m = c._msg_fido(ClientError(ERR.OTHER_ERROR))
ok(isinstance(m, str) and m.strip() != "", "ClientError sem causa: mensagem não vazia, sem erro")

print("== nenhuma mensagem começa com código técnico")
for codigo in ERR:
    for causa in ("", "pin not set", "pin blocked", "pin invalid", "cancelled"):
        m = msg(codigo, causa)
        if not isinstance(m, str) or not m.strip() or re.fullmatch(r'[A-Z_0-9]{3,}', m.split()[0]):
            ok(False, f"{codigo.name}/'{causa}': mensagem vazia ou começando com código ({m!r})")
ok(True, "varridas todas as combinações de código x causa")

print("\nFALHAS: " + str(FAL) if FAL else "\nTODOS OK")
sys.exit(1 if FAL else 0)
