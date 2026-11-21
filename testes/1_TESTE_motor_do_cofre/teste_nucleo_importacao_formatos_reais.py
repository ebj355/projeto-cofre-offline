#!/usr/bin/env python3
# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Importação com arquivos no formato REAL de outros programas (lacuna "importação de exportações reais").

Os testes teste_importacao.py e teste_fuzz_importacao.py usam dados gerados pelo próprio projeto. Aqui os arquivos
seguem o layout documentado de cada origem, com dados fictícios: Chrome/Edge (com e sem a coluna 'note'), Firefox,
Bitwarden, LastPass, 1Password, KeePassXC, CSV do Excel em português (';' e cp1252), CSV UTF-8 com BOM, TSV, linha
'sep=;' do Excel e planilhas .xlsx no estilo Excel/LibreOffice. O critério principal é o de um cofre de senhas:

    NENHUMA senha pode ser alterada, cortada ou perdida em silêncio na importação.

A importação usa ler_planilha(..., exigir_selo=False), o caminho de quem recompila com
IMPORTAR_SOMENTE_COM_SELO = False para aceitar arquivos do Chrome/Samsung Pass (README, seção de importação).
Não toca no cofre real: tudo acontece em pasta temporária.
"""
import csv
import io
import os
import random
import shutil
import sys
import tempfile

FALHAS = []


def ok(cond, msg):
    print(("  [OK]   " if cond else "  [FALHOU] ") + msg)
    if not cond:
        FALHAS.append(msg)


def info(msg):
    print("  [INFO] " + msg)


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

TMP = tempfile.mkdtemp(prefix="arca_import_real_")
_n = [0]


def gravar(nome, dados):
    _n[0] += 1
    pasta = os.path.join(TMP, str(_n[0]))
    os.makedirs(pasta)
    caminho = os.path.join(pasta, nome)
    with open(caminho, "wb") as f:
        f.write(dados)
    return caminho


def ler(caminho):
    try:
        regs, avisos = cs.ler_planilha(caminho, exigir_selo=False)
        return {r["servico"]: r for r in regs}, regs, avisos
    except Exception as ex:      # noqa: BLE001
        return None, [], [f"{type(ex).__name__}: {ex}"]


def conferir(rotulo, caminho, esperado, notas_contem=None):
    """esperado: lista de (servico, login, senha). Confere contagem, login e senha EXATOS de cada linha."""
    por_nome, regs, avisos = ler(caminho)
    if por_nome is None:
        ok(False, f"{rotulo}: a leitura falhou ({avisos[0][:90]})")
        return regs
    ok(len(regs) == len(esperado), f"{rotulo}: {len(esperado)} contas lidas (leu {len(regs)})")
    for serv, login, senha in esperado:
        r = por_nome.get(serv)
        if r is None:
            ok(False, f"{rotulo}: conta '{serv}' sumiu")
            continue
        ok(r["senha"] == senha, f"{rotulo}: senha de '{serv}' idêntica ({senha!r}; leu {r['senha']!r})")
        ok(r["login"] == login, f"{rotulo}: login de '{serv}' = {login!r}")
    for serv, trecho in (notas_contem or []):
        ok(serv in por_nome and trecho in por_nome[serv].get("notas", ""),
           f"{rotulo}: '{serv}' guarda {trecho!r} nas notas (nenhum dado sai da planilha)")
    return regs


try:
    print("1) Exportações de gerenciadores (layout documentado de cada um, dados fictícios)")
    chrome = ('name,url,username,password,note\n'
              'Banco Exemplo,https://banco.exemplo.com.br/login,ana@exemplo.com,"S3nha;com,virgula""e aspas",Conta principal\n'
              'Gmail,https://accounts.google.com/,ana@exemplo.com,Outra-Senha-123,"linha1\nlinha2"\n'
              'Café São João,https://cafe.exemplo/,jose,pão-de-açúcar,\n')
    esp_chrome = [("Banco Exemplo", "ana@exemplo.com", 'S3nha;com,virgula"e aspas'),
                  ("Gmail", "ana@exemplo.com", "Outra-Senha-123"),
                  ("Café São João", "jose", "pão-de-açúcar")]
    conferir("ACHADO R1 Chrome (UTF-8, LF, com aspas, vírgula e ; na senha)", gravar("Senhas do Chrome.csv", chrome.encode()),
             esp_chrome, [("Gmail", "https://accounts.google.com/")])
    conferir("ACHADO R1 Edge/Chrome (UTF-8 com BOM, CRLF)",
             gravar("edge.csv", b"\xef\xbb\xbf" + chrome.replace("\n", "\r\n").encode()), esp_chrome)
    chrome_antigo = ('name,url,username,password\nSite A,https://a.exemplo,ana,aaa-111-bbb\n'
                     'Site B,https://b.exemplo,bia,"b,b;b"\n')
    conferir("Chrome antigo (sem 'note')", gravar("chrome_antigo.csv", chrome_antigo.encode()),
             [("Site A", "ana", "aaa-111-bbb"), ("Site B", "bia", "b,b;b")])

    firefox = ('"url","username","password","httpRealm","formActionOrigin","guid","timeCreated","timeLastUsed",'
               '"timePasswordChanged"\n'
               '"https://www.exemplo.com","ana","abc;def;ghi","","https://www.exemplo.com","{3f1c-aa}","1700000000000",'
               '"1700000000000","1700000000000"\n'
               '"https://outro.exemplo","bia","p""q,r","","","{9d2e-bb}","1700000000001","1700000000001","1700000000001"\n')
    conferir("ACHADO R1 Firefox (senha com aspa e vírgula)", gravar("logins.csv", firefox.encode()),
             [("https://www.exemplo.com", "ana", "abc;def;ghi"), ("https://outro.exemplo", "bia", 'p"q,r')])

    bitwarden = ('folder,favorite,type,name,notes,fields,reprompt,login_uri,login_username,login_password,login_totp\n'
                 'Finanças,1,login,Banco Exemplo,"nota, com vírgula",,0,https://banco.exemplo.com.br,ana,Pa$$w0rd;1,'
                 'otpauth://totp/x?secret=ABC\n'
                 ',,login,Loja,,,0,https://loja.exemplo,bob,xyz,\n')
    regs = conferir("Bitwarden", gravar("bitwarden_export.csv", bitwarden.encode()),
                    [("Banco Exemplo", "ana", "Pa$$w0rd;1"), ("Loja", "bob", "xyz")],
                    [("Banco Exemplo", "nota, com vírgula")])
    ok(any(r.get("chave", "") == "otpauth://totp/x?secret=ABC" for r in regs), "Bitwarden: o segredo TOTP vai para o campo 'chave'")
    ok(any(r.get("grupo", "") == "Finanças" for r in regs), "Bitwarden: a pasta 'Finanças' vira o grupo")

    lastpass = ('url,username,password,totp,extra,name,grouping,fav\n'
                'https://site.exemplo,ana,senha-123-abc,,nota extra,Site Exemplo,Pessoal,0\n'
                'https://outro.exemplo,bia,"x;y;z",,,Outro,,1\n')
    conferir("LastPass", gravar("lastpass_export.csv", lastpass.encode()),
             [("Site Exemplo", "ana", "senha-123-abc"), ("Outro", "bia", "x;y;z")], [("Site Exemplo", "nota extra")])

    onepass = ('Title,Url,Username,Password,OTPAuth,Favorite,Archived,Tags,Notes\n'
               'Banco,https://b.exemplo,ana,s3nh@-Longa-1,,0,0,,Obs do banco\n')
    conferir("1Password", gravar("1password.csv", onepass.encode()), [("Banco", "ana", "s3nh@-Longa-1")],
             [("Banco", "Obs do banco")])

    keepass = ('"Group","Title","Username","Password","URL","Notes","TOTP","Icon","Last Modified","Created"\n'
               '"Root/Banco","Banco X","ana","kp-senha-1","https://x","","","0","2026-01-01T00:00:00Z","2025-01-01T00:00:00Z"\n')
    regs = conferir("KeePassXC", gravar("keepass.csv", keepass.encode()), [("Banco X", "ana", "kp-senha-1")],
                    [("Banco X", "Root/Banco")])
    if regs and not regs[0].get("grupo"):
        info("KeePassXC: a coluna 'Group' vai para as Notas, não para o campo Grupo (só 'folder/pasta/grupo/categoria' são "
             "reconhecidos). Nenhum dado se perde; é só melhoria de organização.")

    pt = 'Serviço;Usuário;Senha;Observações\r\nBanco São João;ana;sênha-ç-1;conta de salário\r\nPadaria;josé;pão123;\r\n'
    esp_pt = [("Banco São João", "ana", "sênha-ç-1"), ("Padaria", "josé", "pão123")]
    conferir("Excel PT-BR (';' e cp1252/ANSI)", gravar("excel_ansi.csv", pt.encode("cp1252")), esp_pt,
             [("Banco São João", "conta de salário")])
    conferir("Excel 'CSV UTF-8' (';' e BOM)", gravar("excel_utf8.csv", b"\xef\xbb\xbf" + pt.encode("utf-8")), esp_pt)
    conferir("ACHADO R1 Excel com linha 'sep=;' no topo (nenhuma conta lida)", gravar("excel_sep.csv", ("sep=;\r\n" + pt).encode("cp1252")), esp_pt)
    conferir("Excel PT-BR com vírgulas na senha",
             gravar("excel_virgulas.csv", 'Serviço;Usuário;Senha\r\nA;u;a,b,c,d,e\r\nB;u;x\r\n'.encode("cp1252")),
             [("A", "u", "a,b,c,d,e"), ("B", "u", "x")])
    conferir("TSV (separado por tabulação)", gravar("tab.csv", b"name\turl\tusername\tpassword\nA\thttp://a\tu\tp1\n"),
             [("A", "u", "p1")])
    conferir("CSV sem cabeçalho (serviço, login, senha)", gravar("sem_cab_ok.csv", b"Padaria;jose;pao-123\nLoja;bia;xyz-789\n"),
             [("Padaria", "jose", "pao-123"), ("Loja", "bia", "xyz-789")])
    conferir("ACHADO R1 CSV sem cabeçalho cuja 1ª linha parece título ('Banco', 'senha-1')",
             gravar("sem_cab_banco.csv", b"Banco;ana;senha-1\nLoja;bia;senha-2\n"),
             [("Banco", "ana", "senha-1"), ("Loja", "bia", "senha-2")])
    conferir("linhas finais em branco e 'sujeira' de fim de arquivo",
             gravar("fim.csv", b"name,url,username,password\nA,http://a,u,p1\n\n\n,,,\n"), [("A", "u", "p1")])

    print("\n2) Ida e volta aleatória no padrão RFC 4180 (o que qualquer programa grava): nenhuma senha pode mudar")
    rnd = random.Random(20261120)
    ALFA = "abcXYZ019,;\"'\t \\|!@#$%&*()-_=+[]{}<>?/.:"
    cabecalhos = (["name", "url", "username", "password", "note"], ["name", "url", "username", "password"],
                  ["Serviço", "Usuário", "Senha"])
    arquivos = alteradas = erros = 0
    exemplos = []
    for delim in (",", ";", "\t"):
        for term in ("\n", "\r\n"):
            for cab in cabecalhos:
                for n_linhas in (2, 3, 6):
                    for _ in range(8):
                        buf = io.StringIO()
                        w = csv.writer(buf, delimiter=delim, lineterminator=term)
                        w.writerow(cab)
                        esperado = []
                        for i in range(n_linhas):
                            senha = "".join(rnd.choice(ALFA) for _ in range(rnd.randint(6, 22))).strip() or "Zz"
                            reg = (f"Site{i}", f"user{i}@ex.com", senha)
                            mapa = {"name": reg[0], "url": f"https://s{i}.exemplo", "username": reg[1], "password": reg[2],
                                    "note": f"n{i}", "Serviço": reg[0], "Usuário": reg[1], "Senha": reg[2]}
                            w.writerow([mapa[h] for h in cab])
                            esperado.append(reg)
                        dados = buf.getvalue().encode("utf-8")
                        if rnd.random() < 0.5:
                            dados = b"\xef\xbb\xbf" + dados
                        arquivos += 1
                        por_nome, regs, av = ler(gravar("aleatorio.csv", dados))
                        if por_nome is None:
                            erros += 1
                            exemplos.append(("ERRO", av[0][:70], delim))
                            continue
                        ruim = [(e[2], por_nome.get(e[0], {}).get("senha")) for e in esperado
                                if por_nome.get(e[0], {}).get("senha") != e[2]]
                        if ruim:
                            alteradas += 1
                            exemplos.append((repr(delim), ruim[0]))
    ok(alteradas == 0 and erros == 0,
       f"ACHADO R1: {arquivos} CSVs válidos (vírgula, ';' e tab; LF e CRLF; com e sem BOM): "
       f"{alteradas} arquivos com senha ALTERADA ou conta perdida, {erros} recusados"
       + (f". Ex.: {exemplos[0]}" if exemplos else "")
       + (" (hoje csv.Sniffer adivinha o dialeto olhando as senhas e erra o delimitador e a aspa dupla)" if exemplos else ""))

    print("\n3) Planilhas .xlsx no estilo Excel / LibreOffice (geradas com openpyxl, sem selo do cofre)")
    try:
        import openpyxl
    except ImportError:
        openpyxl = None
        ok(False, "openpyxl não instalado (faz parte de requirements.txt)")
    if openpyxl:
        import datetime
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Planilha1"
        ws.append(["Minhas senhas - cópia de 2026"])           # título acima do cabeçalho, como se vê em planilhas reais
        ws.append([])
        ws.append(["Serviço", "Usuário", "Senha", "PIN", "Observações"])
        ws.append(["Banco São João", "ana", "Sênha-ç-1-Longa", 123, "gerente: José"])      # PIN numérico: Excel tira o zero
        ws.append(["Plano de saúde", "bia", 12345678, None, datetime.date(2026, 3, 1)])    # senha numérica e data
        ws.append(["Fórmula", "x", "=1+1", None, None])                                      # célula de fórmula simples
        ws.append(["Com espaços", "z", "  senha com espaço  ", None, None])
        oculta = wb.create_sheet("Auxiliar")
        oculta.sheet_state = "hidden"
        oculta.append(["Serviço", "Usuário", "Senha"])
        oculta.append(["Aba oculta", "w", "senha-da-aba-oculta"])
        caminho = os.path.join(TMP, "excel_real.xlsx")
        wb.save(caminho)
        wb_perigo = openpyxl.Workbook()
        wp = wb_perigo.active
        wp.append(["Serviço", "Usuário", "Senha"])
        wp.append(["Armadilha", "x", '=HYPERLINK("http://x","clique")'])
        wb_perigo.save(os.path.join(TMP, "perigo.xlsx"))
        por_p, _, av_p = ler(os.path.join(TMP, "perigo.xlsx"))
        ok(por_p is None and "VARREDURA" in av_p[0], "xlsx com fórmula HYPERLINK() é RECUSADO pela varredura de segurança (nada é lido)")
        por_nome, regs, avisos = ler(caminho)
        if por_nome is None:
            ok(False, f"xlsx no estilo Excel: leitura falhou ({avisos[0][:90]})")
        else:
            r = por_nome.get("Banco São João", {})
            ok(r.get("senha") == "Sênha-ç-1-Longa" and r.get("login") == "ana", "xlsx: cabeçalho achado abaixo de linhas de título; acentos preservados")
            ok(por_nome.get("Plano de saúde", {}).get("senha") == "12345678", "xlsx: senha numérica 12345678 entra como texto, sem '.0'")
            ok(por_nome.get("Banco São João", {}).get("pin") == "123", "xlsx: PIN numérico lido (o zero à esquerda que o Excel apagou não volta)")
            ok(any("PIN" in a and "zeros" in a for a in avisos), "xlsx: o programa AVISA que PIN curto pode ter perdido zeros à esquerda")
            f = por_nome.get("Fórmula", {})
            ok(f.get("senha", "") in ("", "=1+1"), "xlsx: fórmula simples não vira valor calculado nem texto estranho no cofre")
            ok("Aba oculta" in por_nome, "xlsx: aba oculta também é lida e visível na prévia (nada entra escondido)")
            esp = por_nome.get("Com espaços", {}).get("senha")
            if esp != "  senha com espaço  ":
                info(f"espaços nas pontas da senha são cortados na importação (leu {esp!r}). Se a senha REALMENTE tem "
                     "espaço no começo/fim, ela entra diferente; vale um aviso na prévia.")

    print("\n4) Dados que não podem sair da planilha")
    csv_notas = ('name,url,username,password,note\n'
                 'Roteador,http://192.168.0.1,admin,admin-123,"SSID: Casa 5G\nWi-Fi: gato-azul-77"\n').encode()
    regs = conferir("nota com várias linhas", gravar("notas.csv", csv_notas), [("Roteador", "admin", "admin-123")],
                    [("Roteador", "gato-azul-77"), ("Roteador", "192.168.0.1")])
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print()
print("FALHAS:", FALHAS)
sys.exit(1 if FALHAS else 0)
