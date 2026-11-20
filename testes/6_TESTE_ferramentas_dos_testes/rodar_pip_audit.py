"""Executa pip-audit com limite de tempo e sem deixar o BAT preso aguardando a rede."""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache_testes import preparar_cache_temporario


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", required=True)
    parser.add_argument("--requirements", required=True)
    parser.add_argument("--log", required=True)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--format")
    parser.add_argument("--output")
    args = parser.parse_args()

    cache_base = preparar_cache_temporario("pip_audit")
    cache_dir = tempfile.mkdtemp(prefix="_cache_pip_audit_", dir=cache_base)
    comando = [args.python, "-m", "pip_audit", "-r", args.requirements,
               "--no-deps", "--disable-pip", "--timeout", "15",
               "--cache-dir", cache_dir, "--progress-spinner", "off"]
    if args.format:
        comando.extend(["--format", args.format])
    if args.output:
        comando.extend(["--output", args.output])

    ambiente = dict(os.environ)
    ambiente["PIP_NO_CACHE_DIR"] = "1"
    ambiente["PIP_DEFAULT_TIMEOUT"] = "15"
    ambiente["PIP_RETRIES"] = "0"
    ambiente["PYTHONUTF8"] = "1"
    ambiente["PYTHONIOENCODING"] = "utf-8"

    erro_limpeza = None
    try:
        processo = subprocess.run(
            comando,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=ambiente,
            timeout=args.timeout,
        )
        texto = processo.stdout or ""
        codigo = processo.returncode
    except subprocess.TimeoutExpired as ex:
        codigo = 9
        saida = ex.stdout or ex.stderr or ""
        if isinstance(saida, bytes):
            saida = saida.decode("utf-8", "replace")
        texto = (saida or "") + (
            f"\n[PULADO] pip-audit excedeu o limite de {args.timeout}s "
            "e foi encerrado. Nao houve confirmacao de vulnerabilidade; confira a rede.\n"
        )
    except (FileNotFoundError, OSError) as ex:
        codigo = 9
        texto = f"[PULADO] pip-audit nao pode ser iniciado: {ex}\n"
    finally:
        try:
            shutil.rmtree(cache_dir)
        except FileNotFoundError:
            pass
        except OSError as ex:
            erro_limpeza = ex

    if erro_limpeza:
        texto += f"[ERRO] nao consegui remover o cache temporario {cache_dir}: {erro_limpeza}\n"
        if codigo == 0:
            codigo = 1

    modo = "a" if os.path.exists(args.log) else "w"
    with open(args.log, modo, encoding="utf-8") as destino:
        destino.write(texto)
        if not texto.endswith("\n"):
            destino.write("\n")

    sys.stdout.write(texto)
    return codigo


if __name__ == "__main__":
    sys.exit(main())
