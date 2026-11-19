"""Procura no projeto o que NUNCA pode ir para o GitHub: arquivos de cofre/chave/copias e segredos em texto (detect-secrets, se instalado).
Uso: python verificar_segredos.py [pasta]  |  Saida: 0 = limpo | 1 = achados | 9 = nada a verificar."""
import fnmatch
import json
import os
import subprocess
import sys

PROIBIDOS = ["cofre.dat", "*.dat", "*.key", "*.bak", "*.bak[1-5]", "*.diag", "*.pre-v5", "*.lock", "cofre*.xlsx"]
PULAR = {".git", "pacotes", "_venv_ferramentas", "__pycache__", "resultados", "logs_de_compilacao"}


def main():
    raiz = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
    achados = []
    for pasta, subs, arqs in os.walk(raiz):
        subs[:] = [s for s in subs if s not in PULAR and not s.startswith("venv")]
        for a in arqs:
            if any(fnmatch.fnmatch(a.lower(), p) for p in PROIBIDOS):
                achados.append(f"arquivo sensivel: {os.path.relpath(os.path.join(pasta, a), raiz)}")
    try:
        ls = subprocess.run(["git", "ls-files"], cwd=raiz, capture_output=True, text=True, timeout=60)
        rastreados = ls.stdout.split() if ls.returncode == 0 else []
        for a in rastreados:
            if any(fnmatch.fnmatch(os.path.basename(a).lower(), p) for p in PROIBIDOS):
                achados.append(f"JA RASTREADO PELO GIT: {a}")
    except (OSError, subprocess.SubprocessError):
        print("aviso: git nao encontrado; so a varredura de arquivos foi feita.")
    try:
        r = subprocess.run([sys.executable, "-m", "detect_secrets", "scan", "--all-files",
                            "--exclude-files", r"(pacotes|_venv_ferramentas|resultados|\.git)[/\\]"],
                           cwd=raiz, capture_output=True, text=True, timeout=600)
        if r.returncode == 0 and r.stdout.strip():
            for arq, lista in json.loads(r.stdout).get("results", {}).items():
                for s in lista:
                    achados.append(f"possivel segredo ({s['type']}): {arq}:{s['line_number']}")
        else:
            print("aviso: detect-secrets indisponivel; so a varredura de nomes foi feita.")
    except (OSError, subprocess.SubprocessError, ValueError):
        print("aviso: detect-secrets falhou; so a varredura de nomes foi feita.")
    for a in achados:
        print(" -", a)
    print(f"Achados: {len(achados)}")
    return 1 if achados else 0


if __name__ == "__main__":
    sys.exit(main())
