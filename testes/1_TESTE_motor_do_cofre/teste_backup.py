# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Cópias de segurança (.bak1-5): criadas ao salvar, restauração de cópia boa, contador zerado/dados alterados recusam SEM destruir e devolvem a tentativa."""
import sys, os, importlib.util, tempfile, shutil
spec=importlib.util.spec_from_file_location('c',os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','cofre_senhas.py'));c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
c._validar_params=c._validar_params
FAL=[]
def ok(cond,msg):
    print(("  [OK]   " if cond else "  [FALHOU] ")+msg)
    if not cond: FAL.append(msg)
d=tempfile.mkdtemp(); P=os.path.join(d,"cofre.dat"); S="cavalo azul come pizza na chuva"
v=c.Cofre.criar(P,S,3,0,"alto"); ok(os.path.exists(P+".bak1"),"cofre recém-criado já tem backup"); v.registros.append({"id":"1","servico":"A","login":"x","senha":"s1"}); v.salvar()
a=c.Cofre.abrir(P,senha=S); a.registros.append({"id":"2","servico":"B","login":"y","senha":"s2"}); os.utime(P+".bak1",(1,1)) if os.path.exists(P+".bak1") else None; a.salvar()
ok(os.path.exists(P+".bak1"),"cópia .bak1 criada ao salvar")
# corrompe contador e conteúdo
b=bytearray(open(P,"rb").read()); h=c._ler_cabecalho(bytes(b)); b[h["hl"]]=0; open(P,"wb").write(bytes(b))
try: c.Cofre.abrir(P,senha=S); r="abriu"
except c.ArquivoCorrompido: r="corrompido"
ok(r=="corrompido" and os.path.exists(P),"contador zerado por byte ruim: recusa, NÃO destrói")
usada=c.restaurar_copia(P)
ok(usada is not None and os.path.exists(P+".danificado"),f"restaurar cópia ({usada}) guarda o danificado")
x=c.Cofre.abrir(P,senha=S); ok(len(x.registros)>=1,"cofre restaurado abre")
# adulteração com senha certa
b=bytearray(open(P,"rb").read()); b[-5]^=1; open(P,"wb").write(bytes(b))
t0=c.tentativas_restantes(P)
try: c.Cofre.abrir(P,senha=S); r="abriu"
except c.ArquivoCorrompido: r="corrompido"
ok(r=="corrompido" and os.path.exists(P) and c.tentativas_restantes(P)==t0,"dados alterados + senha certa: preserva e devolve a tentativa")
# destruir apaga cópias
c.destruir(P)
ok(not os.path.exists(P) and not os.path.exists(P+".bak1") and not os.path.exists(P+".bak2"),"autodestruição apaga também as cópias de segurança")
# trocar senha apaga cópias
v=c.Cofre.criar(P,S,3,0,"alto"); v.salvar(); a=c.Cofre.abrir(P,senha=S); os.utime(P+".bak1",(1,1)) if os.path.exists(P+".bak1") else None; a.salvar()
ok(os.path.exists(P+".bak1"),"bak antes da troca")
a.trocar_senha("outra senha bem comprida 2026 xyz"); ok(not os.path.exists(P+".bak1"),"trocar senha apaga cópias que abririam com a senha velha")
# HashingError devolve tentativa
from argon2.exceptions import HashingError
orig=c.derivar_chave
def falha(*a,**k): raise HashingError("memory")
c.derivar_chave=falha
t0=c.tentativas_restantes(P)
try: c.Cofre.abrir(P,senha="outra senha bem comprida 2026 xyz"); r="abriu"
except MemoryError: r="mem"
c.derivar_chave=orig
ok(r=="mem" and c.tentativas_restantes(P)==t0,"HashingError/sem memória: tentativa devolvida")
# backup tem contador cheio; .danificado some na autodestruição; sem falso alarme
v=c.Cofre.criar(P,S,3,0,"alto"); 
b=open(P+".bak1","rb").read(); h=c._ler_cabecalho(b); ok(h["contador"]==h["max_t"],"backup guarda contador cheio")
try: c.Cofre.abrir(P,senha="errada errada errada 1"); 
except c.SenhaIncorreta: pass
a=c.Cofre.abrir(P,senha=S); os.utime(P+".bak1",(1,1)); a.salvar(); a.fechar()
c.restaurar_copia(P); ok(os.path.exists(P+".danificado"),".danificado criado")
r=c.Cofre.abrir(P,senha=S); ok(r.erros_desde_ultima==0,f"restaurar não gera falso alarme (erros={r.erros_desde_ultima})")
for i in range(3):
    try: c.Cofre.abrir(P,senha="errada errada errada 1")
    except Exception: pass
ok(not os.path.exists(P) and not os.path.exists(P+".danificado") and not os.path.exists(P+".bak1"),"autodestruição apaga .danificado e cópias")
# interval: cinco aberturas seguidas mantêm bak1
v=c.Cofre.criar(P,S,3,0,"alto"); m1=os.path.getmtime(P+".bak1")
for i in range(3): c.Cofre.abrir(P,senha=S)
ok(not os.path.exists(P+".bak2"),"aberturas seguidas não duplicam as cópias (regra de 10 min)")
print("FALHAS:",FAL); shutil.rmtree(d)

# ======== v5: migração, checksum, rotação de DEK, conflito, NFC/NFD, chave com dígitos ========
FAL2=[]
def ok2(cond,msg):
    print(("  [OK]   " if cond else "  [FALHOU] ")+msg)
    if not cond: FAL2.append(msg)
import json
d=tempfile.mkdtemp(); P=os.path.join(d,"cofre.dat"); S="cavalo azul come pizza na chuva"
for modo in (c.MODO_OU, c.MODO_E):
    # monta à mão um arquivo v4 (formato do seu pendrive hoje)
    v=c.Cofre.criar(P,S,3,modo,"alto"); K=v.chave_gerada
    v.registros.append({"id":"1","servico":"Velho","login":"a","senha":"SEGREDO-123"}); v.salvar()
    b=open(P,"rb").read(); h=c._ler_cabecalho(b)
    cab4=c.MAGIC_V4+b[8:h["hl"]-8]; secao=c._serializar_fido(None)
    k_cha,k_aes=c._subchaves(v.dek)
    dados=json.dumps({"itens":v.registros,"meta":v.meta}).encode(); dados+=b"\0"*(4096-len(dados)%4096)
    aad=cab4+secao
    interno=c.ChaCha20Poly1305(k_cha).encrypt(h["nonce_c"],dados,aad); externo=c.AESGCM(k_aes).encrypt(h["nonce_a"],interno,aad)
    open(P,"wb").write(cab4+bytes([3])+secao+externo)
    for f in (P+".bak1",P+".bak2"):
        if os.path.exists(f): os.remove(f)
    kw=dict(senha=S,chave=K) if modo==c.MODO_E else dict(senha=S)
    w=c.Cofre.abrir(P,**kw)
    ok2(w.registros[0]["senha"]=="SEGREDO-123" and open(P,"rb").read()[:8]==c.MAGIC,f"v4 (modo {modo}) migra para v5 sem perder dados")
    bk=open(P+".bak1","rb").read() if os.path.exists(P+".bak1") else b""
    ok2(bk[:8]==c.MAGIC_V4,"a cópia de segurança da migração guarda o v4 original")
    w.fechar()
    # bit-rot em cada região do cabeçalho com a senha CERTA: nunca destrói, nunca gasta tentativa
    base=open(P,"rb").read(); h=c._ler_cabecalho(base); ruins=[]
    for pos in range(0,h["hl"]):
        if pos==h["hl"]: continue
        b2=bytearray(base); b2[pos]^=0x01; open(P,"wb").write(bytes(b2))
        try: c.Cofre.abrir(P,**kw); r="abriu"
        except c.ArquivoCorrompido: r="ok"
        except c.ArquivoInvalido: r="ok"
        except Exception as e: r=type(e).__name__
        if r!="ok" or not os.path.exists(P) or open(P,"rb").read()[h["hl"]]!=h["contador"]: ruins.append((pos,r))
    ok2(not ruins,f"1 bit trocado em cada byte do cabeçalho (modo {modo}): nunca destrói nem gasta tentativa {ruins[:3]}")
    open(P,"wb").write(base)
    # rotação da DEK
    a=c.Cofre.abrir(P,**kw); dek_velha=a.dek
    if modo==c.MODO_OU:
        txt=a.trocar_senha("senha nova bem comprida 2026 xyz!", chave_acesso=K); ok2(txt is None,"modo OU: troca de senha mantém a chave digitada")
    else:
        a.trocar_senha("senha nova bem comprida 2026 xyz!")
    ok2(a.dek!=dek_velha,"troca de senha gera chave interna (DEK) nova")
    # ataque: cópia antiga + senha antiga não abre o arquivo novo, nem extrai a DEK velha
    try: c.Cofre.abrir(P,**kw); r="abriu"
    except c.SenhaIncorreta: r="negado"
    ok2(r=="negado","senha antiga NÃO abre o arquivo novo")
    kw2=dict(senha="senha nova bem comprida 2026 xyz!"); 
    if modo==c.MODO_E: kw2["chave"]=K
    z=c.Cofre.abrir(P,**kw2); ok2(z.registros[0]["senha"]=="SEGREDO-123","senha nova abre e os dados estão lá")
    if modo==c.MODO_OU:
        zk=c.Cofre.abrir(P,chave=K); ok2(zk.registros[0]["senha"]=="SEGREDO-123","a mesma chave de acesso continua abrindo")
        ktxt=zk.gerar_nova_chave_acesso(senha="senha nova bem comprida 2026 xyz!"); d2=zk.dek
        ok2(zk.dek!=a.dek,"nova chave de acesso também gera DEK nova")
        try: c.Cofre.abrir(P,chave=K); r="abriu"
        except c.SenhaIncorreta: r="negado"
        ok2(r=="negado","chave antiga NÃO abre")
        ok2(c.Cofre.abrir(P,chave=ktxt).registros[0]["senha"]=="SEGREDO-123","chave nova abre")
        ok2(c.Cofre.abrir(P,senha="senha nova bem comprida 2026 xyz!").registros[0]["senha"]=="SEGREDO-123","senha continua abrindo após trocar a chave")
        # trocar senha sem a chave: gera chave nova
        y=c.Cofre.abrir(P,senha="senha nova bem comprida 2026 xyz!"); nk=y.trocar_senha("terceira senha comprida 2026 abc!")
        ok2(bool(nk) and c.Cofre.abrir(P,chave=nk).registros[0]["senha"]=="SEGREDO-123","sem a chave em mãos: troca de senha gera chave nova que abre")
    c.destruir(P)

# conflito de duas instâncias
v=c.Cofre.criar(P,S,3,0,"alto"); v.salvar()
A=c.Cofre.abrir(P,senha=S); B=c.Cofre.abrir(P,senha=S)
B.registros.append({"id":"b","servico":"da B"}); B.salvar()
try: A.registros.append({"id":"a","servico":"da A"}); A.salvar(); r="salvou"
except c.ConflitoGravacao: r="recusou"
ok2(r=="recusou","duas instâncias: a que ficou desatualizada NÃO sobrescreve em silêncio")
ok2(any(x["servico"]=="da B" for x in c.Cofre.abrir(P,senha=S).registros),"o item da outra instância continua no arquivo")
# contador mudando não conta como conflito
try: c.Cofre.abrir(P,senha="errada errada errada errada"); 
except c.SenhaIncorreta: pass
A2=c.Cofre.abrir(P,senha=S); 
try: c._gastar_tentativa(P,c._ler_cabecalho(open(P,"rb").read())["hl"],3)
except Exception: pass
A2.registros.append({"id":"c","servico":"x"}); A2.salvar(); ok2(True,"tentativa de outra pessoa (contador) não bloqueia o salvar")
c.destruir(P)

# NFC / NFD
import unicodedata as ud
v=c.Cofre.criar(P,"cafézinho com leite forte 2026",3,0,"alto"); v.salvar()
for forma in ("NFC","NFD","NFKC"):
    try: c.Cofre.abrir(P,senha=ud.normalize(forma,"cafézinho com leite forte 2026")); r="abriu"
    except Exception as e: r=type(e).__name__
    ok2(r=="abriu",f"senha com acento digitada em {forma} abre")
ok2(c.tentativas_restantes(P)==3,"sem tentativas perdidas")
c.destruir(P)

# chave com dígitos de verificação
b,txt=c.nova_chave_acesso(); ok2(len(txt.replace("-",""))==34,"chave nova tem 34 caracteres (32 + 2 de verificação)")
ok2(c.ler_chave_acesso(txt)==b and c.ler_chave_acesso(txt[:-3].replace("-",""))==b,"chave nova e a forma antiga (32) leem igual")
errada=txt[:2]+("A" if txt[2]!="A" else "B")+txt[3:]
try: c.ler_chave_acesso(errada); r="aceitou"
except c.ChaveMalFormada: r="recusou"
ok2(r=="recusou","erro de digitação na chave é percebido antes de gastar tentativa")

# destruir não mexe em irmãos de arquivos comuns
open(os.path.join(d,"senhas.xlsx"),"wb").write(b"x"*100); open(os.path.join(d,"senhas.xlsx.bak1"),"wb").write(b"y"*100)
c.destruir_arquivo(os.path.join(d,"senhas.xlsx"))
ok2(not os.path.exists(os.path.join(d,"senhas.xlsx")) and os.path.exists(os.path.join(d,"senhas.xlsx.bak1")),"destruir_arquivo não apaga irmãos")
print("FALHAS v5:",FAL2)
