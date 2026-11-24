# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Procura arquivos de cofre/chave/copias e segredos em texto antes de enviar o projeto ao GitHub.
Uso: python verificar_segredos.py [pasta]  |  Saida: 0 = limpo | 1 = achados ou falha da auditoria."""
import fnmatch
import json
import os
import subprocess
import sys
import shutil
import tempfile

PROIBIDOS = ["cofre.dat", "*.dat", "*.key", "*.bak", "*.bak[1-5]", "*.diag", "*.pre-v5", "*.lock", "cofre*.xlsx"]
PULAR = {
    ".git", "pacotes", "ambiente_virtual_ferramentas (NAO MEXER)", "__pycache__", "resultados", "CACHE", "CACHE_PROJETO_NAO_MEXER", "logs_de_compilacao",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "_build",
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
                            "--exclude-files",                                                         r"(?:^|[/\\])(?:pacotes|ambiente_virtual_ferramentas(?:[^/\\]*)|_venv[^/\\]*|venv[^/\\]*|\.venv|resultados|CACHE|CACHE_PROJETO_NAO_MEXER|logs_de_compilacao|\.mypy_cache|\.pytest_cache|\.ruff_cache|_build|\.git)(?:[/\\]|$)"],
                           cwd=raiz, capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            achados.append("falha operacional: detect-secrets scan retornou erro")
        else:
            dados = json.loads(r.stdout)
            for arq, lista in dados.get("results", {}).items():
                for s in lista:
                    caminho = os.path.join(raiz, arq)
                    try:
                        with open(caminho, encoding="utf-8", errors="replace") as f:
                            linha = next((texto for numero, texto in enumerate(f, 1)
                                          if numero == s["line_number"]), "")
                    except OSError:
                        linha = ""
                    if "pragma: allowlist secret" in linha:
                        continue
                    achados.append(f"possivel segredo ({s['type']}): {arq}:{s['line_number']}")
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        achados.append("falha operacional: detect-secrets nao pode ser executado ou retornou JSON invalido")
    gitleaks = shutil.which("gitleaks")
    if not gitleaks:
        candidatos = (
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Links", "gitleaks.exe"),
            os.path.join(os.environ.get("PROGRAMFILES", ""), "WinGet", "Links", "gitleaks.exe"),
        )
        gitleaks = next((caminho for caminho in candidatos if caminho and os.path.isfile(caminho)), None)
    if not gitleaks:
        achados.append("falha operacional: gitleaks nao esta instalado ou no PATH")
    else:
        with tempfile.TemporaryDirectory(prefix="arca-gitleaks-") as temporario:
            relatorio = os.path.join(temporario, "gitleaks.json")
            try:
                r = subprocess.run([gitleaks, "detect", "--source", raiz, "--report-format", "json",
                                    "--report-path", relatorio, "--exit-code", "1"],
                                   cwd=raiz, capture_output=True, text=True, timeout=600)
                if r.returncode == 1:
                    achados.append("gitleaks encontrou segredo no historico ou na area de trabalho")
                elif r.returncode != 0:
                    achados.append("falha operacional: gitleaks retornou codigo %d" % r.returncode)
            except (OSError, subprocess.SubprocessError):
                achados.append("falha operacional: gitleaks nao pode ser executado")
    for a in achados:
        print(" -", a)
    print(f"Achados: {len(achados)}")
    return 1 if achados else 0


if __name__ == "__main__":
    sys.exit(main())
