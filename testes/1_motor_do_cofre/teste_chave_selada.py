"""Arquivo de chave de acesso SELADO (.key cifrado): só o cofre dono o decifra e o carrega; outro cofre, byte
alterado e texto puro antigo se comportam como esperado; a chave carregada realmente abre o cofre."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import cofre_senhas as c

falhas = 0
def ok(cond, nome):
    """Registra uma verificação."""
    global falhas
    print(("  [OK] " if cond else "  [FALHOU] ") + nome)
    falhas += 0 if cond else 1

d = tempfile.mkdtemp(); S = "Mestra-Selada-Aa1!-xyz"
p1, p2 = os.path.join(d, "a.dat"), os.path.join(d, "b.dat")
v1 = c.Cofre.criar(p1, S, 5, c.MODO_OU, "alto"); chave1 = v1.chave_gerada
v2 = c.Cofre.criar(p2, S, 5, c.MODO_OU, "alto"); chave2 = v2.chave_gerada
arq = c.selar_chave_acesso(chave1, v1.sal_k, v1.nonce_k, v1.wrap_k)
ok(c.arquivo_de_chave_e_selado(arq), "arquivo gerado é do formato selado")
ok(chave1.replace("-", "").encode() not in arq and c.ler_chave_acesso(chave1) not in arq, "a chave não aparece em claro no arquivo")
ok(c.chave_de_arquivo(p1, arq) == chave1, "o cofre dono decifra e devolve a mesma chave")
v1.fechar()
# a chave carregada abre o cofre (sem senha)
v = c.Cofre.abrir(p1, chave=c.chave_de_arquivo(p1, arq)); ok(v is not None, "a chave lida do arquivo abre o cofre"); v.fechar()
# outro cofre não consegue
try: c.chave_de_arquivo(p2, arq); ok(False, "outro cofre recusa o arquivo")
except c.ChaveMalFormada as e: ok("outro cofre" in str(e), "outro cofre recusa o arquivo, com mensagem clara")
# byte alterado em qualquer posição
alterou = 0
for i in range(len(arq)):
    ruim = bytearray(arq); ruim[i] ^= 0x01
    try: c.chave_de_arquivo(p1, bytes(ruim))
    except c.ChaveMalFormada: alterou += 1
    except Exception: pass
ok(alterou == len(arq), f"qualquer byte alterado é recusado ({alterou}/{len(arq)})")
try: c.chave_de_arquivo(p1, arq[:30]); ok(False, "arquivo cortado recusado")
except c.ChaveMalFormada: ok(True, "arquivo cortado é recusado")
# formato antigo (texto puro) continua carregando
ok(c.chave_de_arquivo(p1, (chave1 + "\n").encode()) == chave1, "arquivo .key antigo (texto) continua valendo")
# o arquivo de outro cofre também não passa pela chave errada: nada gastou tentativa (só leitura)
ok(c.tentativas_restantes(p1) == 5, "carregar o arquivo não gasta tentativa")
print("FALHAS:", falhas); sys.exit(1 if falhas else 0)
