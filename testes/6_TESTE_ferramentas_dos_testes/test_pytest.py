"""Ponte para o PYTEST: cada arquivo teste_*.py do projeto vira um caso do pytest (rodando em processo separado, com os
mesmos parâmetros do rodar_todos.py). Uso:  pytest testes/6_TESTE_ferramentas_dos_testes/test_pytest.py -v   (ou  -k trava  para escolher um)
Os testes de interface (gui/) precisam de tela: no Linux usam o xvfb-run; sem ele são pulados."""
import glob, os, shutil, subprocess, sys
import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))        # testes/6_TESTE_ferramentas_dos_testes
RAIZ_TESTES = os.path.dirname(AQUI)                       # testes/ (onde ficam nucleo/ e gui/)
sys.path.insert(0, AQUI)
import rodar_todos                                      # reaproveita a escolha do Python que tem tkinter

NUCLEO = sorted(glob.glob(os.path.join(RAIZ_TESTES, "1_TESTE_motor_do_cofre", "teste_*.py")))
GUI = sorted(glob.glob(os.path.join(RAIZ_TESTES, "2_TESTE_telas_e_botoes", "teste_*.py")))


def _rodar(cmd, cwd, limite):
    """Roda o comando, converte a ausência opcional de Hypothesis em skip e falha nos demais códigos não zero."""
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, errors="replace", timeout=limite)
    saida = (r.stdout or "") + (r.stderr or "")
    if r.returncode == 9 and any(
        linha.strip().casefold().startswith("pulado: hypothesis indisponivel")
        for linha in saida.splitlines()
    ):
        pytest.skip("Hypothesis indisponível no ambiente")
    assert r.returncode == 0, "saiu com código %d\n%s" % (r.returncode, saida[-3000:])


@pytest.mark.parametrize("arq", NUCLEO, ids=os.path.basename)
def test_nucleo(arq):
    """Teste do núcleo (criptografia, formato, gravação, concorrência, importação...)."""
    nome = os.path.basename(arq)
    if nome == "teste_memoria.py" and not sys.platform.startswith("linux"):
        pytest.skip("lê /proc/<pid>/mem: só existe no Linux")
    flags = [] if nome in ("teste_severo.py", "teste_backup.py") else ["-X", "dev", "-W", "error"]
    _rodar([sys.executable] + flags + [arq], os.path.dirname(arq), 1500)


@pytest.mark.parametrize("arq", GUI, ids=os.path.basename)
def test_interface(arq):
    """Teste da interface (Tkinter), com tela virtual no Linux."""
    py = rodar_todos.python_da_interface()
    if os.name == "nt" or os.environ.get("DISPLAY"):
        xv = []
    elif shutil.which("xvfb-run"):
        xv = ["xvfb-run", "-a", "-s", "-screen 0 1600x1000x24"]
    else:
        pytest.skip("sem tela e sem xvfb-run")
    _rodar(xv + [py, "-X", "dev", arq], os.path.dirname(arq), 400)
