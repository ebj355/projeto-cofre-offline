#!/usr/bin/env python3
# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Reprova qualquer uso de hash "cru" (SHA-2, SHA-1, MD5, SHA-3) misturando um SEGREDO com outros dados.

Por que existe: SHA-256(segredo + dados) permite ataque de extensão de comprimento (length extension): quem conhece
o resultado consegue calcular o hash de (segredo + dados + enchimento + algo a mais) sem saber o segredo. Quando
precisa de autenticação ou derivação com segredo, o projeto usa HMAC ou HKDF (a biblioteca `cryptography`), nunca
hashlib.sha256(segredo + x). Este teste impede que alguém reabra o problema sem querer.

Regras (olhando o código-fonte com `ast`, nada é executado):
  A) hashlib.<hash>(...) cujo argumento CONCATENA (+, f-string, join) e contém um nome de aparência secreta;
  B) objeto hashlib com mais de uma entrada (argumento inicial + update, ou 2+ updates) em que um update recebe
     um nome de aparência secreta;
  C) hashlib.<hash>(<nome secreto>) sozinho, sem sal e sem HMAC (hash puro de senha/segredo: permite dicionário
     offline contra o valor guardado).
Usos legítimos (checksum, identificador público, hash de arquivo) ficam numa lista BRANCA abaixo, cada um com o
MOTIVO escrito. Para acrescentar um uso novo, escreva o motivo; se o motivo for "autenticação" ou "derivação de
chave", a resposta certa é trocar por HMAC/HKDF, não acrescentar na lista.

