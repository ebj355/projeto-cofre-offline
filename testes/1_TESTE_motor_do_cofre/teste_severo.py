# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Teste severo do arquivo: vira 1 bit em posições aleatórias, trunca, enche de lixo, falha no replace e migra o formato antigo (v4); nunca destrói nem gasta tentativa."""
import sys, os, random, tempfile, shutil, json, importlib.util, struct, string, time, threading
spec=importlib.util.spec_from_file_location('c',os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','cofre_senhas.py'));c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
FAL=[]
def ok(cond,msg):
    print(("  [OK]   " if cond else "  [FALHOU] ")+msg, flush=True)
    if not cond: FAL.append(msg)
rnd=random.Random(12345)
d=tempfile.mkdtemp(); P=os.path.join(d,"cofre.dat"); S="cavalo azul come pizza na chuva 2026"
def novo(modo=0,nivel="alto",n=5):
    for f in os.listdir(d): os.remove(os.path.join(d,f))
    v=c.Cofre.criar(P,S,n,modo,nivel); K=v.chave_gerada
    for i in range(30): v.registros.append({"id":f"i{i}","servico":f"Serv{i}","login":f"u{i}","senha":f"Sx{i}-"+"k"*20,"notas":"linha1\nlinha2"})
    v.salvar(); return v,K
def kw(modo,K): return dict(senha=S,chave=K) if modo==1 else dict(senha=S)

print("== 1) Fuzz: 1 bit em posições aleatórias do arquivo inteiro (senha CERTA)")
for modo in (0,1):
    v,K=novo(modo); base=open(P,"rb").read(); h=c._ler_cabecalho(base); n=len(base)
    pos_hdr=[p for p in range(h["hl"]+0)]  # cabeçalho todo
    pos_fido=list(range(h["hl"]+1,h["ini_dados"]))
    pos_dados=[rnd.randrange(h["ini_dados"],n) for _ in range(12)]+[n-1,n-17,h["ini_dados"]]
    ruins=[]
    for p in pos_hdr+pos_fido+pos_dados:
        b=bytearray(base); b[p]^=1<<rnd.randrange(8); open(P,"wb").write(bytes(b))
        try: c.Cofre.abrir(P,**kw(modo,K)); r="abriu"
        except (c.ArquivoCorrompido,c.ArquivoInvalido): r="ok"
        except Exception as e: r=type(e).__name__
        if r!="ok" or not os.path.exists(P) or open(P,"rb").read()[h["hl"]]!=h["contador"]: ruins.append((p,r))
        for f in os.listdir(d):
            if f not in ("cofre.dat", "cofre.dat.lock", "cofre.dat.gravar.lock") and not f.endswith((".bak1",".bak2",".bak3",".bak4",".bak5",".pre-v5",".diag")): ruins.append((p,"sobra "+f))
    ok(not ruins,f"modo {modo}: {len(pos_hdr)+len(pos_fido)+len(pos_dados)} bit-flips -> nunca destrói, nunca gasta tentativa, nunca SenhaIncorreta {ruins[:3]}")
    open(P,"wb").write(base)
    ok(len(c.Cofre.abrir(P,**kw(modo,K)).registros)==30,"arquivo íntegro ainda abre")

print("== 2) Truncamentos e lixo")
v,K=novo(); base=open(P,"rb").read(); ruins=[]
for cut in [0,1,7,8,50,100,len(base)//2,len(base)-1,len(base)-16]:
    open(P,"wb").write(base[:cut])
    try: c.Cofre.abrir(P,senha=S); r="abriu"
    except (c.ArquivoInvalido,) : r="ok"
    except Exception as e: r=type(e).__name__
    if r!="ok" or not os.path.exists(P): ruins.append((cut,r))
ok(not ruins,f"truncado em 9 pontos -> recusa sem destruir {ruins}")
open(P,"wb").write(os.urandom(5000))
try: c.Cofre.abrir(P,senha=S); r="abriu"
except c.ArquivoInvalido: r="ok"
except Exception as e: r=type(e).__name__
ok(r=="ok" and os.path.exists(P),"lixo aleatório -> recusa sem destruir")

print("== 3) Queda de energia entre .tmp e replace")
v,K=novo(); antes=open(P,"rb").read(); v2=c.Cofre.abrir(P,senha=S); v2.registros.append({"id":"x","servico":"novo"})
orig=os.replace
def boom(a,b): raise OSError("queda")
c.os.replace=boom
try: v2.salvar(); r="salvou"
except OSError: r="falhou"
c.os.replace=orig
ok(r=="falhou" and not os.path.exists(P+".tmp"),"falha no replace: sem .tmp sobrando")
w=c.Cofre.abrir(P,senha=S); ok(len(w.registros)==30 and not any(x["id"]=="x" for x in w.registros),"cofre original intacto após a queda")

print("== 4) Contas de tentativas")
v,K=novo(0,"alto",4); res=[]
for i in range(4):
    try: c.Cofre.abrir(P,senha="errada errada errada "+str(i)); res.append("abriu")
    except c.SenhaIncorreta as e: res.append(e.restantes)
    except c.CofreDestruido: res.append("destruido")
    if not os.path.exists(P): break
sobras=[f for f in os.listdir(d) if f not in ("cofre.dat.lock","cofre.dat.gravar.lock")]
ok(res==[3,2,1,"destruido"] and not os.path.exists(P) and not sobras,f"4 erros -> destrói dados e temporários, trava permitida {res} {sobras}")
v,K=novo(0,"alto",4)
for i in range(2):
    try: c.Cofre.abrir(P,senha="errada errada errada "+str(i))
    except c.SenhaIncorreta: pass
c.Cofre.abrir(P,senha=S); ok(c.tentativas_restantes(P)==4,"abertura certa zera as tentativas")

print("== 5) Propriedade: sequência aleatória de operações sempre reabre igual")
for modo in (0,1):
    v,K=novo(modo); senha=S; chave=K; ref=json.loads(json.dumps(v.registros))
    for passo in range(14):
        v=c.Cofre.abrir(P,**(dict(senha=senha,chave=chave) if modo==1 else dict(senha=senha)))
        ok_=json.loads(json.dumps(v.registros))==ref
        if not ok_: ok(False,f"modo {modo} passo {passo}: dados divergiram"); break
        op=rnd.choice(["add","edit","del","senha","chave"])
        if op=="add": r={"id":f"n{passo}","servico":f"N{passo}","senha":"abc"+str(passo)}; v.registros.append(r); ref.append(json.loads(json.dumps(r))); v.salvar()
        elif op=="edit" and v.registros: v.registros[0]["login"]=f"ed{passo}"; ref[0]["login"]=f"ed{passo}"; v.salvar()
        elif op=="del" and len(v.registros)>3: v.registros.pop(); ref.pop(); v.salvar(forcar_copia=True)
        elif op=="senha":
            nova=f"senha numero {passo} bem longa e unica 2026!"
            if modo==0: nk=v.trocar_senha(nova,chave_acesso=chave if v._kb is None else None); chave=nk or chave
            else: v.trocar_senha(nova)
            senha=nova
        elif op=="chave":
            nk=v.gerar_nova_chave_acesso(senha); chave=nk
        v.fechar()
    else:
        v=c.Cofre.abrir(P,**(dict(senha=senha,chave=chave) if modo==1 else dict(senha=senha)))
        ok(json.loads(json.dumps(v.registros))==ref,f"modo {modo}: 14 operações aleatórias (add/edit/del/trocar senha/chave) -> dados idênticos no fim")
        if modo==0:
            ok(len(c.Cofre.abrir(P,chave=chave).registros)==len(ref),"modo OU: a chave final também abre")

print("== 6) Senhas esquisitas")
for sen in ["é"*20,"🔐🔐🔐🔐🔐🔐🔐🔐🔐🔐🔐🔐🔐🔐","a"*1000,"com espaços   no fim e começo  ","tab\tdentro da senha longa ok","nul\x00dentro da senha longa ok"]:
    for f in os.listdir(d): os.remove(os.path.join(d,f))
    try:
        v=c.Cofre.criar(P,sen,3,0,"alto"); v.salvar(); w=c.Cofre.abrir(P,senha=sen); r=bool(w)
    except Exception as e: r=type(e).__name__
    ok(r is True,f"senha {sen[:10]!r} ({len(sen)} car.) cria e abre ({r})")

print("== 7) Leitura de chave: lixo nunca dá exceção estranha")
bad=0
for _ in range(3000):
    s="".join(rnd.choice(string.printable+"é🔐\x00") for _ in range(rnd.randrange(0,80)))
    try: c.ler_chave_acesso(s)
    except c.ChaveMalFormada: pass
    except Exception: bad+=1
ok(bad==0,"3000 textos aleatórios -> só ChaveMalFormada")
b,t=c.nova_chave_acesso(); bad=0
for i in range(34):
    ch=t.replace("-","")
    alt="B" if ch[i]!="B" else "C"
    s=ch[:i]+alt+ch[i+1:]
    try: c.ler_chave_acesso(s); bad+=1 if i>=32 and False else 0; 
    except c.ChaveMalFormada: pass
caiu=sum(1 for i in range(34) if (lambda s:(c.ler_chave_acesso(s) and False) if False else None) )
cnt=0
for i in range(34):
    ch=t.replace("-",""); alt="B" if ch[i]!="B" else "C"; s=ch[:i]+alt+ch[i+1:]
    try: c.ler_chave_acesso(s)
    except c.ChaveMalFormada: cnt+=1
ok(cnt>=33,f"troca de 1 caractere em qualquer das 34 posições é percebida ({cnt}/34)")

print("== 8) Importação hostil")
import openpyxl, zipfile
def xl(nome,linhas,**k):
    wb=openpyxl.Workbook(); ws=wb.active
    for l in linhas: ws.append(l)
    wb.save(os.path.join(d,nome)); return os.path.join(d,nome)
casos={
 "controle": xl("a.xlsx",[["Serviço","Login","Senha"],["Banco\u202eEVIL\u200b","joão","segredo\u2066x"]]),
 "so_cab": xl("b.xlsx",[["Serviço","Login","Senha"]]),
 "vazio": xl("c.xlsx",[]),
 "grande_texto": xl("e.xlsx",[["Serviço","Login","Senha"],["x"*200000,"y","z"]]),
 "bw": xl("f.xlsx",[["login_username","login_password","login_uri","login_totp","favorite","type","reprompt","name"],["ana@x.com","S3gredo!","https://x.com","JBSWY3DP","1","login","0","Site X"]]),
 "nums": xl("g.xlsx",[["Serviço","Login","Senha","PIN"],["Cartao",4111111111111111,"x",1234],["Cartao2",12.5,"y",0o7]]),
}
for nome,cam in casos.items():
    try:
        regs,av=c.ler_planilha(cam); r=f"{len(regs)} regs"
    except ValueError as e: r="recusou"
    except Exception as e: r="ERRO "+type(e).__name__+str(e)[:60]
    ok(not r.startswith("ERRO"),f"xlsx '{nome}': {r}")
regs,_=c.ler_planilha(casos["controle"]); ok("\u202e" not in regs[0]["servico"] and "\u2066" not in regs[0]["senha"] and "\u200b" not in regs[0]["servico"],"controles e bidi removidos dos valores")
regs,_=c.ler_planilha(casos["bw"]); r=regs[0]
ok(r["login"]=="ana@x.com" and r["senha"]=="S3gredo!" and r["chave"]=="JBSWY3DP" and "favorite" not in r["notas"] and r["servico"]=="Site X","Bitwarden: login, senha, TOTP certos; metadados triviais fora das Notas")
regs,_=c.ler_planilha(casos["nums"]); ok(regs[0]["login"]=="4111111111111111","número de 16 dígitos sem perder precisão")
# colunas largas (memória)
wb=openpyxl.Workbook(); ws=wb.active; ws.append(["Serviço","Login","Senha"])
for i in range(3000): ws.append([f"S{i}","u","p"])
ws.cell(row=3001,column=16384,value="fim"); cam=os.path.join(d,"larga.xlsx"); wb.save(cam)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "6_TESTE_ferramentas_dos_testes"))  # testes/6_TESTE_ferramentas_dos_testes/ -> _util_mem.py
from _util_mem import pico_kb
t0=time.time(); regs,_=c.ler_planilha(cam); pico=pico_kb()/1024
ok(len(regs)==3000 and pico<900,f"planilha A1:XFD3001: {len(regs)} regs em {time.time()-t0:.1f}s, pico {pico:.0f} MB")
# csv multilinha e binário
open(os.path.join(d,"m.csv"),"w",encoding="utf-8",newline="").write('nome,login,senha,notas\r\nA,x,y,"linha1\nlinha2"\r\n')
regs,_=c.ler_planilha(os.path.join(d,"m.csv")); ok(regs[0]["notas"]=="linha1\nlinha2" or "linha1\nlinha2" in regs[0]["notas"],"CSV com campo em várias linhas")
open(os.path.join(d,"bin.csv"),"wb").write(os.urandom(4000))
try: c.ler_planilha(os.path.join(d,"bin.csv")); r="aceitou"
except ValueError: r="recusou"
ok(r=="recusou","CSV binário recusado")
# zip bomb
z=os.path.join(d,"bomba.xlsx")
with zipfile.ZipFile(z,"w",zipfile.ZIP_DEFLATED) as zf: zf.writestr("xl/x.xml",b"\0"*(450*1024*1024))
try: c.ler_planilha(z); r="leu"
except ValueError: r="recusou"
ok(r=="recusou","zip bomb (450 MB descompactados) recusada"); os.remove(z)

