"""Transações do cofre: alteração dentro de 'with transacao()' grava; se a gravação falha (disco cheio) a alteração é desfeita."""
import sys, os, tempfile
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import cofre_senhas as c
d=tempfile.mkdtemp(); p=os.path.join(d,"c.dat")
v=c.Cofre.criar(p,"frase de teste bem longa 123",3,0,"alto")
v.registros.append({"id":"1","servico":"x","pessoa":"","grupo":"g"}); v.salvar()
v2=c.Cofre.abrir(p,senha="frase de teste bem longa 123")
assert v2.meta.get("schema")==1, v2.meta
# transacao: sucesso
with v2.transacao():
    v2.registros[0]["grupo"]="h"
assert c.Cofre.abrir(p,senha="frase de teste bem longa 123").registros[0]["grupo"]=="h"
# transacao: falha na gravação -> desfaz
orig=v2.salvar
def ruim(*a,**k): raise OSError("disco cheio")
v2.salvar=ruim
try:
    with v2.transacao():
        v2.registros[0]["grupo"]="z"; v2.meta["pessoas"]=["A"]
except OSError: pass
assert v2.registros[0]["grupo"]=="h" and "pessoas" not in v2.meta, (v2.registros, v2.meta)
print("transacao OK; schema OK")
c.destruir(p)
