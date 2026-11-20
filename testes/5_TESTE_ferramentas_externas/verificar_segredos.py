"""Procura arquivos de cofre/chave/copias e segredos em texto antes de enviar o projeto ao GitHub.
Uso: python verificar_segredos.py [pasta]  |  Saida: 0 = limpo | 1 = achados ou falha da auditoria."""
import fnmatch
import json
import os
import subprocess
import sys

PROIBIDOS = ["cofre.dat", "*.dat", "*.key", "*.bak", "*.bak[1-5]", "*.diag", "*.pre-v5", "*.lock", "cofre*.xlsx"]
PULAR = {
    ".git", "pacotes", "ambiente_virtual_ferramentas (NAO MEXER)", "__pycache__", "resultados", "logs_de_compilacao",
    ".mypy_cache", ".ruff_cache",
}


def main():
    raiz = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
    achados = []
    if not os.path.isdir(raiz):
        print(f"ERRO: pasta inexistente: {raiz}")
        return 1
    for pasta, subs, arqs in os.walk(raiz):
        subs[:] = [
            s for s in subs
            if s not in PULAR and not s.startswith(("venv", "_venv")) and s != ".venv"
        ]
        for a in arqs:
            if any(fnmatch.fnmatch(a.lower(), p) for p in PROIBIDOS):
                achados.append(f"arquivo sensivel: {os.path.relpath(os.path.join(pasta, a), raiz)}")
    try:
        ls = subprocess.run(["git", "ls-files", "-z"], cwd=raiz, capture_output=True, timeout=60)
        if ls.returncode != 0:
            achados.append("falha operacional: git ls-files retornou erro")
            rastreados = []
        else:
            rastreados = ls.stdout.decode("utf-8", "surrogateescape").split("\0")
        for a in rastreados:
            if a and any(fnmatch.fnmatch(os.path.basename(a).lower(), p) for p in PROIBIDOS):
                achados.append(f"JA RASTREADO PELO GIT: {a}")
    except (OSError, subprocess.SubprocessError):
        achados.append("falha operacional: git ls-files nao pode ser executado")
    try:
        r = subprocess.run([sys.executable, "-m", "detect_secrets", "scan", "--all-files",
                            "--exclude-files", r"(?:^|[/\\])(?:pacotes|_venv[^/\\]*|venv[^/\\]*|\.venv|resultados|logs_de_compilacao|\.mypy_cache|\.ruff_cache|\.git)[/\\]"],
                           cwd=raiz, capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            achados.append("falha operacional: detect-secrets scan retornou erro")
        else:
            dados = json.loads(r.stdout)
            for arq, lista in dados.get("results", {}).items():
                for s in lista:
                    achados.append(f"possivel segredo ({s['type']}): {arq}:{s['line_number']}")
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        achados.append("falha operacional: detect-secrets nao pode ser executado ou retornou JSON invalido")
    for a in achados:
        print(" -", a)
    print(f"Achados: {len(achados)}")
    return 1 if achados else 0


if __name__ == "__main__":
    sys.exit(main())