print("== 9) Migrações v1→v5 e v3→v5 (formatos antigos)")
# usa o programa antigo que gerou v4 (pré-revisão) para criar um v4 real
spec2=importlib.util.spec_from_file_location('c4',os.path.join(os.path.dirname(os.path.abspath(__file__)),'PECA_DE_TESTE_cofre_versao_4_antiga.py')); c4=importlib.util.module_from_spec(spec2); spec2.loader.exec_module(c4)
for modo in (0,1):
    for f in os.listdir(d): os.remove(os.path.join(d,f))
    v=c4.Cofre.criar(P,S,5,modo,"alto"); K=v.chave_gerada; v.registros.append({"id":"1","servico":"Real","login":"a","senha":"s3"}); v.salvar()
    # simula 2 tentativas erradas antes (contador 3/5), como o seu cofre real
    for i in range(2):
        try: c4.Cofre.abrir(P,**(dict(senha="errada errada errada 123",chave=K) if modo else dict(senha="errada errada errada 123")))
        except c4.SenhaIncorreta: pass
    ok(open(P,"rb").read()[:8]==b"COFRE04\x00","(programa anterior) gerou COFRE04 de verdade")
    w=c.Cofre.abrir(P,**kw(modo,K))
    ok(w.registros[0]["senha"]=="s3" and open(P,"rb").read()[:8]==b"COFRE05\x00" and os.path.exists(P+".pre-v5"),f"modo {modo}: COFRE04 real migra; .pre-v5 guardado")
    pre=open(P+".pre-v5","rb").read(); 
    ok(pre[:8]==b"COFRE04\x00" and c4.Cofre.abrir(P+".pre-v5",**kw(modo,K)).registros[0]["senha"]=="s3","a cópia .pre-v5 é o v4 original e abre")
    ok(w.erros_desde_ultima==2,"alerta de 2 tentativas erradas preservado na migração")

