# ARCA SISTEMAS | PRODUTO ARCA | IDENTIFICACAO INTERNA; CONSULTE MARCA_ARCA.txt
"""Confere o .gitignore com residuos reais de cofre e valida os pins usados pelo build."""
import hashlib
import importlib.util
import re
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
import cofre_senhas as cofre


def main():
    falhas = []

    def conferir(condicao, descricao):
        print(("[OK] " if condicao else "[FALHOU] ") + descricao, flush=True)
        if not condicao:
            falhas.append(descricao)

    gitignore = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", ".gitignore"],
        cwd=RAIZ, capture_output=True, text=True, check=False,
    )
    conferir(gitignore.returncode == 0, ".gitignore existe e esta versionado com o nome correto")
    legado_gitignore = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", "_gitignore"],
        cwd=RAIZ, capture_output=True, text=True, check=False,
    )
    conferir(legado_gitignore.returncode != 0, "_gitignore nao esta versionado")

    for relativo in ("pacotes/LEIA-ME.txt", "pacotes/SHA256.txt"):
        checagem = subprocess.run(
            ["git", "check-ignore", "--no-index", "--quiet", "--", relativo],
            cwd=RAIZ, check=False,
        )
        conferir(checagem.returncode == 1, f".gitignore permite versionar {relativo}")
    wheels = subprocess.run(
        ["git", "check-ignore", "--no-index", "--quiet", "--", "pacotes/exemplo.whl"],
        cwd=RAIZ, check=False,
    )
    conferir(wheels.returncode == 0, ".gitignore continua ignorando wheels em pacotes")

    requirements = (RAIZ / "requirements.txt").read_text(encoding="utf-8-sig")
    requirements_test_in = (RAIZ / "requirements-test-direct.in").read_text(encoding="utf-8-sig")
    requirements_test = (RAIZ / "requirements-test-lock.txt").read_text(encoding="utf-8-sig")
    pins_prod = dict(re.findall(r"(?m)^\s*([A-Za-z0-9_.-]+)==([0-9A-Za-z.+!-]+)", requirements))
    pins_test = re.findall(r"(?m)^\s*cryptography==([0-9.]+)(?:\s|\\|$)", requirements_test)
    pins_test_in = dict(re.findall(r"(?m)^\s*([A-Za-z0-9_.-]+)==([0-9A-Za-z.+!-]+)", requirements_test_in))
    pins_lock = dict(re.findall(r"(?m)^([A-Za-z0-9_.-]+)==([0-9A-Za-z.+!-]+)", requirements_test))
    conferir(pins_prod.get("cryptography") == "50.0.2" and pins_test == ["50.0.2"],
             "requirements.txt e requirements-test-lock.txt fixam a mesma cryptography")
    conferir(bool(pins_test_in) and all(pins_lock.get(nome) == versao for nome, versao in pins_test_in.items()),
             "requirements-test-lock.txt preserva os pins de requirements-test-direct.in")
    runtime = {"cryptography", "argon2-cffi", "argon2-cffi-bindings", "openpyxl", "defusedxml",
               "fido2", "cffi", "pycparser", "et-xmlfile"}
    conferir(all(pins_test_in.get(nome) == pins_prod.get(nome) for nome in runtime),
             "requirements-test-direct.in mantém os pins de runtime de requirements.txt")
    conferir("--hash=sha256:" in requirements_test
             and not re.search(r"(?m)^\s*[A-Za-z0-9_.-]+\s*[><~!]=?", requirements_test),
             "requirements-test-lock.txt exige hashes e nao contem faixas de versao")

    instalador = (RAIZ / "instalar_cofre.ps1").read_text(encoding="utf-8-sig")
    pins_installer = dict(re.findall(r"(?m)^\s*([A-Za-z0-9_.-]+)==([0-9A-Za-z.+!-]+)", instalador))
    conferir(bool(pins_prod) and all(pins_installer.get(nome) == versao for nome, versao in pins_prod.items()),
             "requirements.txt e instalador fixam as mesmas versoes")
    linhas_crypto = [linha.strip() for linha in instalador.splitlines()
                     if linha.strip().startswith("cryptography==")]
    hashes = re.findall(r"--hash=sha256:([0-9a-f]{64})", "\n".join(linhas_crypto))
    conferir(
        len(linhas_crypto) == 1
        and linhas_crypto[0].startswith("cryptography==50.0.2 ")
        and len(hashes) == 1,
        "instalador fixa a mesma versao com hash SHA-256",
    )
    conferir("cryptography==50.0.2" in (RAIZ / "README.md").read_text(encoding="utf-8-sig"),
             "README documenta a versao fixada")
    fonte = (RAIZ / "cofre_senhas.py").read_text(encoding="utf-8-sig")
    conferir("WerAddExcludedApplication" not in fonte and "WerRemoveExcludedApplication" in fonte,
             "o programa nao cria exclusao WER e remove a entrada legada do Registro")

    wheelhouse = RAIZ / "pacotes"
    wheels = sorted(wheelhouse.glob("cryptography-50.0.2-*-win_amd64.whl"))
    conferir(len(wheels) == 1, "wheel x64 fixado existe no wheelhouse")
    if len(wheels) == 1 and len(hashes) == 1:
        wheel_hash = hashlib.sha256(wheels[0].read_bytes()).hexdigest()
        conferir(wheel_hash == hashes[0], "hash embutido no instalador confere com o wheel local")
        manifest = wheelhouse / "SHA256.txt"
        linhas_manifesto = manifest.read_text(encoding="ascii").splitlines() if manifest.exists() else []
        conferir(any(linha == f"{wheel_hash}  {wheels[0].name}" for linha in linhas_manifesto),
                 "manifesto SHA256 do wheelhouse inclui o wheel fixado")

    cofre.NIVEIS["alto"] = (1, 8192)
    senha = "teste temporario para verificar gitignore"
    with tempfile.TemporaryDirectory(prefix="cofre-ignore-", dir=RAIZ) as temporario:
        pasta = Path(temporario)
        danificado = pasta / "cofre.dat"
        original = cofre.Cofre.criar(str(danificado), senha, 3, cofre.MODO_OU, "alto")
        original.registros.append({"id": "1", "servico": "Teste", "login": "u", "senha": "s"})
        original.salvar()
        original.fechar()
        danificado.write_bytes(b"arquivo danificado de teste")
        conferir(cofre.restaurar_copia(str(danificado)) is not None,
                 "restauracao de teste gera o arquivo .danificado")
        caminho_danificado = Path(str(danificado) + ".danificado")

        fixture_path = RAIZ / "testes" / "1_TESTE_motor_do_cofre" / "PECA_DE_TESTE_cofre_versao_4_antiga.py"
        spec = importlib.util.spec_from_file_location("cofre_v4_fixture", fixture_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("Nao foi possivel carregar o fixture de migracao v4.")
        cofre_v4 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cofre_v4)
        cofre_v4.NIVEIS["alto"] = (1, 8192)
        legado_path = pasta / "cofre-legado.dat"
        legado = cofre_v4.Cofre.criar(str(legado_path), senha, 3, 0, "alto")
        legado.registros.append({"id": "1", "servico": "Antigo", "login": "u", "senha": "s"})
        legado.salvar()
        legado.fechar()
        migrado = cofre.Cofre.abrir(str(legado_path), senha=senha)
        migrado.fechar()
        caminho_pre_v5 = Path(str(legado_path) + ".pre-v5")
        conferir(caminho_pre_v5.is_file(), "migracao real gera o arquivo .pre-v5")

        temporario_tmp = pasta / "cofre.dat.123.tmp"
        temporario_tmp.write_bytes(b"temporario")
        subpasta_tmp = pasta / ".tmp_cofre"
        subpasta_tmp.mkdir()
        marcador_tmp = subpasta_tmp / "marcador"
        marcador_tmp.write_bytes(b"temporario")

        for caminho, nome in (
            (caminho_danificado, "*.danificado"),
            (caminho_pre_v5, "*.pre-v5"),
            (temporario_tmp, "*.tmp"),
            (marcador_tmp, ".tmp_cofre/"),
        ):
            relativo = caminho.relative_to(RAIZ).as_posix()
            ignorado = subprocess.run(
                ["git", "check-ignore", "--no-index", "--quiet", "--", relativo],
                cwd=RAIZ, check=False,
            ).returncode == 0
            conferir(ignorado, f".gitignore cobre {nome}")

    rastreados = subprocess.run(
        ["git", "ls-files", "-z"], cwd=RAIZ, capture_output=True, check=True,
    ).stdout.decode("utf-8", "surrogateescape").split("\0")
    sensiveis = [
        nome for nome in rastreados if nome and nome.lower().endswith(
            (".dat", ".danificado", ".pre-v5", ".tmp", ".key", ".diag")
        )
    ]
    conferir(not sensiveis, "git ls-files nao contem arquivos de cofre, chaves ou temporarios")

    print("FALHAS:", falhas)
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