Uso: python teste_nucleo_sem_hash_com_segredo.py     (código de saída 0 = passou, 1 = falhou)
"""
import ast
import os
import re
import sys

ARQUIVOS = ["cofre_senhas.py", "icones_marcas.py"]

HASHES = {"md5", "sha1", "sha224", "sha256", "sha384", "sha512",
          "sha3_224", "sha3_256", "sha3_384", "sha3_512"}

# Nomes (variáveis, atributos) que parecem segredo. "material" entra porque no cofre ele já é derivado de segredo.
SECRETO = re.compile(
    r"(senha|password|passwd|segredo|secret|token|seed|kek|dek|master|material|chave|key|recuper|\bpin\b|^_?[fg]$)",
    re.IGNORECASE)
# Nomes que contêm "key"/"chave" mas são públicos ou só dados de apresentação.
NAO_SECRETO = re.compile(r"(pub|publica|public|ident|nome|name|chaves_|_id$|hash_|digest)", re.IGNORECASE)

# (função onde está, nome do segredo-aparente) -> MOTIVO. Sem motivo, não entra.
LISTA_BRANCA = {
    ("_id_pc", "material"):
        "identificador público de 8 bytes de um computador, truncado; não autentica nada nem é derivação de chave "
        "(o 'material' já chega misturado por HMAC com o segredo local).",
    ("_dv_chave", "b"):
        "2 caracteres de verificação (10 bits) para erro de digitação; rótulo fixo na frente, saída truncada em 10 bits, "
        "a saída não serve como autenticador nem como chave.",
    ("_selo_do_cofre", "base"):
        "identificador público do cofre sobre campos que já ficam em claro no cabeçalho; a chave de selagem sai de HKDF.",
    ("hibp_dividir", "senha"):
        "SHA-1 exigido pelo protocolo k-anonymity do Have I Been Pwned: só os 5 primeiros caracteres saem do computador; "
        "o hash não é gravado nem usado como MAC ou chave.",
    ("_cor_da_marca", "chave_hash"):
        "'chave_hash' é o nome da marca (texto público) usado só para escolher a cor do ícone; MD5 com usedforsecurity=False.",
}


def _nomes(no):
    """Todos os nomes de variável/atributo usados dentro de uma expressão."""
    achados = []
    for n in ast.walk(no):
        if isinstance(n, ast.Name):
            achados.append(n.id)
        elif isinstance(n, ast.Attribute):
            achados.append(n.attr)
    return achados


def _parece_secreto(nome):
    return bool(SECRETO.search(nome)) and not NAO_SECRETO.search(nome)


def _segredos_em(no):
    return sorted({n for n in _nomes(no) if _parece_secreto(n)})


def _eh_concatenacao(no):
    if isinstance(no, ast.BinOp) and isinstance(no.op, ast.Add):
        return True
    if isinstance(no, ast.JoinedStr):
        return True
    if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute) and no.func.attr == "join":
        return True
    if isinstance(no, ast.Call) and no.args:      # bytes(x + y), memoryview(...), .encode() de concatenação
        return any(_eh_concatenacao(a) for a in no.args)
    if isinstance(no, ast.Attribute):             # (a + b).encode()
        return _eh_concatenacao(no.value)
    return False


def _chamada_hashlib(no):
    """Nome do hash se for hashlib.<hash>(...) (ou hashlib.new('<hash>', ...)); senão None."""
    if not (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)):
        return None
    f = no.func
    if isinstance(f.value, ast.Name) and f.value.id == "hashlib":
        if f.attr in HASHES:
            return f.attr
        if f.attr == "new" and no.args and isinstance(no.args[0], ast.Constant) and str(no.args[0].value).lower() in HASHES:
            return str(no.args[0].value).lower()
    return None


def _dados_da_chamada(no):
    """Argumento com os dados: hashlib.sha256(DADOS) ou hashlib.new('sha256', DADOS)."""
    if isinstance(no.func, ast.Attribute) and no.func.attr == "new":
        return no.args[1] if len(no.args) > 1 else None
    return no.args[0] if no.args else None


def _funcao_de(no, pais):
    while no is not None:
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return no.name
        no = pais.get(no)
    return "<modulo>"


def analisar(codigo, nome_arquivo="<codigo>"):
    """Devolve a lista de achados: (regra, arquivo, linha, funcao, segredos, trecho)."""
    arvore = ast.parse(codigo, filename=nome_arquivo)
    pais = {}
    for pai in ast.walk(arvore):
        for filho in ast.iter_child_nodes(pai):
            pais[filho] = pai
    linhas = codigo.splitlines()
    achados = []

    def trecho(no):
        try:
            return linhas[no.lineno - 1].strip()[:120]
        except Exception:
            return ""

    # objetos hashlib por função: nome da variável -> (número de entradas, nó)
    por_funcao = {}
    for no in ast.walk(arvore):
        # --- regras A e C: chamada direta com dados ---
        if _chamada_hashlib(no) and _dados_da_chamada(no) is not None:
            arg = _dados_da_chamada(no)
            segredos = _segredos_em(arg)
            if segredos:
                regra = "A" if _eh_concatenacao(arg) else "C"
                achados.append((regra, nome_arquivo, no.lineno, _funcao_de(no, pais), segredos, trecho(no)))
        # --- regra B: h = hashlib.x(); h.update(...) ---
        if isinstance(no, ast.Assign) and _chamada_hashlib(no.value) and len(no.targets) == 1 \
                and isinstance(no.targets[0], ast.Name):
            fn = _funcao_de(no, pais)
            entradas = 1 if _dados_da_chamada(no.value) is not None else 0
            por_funcao.setdefault(fn, {})[no.targets[0].id] = [entradas, []]
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute) and no.func.attr == "update" \
                and isinstance(no.func.value, ast.Name):
            fn = _funcao_de(no, pais)
            reg = por_funcao.setdefault(fn, {}).get(no.func.value.id)
            if reg is not None and no.args:
                reg[0] += 1
                reg[1].append(no)
    for fn, objetos in por_funcao.items():
        for nome, (entradas, updates) in objetos.items():
            if entradas >= 2:
                for up in updates:
                    segredos = _segredos_em(up.args[0])
                    if segredos:
                        achados.append(("B", nome_arquivo, up.lineno, fn, segredos, trecho(up)))
    return achados


def _filtrar(achados):
    """Tira os usos da lista branca (cada um com motivo escrito)."""
    restantes = []
    for regra, arq, linha, fn, segredos, texto in achados:
        if all((fn, s) in LISTA_BRANCA for s in segredos):
            continue
        restantes.append((regra, arq, linha, fn, segredos, texto))
    return restantes


# --- autoteste: o detector precisa continuar enxergando o erro (senão o teste ficaria cego sem ninguém notar) ---
CASOS_RUINS = {
    "SHA-256(segredo + dados)": "import hashlib\ndef f(segredo, dados):\n    return hashlib.sha256(segredo + dados).digest()\n",
    "SHA-256(prefixo + senha + dados)": "import hashlib\ndef f(senha, d):\n    return hashlib.sha256(b'x|' + senha + b'|' + d).hexdigest()\n",
    "f-string com chave": "import hashlib\ndef f(chave, d):\n    return hashlib.sha256(f'{chave}{d}'.encode()).hexdigest()\n",
    "join com token": "import hashlib\ndef f(token, d):\n    return hashlib.sha512(b''.join([token, d])).digest()\n",
    "update em duas partes": "import hashlib\ndef f(segredo, d):\n    h = hashlib.sha256(segredo)\n    h.update(d)\n    return h.digest()\n",
    "update sem argumento inicial": "import hashlib\ndef f(segredo, d):\n    h = hashlib.sha256()\n    h.update(d)\n    h.update(segredo)\n    return h.digest()\n",
    "hash cru de senha": "import hashlib\ndef f(senha):\n    return hashlib.sha256(senha.encode()).hexdigest()\n",
    "hashlib.new": "import hashlib\ndef f(segredo, d):\n    return hashlib.new('sha256', segredo + d).digest()\n",
}
CASOS_BONS = {
    "HMAC": "import hmac, hashlib\ndef f(segredo, d):\n    return hmac.new(segredo, d, hashlib.sha256).digest()\n",
    "checksum de arquivo": "import hashlib\ndef f(dados):\n    return hashlib.sha256(dados).digest()\n",
    "hash de chunk": "import hashlib\ndef f(chunks):\n    h = hashlib.sha256()\n    for c in chunks:\n        h.update(c)\n    return h.hexdigest()\n",
    "rotulo + dados públicos": "import hashlib\ndef f(sal, cabecalho):\n    return hashlib.sha256(b'id|' + sal + cabecalho).digest()[:8]\n",
}


def main():
    falhas = []

    def conferir(ok, texto, detalhe=""):
        print(("  [OK]   " if ok else "  [FALHOU] ") + texto + (("  ->  " + detalhe) if detalhe and not ok else ""))
        if not ok:
            falhas.append(texto)

    print("== A) autoteste do detector")
    for nome, cod in CASOS_RUINS.items():
        conferir(len(analisar(cod)) >= 1, f"detecta: {nome}")
    for nome, cod in CASOS_BONS.items():
        conferir(len(analisar(cod)) == 0, f"aceita: {nome}")

    print("== B) o código do projeto")
    aqui = os.path.dirname(os.path.abspath(__file__))
    raiz = aqui
    for _ in range(6):
        if os.path.isfile(os.path.join(raiz, ARQUIVOS[0])):
            break
        raiz = os.path.dirname(raiz)
    else:
        conferir(False, f"achei {ARQUIVOS[0]} subindo a partir de {aqui}")
        return finalizar(falhas)
    for nome in ARQUIVOS:
        caminho = os.path.join(raiz, nome)
        if not os.path.isfile(caminho):
            conferir(False, f"existe {nome}")
            continue
        with open(caminho, "r", encoding="utf-8") as f:
            achados = _filtrar(analisar(f.read(), nome))
        if achados:
            for regra, arq, linha, fn, segredos, texto in achados:
                conferir(False, f"{arq}:{linha} em {fn}() regra {regra}: hash cru com {', '.join(segredos)}", texto)
        else:
            conferir(True, f"{nome}: nenhum hashlib misturando segredo com dados")

    print("== C) a lista branca não pode esconder erro novo")
    for (fn, nome), motivo in LISTA_BRANCA.items():
        conferir(len(motivo) >= 30, f"lista branca ({fn}, {nome}) tem motivo escrito")
    return finalizar(falhas)


def finalizar(falhas):
    print()
    if falhas:
        print(f"FALHAS: {falhas}")
        return 1
    print("Tudo certo: nenhum SHA-256(segredo + dados) no código.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