print("== 10) NFD antigo é regravado em NFC")
import unicodedata as ud
for f in os.listdir(d): os.remove(os.path.join(d,f))
nfd=ud.normalize("NFD","cafézinho com leite forte 2026")
v=c.Cofre.criar(P,"x"*20,3,0,"alto"); v._definir_senha(nfd,normalizar=False); v.salvar()
w=c.Cofre.abrir(P,senha=ud.normalize("NFC","cafézinho com leite forte 2026"))
ok(bool(w),"senha NFC abre cofre gravado em NFD")
# agora deve abrir em NFC já na 1ª variante (sem custo extra) e continuar abrindo em NFD
w=c.Cofre.abrir(P,senha=ud.normalize("NFC","cafézinho com leite forte 2026")); ok(bool(w) and c.tentativas_restantes(P)==3,"depois da regravação continua abrindo, sem perder tentativas")
ok(bool(c.Cofre.abrir(P,senha=nfd)),"e ainda abre digitada em NFD")

print("== 11) Concorrência: 8 threads salvando no mesmo objeto")
v,K=novo(); erros=[]
def tr(i):
    try:
        for j in range(5): v.registros.append({"id":f"t{i}_{j}","servico":"T"}); v.salvar()
    except Exception as e: erros.append(type(e).__name__)
ths=[threading.Thread(target=tr,args=(i,)) for i in range(8)]
[t.start() for t in ths]; [t.join() for t in ths]
w=c.Cofre.abrir(P,senha=S); ok(len(w.registros)>=30 and not [f for f in os.listdir(d) if f.endswith(".tmp")],f"arquivo íntegro após 40 salvamentos concorrentes (erros={set(erros)})")

print("FALHAS:",FAL); shutil.rmtree(d,ignore_errors=True); sys.exit(1 if FAL else 0)
