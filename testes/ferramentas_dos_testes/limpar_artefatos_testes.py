"""Apaga as pastas temporárias que os testes deixam para trás (cofres de mentira em %TEMP%/tmp) quando um teste é
interrompido no meio. Só toca em pastas com os PREFIXOS que os nossos testes usam e que tenham mais de N minutos
(padrão 5: nunca mexe no que um teste em andamento está usando). Nunca apaga nada fora da pasta temporária do sistema.
Uso: python testes/ferramentas_dos_testes/limpar_artefatos_testes.py [minutos]   -> grava testes/resultados/limpeza_artefatos.txt"""
import datetime, glob, os, shutil, sys, tempfile, time

PREFIXOS = ("cofre_gui_", "cofre_conc_", "cofre_gc_", "cofre_esq_", "cofre_ocu_", "cofre cam_", "cofre_ataques_",
            "cofre_aleatoriedade_", "cofre_av_", "cofre_res_", "cofre_rede_", "teste_cofre_", "symlink_",
            "acess_", "auto_", "auto2_", "base_", "base3_", "alvo_", "bk_", "ab_")
PASTA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resultados")


def main():
    minutos = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
    base = os.path.realpath(tempfile.gettempdir())
    agora, apagadas, falhas = time.time(), [], []
    for p in sorted(glob.glob(os.path.join(base, "*"))):
        nome = os.path.basename(p)
        if not os.path.isdir(p) or os.path.islink(p) or not nome.startswith(PREFIXOS):
            continue
        if not os.path.realpath(p).startswith(base + os.sep):             # nunca fora da pasta temporária
            continue
        if agora - os.path.getmtime(p) < minutos * 60:
            continue
        shutil.rmtree(p, ignore_errors=True)
        (falhas if os.path.exists(p) else apagadas).append(nome)
    texto = "Limpeza de artefatos de teste (%s)\nPasta: %s | mais velhas que %.0f min\nApagadas: %d\nNão foi possível apagar: %d %s\n" % (
        datetime.datetime.now().isoformat(timespec="seconds"), base, minutos, len(apagadas), len(falhas), falhas)
    print(texto)
    try:
        os.makedirs(PASTA, exist_ok=True)
        with open(os.path.join(PASTA, "limpeza_artefatos.txt"), "w", encoding="utf-8") as f:
            f.write(texto)
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
