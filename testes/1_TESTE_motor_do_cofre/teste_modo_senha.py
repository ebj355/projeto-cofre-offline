"""Núcleo: modo 'só senha mestra' (MODO_S) e aviso inicial que aparece uma única vez."""
import os, sys, tempfile
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
import cofre_senhas as c
f = []
def ok(cond, nome): print(("  [OK]   " if cond else "  [FALHOU] ") + nome); f.append(bool(cond))
W = tempfile.mkdtemp(prefix="cofre_ms_"); P = os.path.join(W, "s.dat")
SENHA = "cavalo azul come pizza na chuva"

v = c.Cofre.criar(P, SENHA, 3, c.MODO_S, "alto")
ok(v.chave_gerada is None, "modo só-senha não gera chave de acesso")
v.registros.append(c.novo_item(servico="Banco", login="a@b.com", senha="Seg-123!x")); v.salvar()
rest, modo, fido = c.info_cofre(P)
ok(modo == c.MODO_S and not fido and rest == 3, "info_cofre informa MODO_S")
a = c.Cofre.abrir(P, senha=SENHA)
ok(a.modo == c.MODO_S and a.registros[0]["servico"] == "Banco", "abre só com a senha e traz os itens")
a.fechar()
try:
    c.Cofre.abrir(P); ok(False, "sem senha deve recusar")
except c.FatorFaltando:
    ok(True, "sem senha: pede a senha (FatorFaltando) sem gastar tentativa")
ok(c.info_cofre(P)[0] == 3, "tentativa não foi gasta ao esquecer a senha")
try:
    c.Cofre.abrir(P, chave="AAAA-BBBB-CCCC"); ok(False, "só chave não abre")
except c.FatorFaltando:
    ok(True, "chave sozinha não abre o cofre só-senha")
try:
    c.Cofre.abrir(P, senha="errada errada errada errada"); ok(False, "senha errada")
except c.SenhaIncorreta as ex:
    ok(ex.restantes == 2, "senha errada gasta 1 tentativa (restam 2)")
b = c.Cofre.abrir(P, senha=SENHA, chave="qualquer-coisa-ignorada")
ok(b.registros and c.info_cofre(P)[0] == 3, "chave extra é ignorada e acerto devolve o contador")
try:
    b.gerar_nova_chave_acesso(SENHA); ok(False, "não existe chave de acesso")
except ValueError:
    ok(True, "gerar chave de acesso é recusado no modo só-senha")
b.trocar_senha("outra senha bem comprida e unica 987")
b.fechar()
d = c.Cofre.abrir(P, senha="outra senha bem comprida e unica 987")
ok(d.registros[0]["login"] == "a@b.com", "troca de senha funciona no modo só-senha")
ok(d.confere_senha("outra senha bem comprida e unica 987") and not d.confere_senha(SENHA), "confere_senha")
d.fechar()
# modo consulta
q = c.Cofre.abrir(P, senha="outra senha bem comprida e unica 987", consulta=True)
ok(q.somente_leitura and q.registros, "modo consulta abre o cofre só-senha")
q.fechar()
# os outros modos continuam intactos
for modo in (c.MODO_E, c.MODO_OU):
    p2 = os.path.join(W, f"m{modo}.dat"); x = c.Cofre.criar(p2, SENHA, 3, modo, "alto")
    ok(x.chave_gerada is not None and c.info_cofre(p2)[1] == modo, f"modo {modo} ainda gera chave de acesso")
    x.fechar()

# aviso inicial: uma vez só
pasta = tempfile.mkdtemp(prefix="cofre_av_")
txt = "Este pendrive está em FAT32, aviso de teste"
ok(not c.aviso_ja_visto(txt, pasta), "aviso novo ainda não foi visto")
c.marcar_aviso_visto(txt, pasta)
ok(c.aviso_ja_visto(txt, pasta), "depois de mostrado, não aparece de novo")
ok(not c.aviso_ja_visto(txt + " diferente", pasta), "outro aviso continua aparecendo")
c.marcar_aviso_visto(txt, pasta)
import json
ok(len(json.load(open(os.path.join(pasta, c.NOME_AVISOS_VISTOS)))["vistos"]) == 1, "marcar duas vezes não duplica")
ok(not c.aviso_ja_visto(txt, os.path.join(pasta, "nao_existe")), "falha de leitura = avisa (na dúvida)")
print("PASSOU" if all(f) else "FALHOU", sum(f), "/", len(f))
sys.exit(0 if all(f) else 1)
