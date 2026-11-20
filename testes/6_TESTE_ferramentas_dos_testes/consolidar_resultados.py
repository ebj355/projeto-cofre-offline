"""Junta os resultados individuais (testes/resultados/resultado_*.txt) em quatro relatórios, para ler tudo de uma vez:
  - resumo_testes.md     : tabela legível (um teste por linha, com contagem de [OK]/[FALHOU] e as linhas que falharam);
  - resumo_testes.json   : o mesmo em formato de máquina (para comparar uma rodada com a outra);
  - resultados.sarif     : formato SARIF 2.1.0 (só as falhas), aceito por ferramentas de revisão de código;
  - RESULTADO COMPLETO.txt: conteúdo de todos os arquivos individuais resultado_*.txt.
Uso: python testes/6_TESTE_ferramentas_dos_testes/consolidar_resultados.py        Sai com código 1 se algum teste falhou ou não puder gerar o TXT completo.
Não altera resultados individuais. Os resumos auxiliares são opcionais; falha ao gravar o TXT completo é informada."""
import datetime, glob, json, os, re, sys

PASTA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resultados")
TESTES = os.path.dirname(PASTA)
RUIM = re.compile(r"\[FALHOU\]|\[X\]|\bFAIL\b|FALHAS( v\d+)?: \[[^\]]")
INCOMPLETO = re.compile(r"\bKeyboardInterrupt\b|\bTimeoutExpired\b", re.I)
OK = re.compile(r"\[OK\]|^\s*\[\s*ok\s*\]", re.I)
PULADO = re.compile(r"^\s*\[PULADO\]", re.I)
IGNORAR = ("resultado_rodar_todos_windows.txt", "RESULTADO COMPLETO.txt")
BATERIAS = (
    ("1_TESTE_motor_do_cofre", "resultado_nucleo_windows.txt"),
    ("2_TESTE_telas_e_botoes", "resultado_teste_gui_windows.txt"),
    ("3_TESTE_ataques_simulados", "resultado_pentest_windows.txt"),
    ("4_TESTE_so_no_windows", ("resultado_teste_windows.txt", "resultado_nativo_windows.txt")),
    ("5_TESTE_ferramentas_externas", "resultado_ferramentas_externas_windows.txt"),
    ("6_TESTE_ferramentas_dos_testes", None),
    ("7_TESTE_de_compilacao", "resultado_cofre_compilado_windows.txt"),
)


def analisa(caminho):
    """Lê um resultado e devolve {nome, ok, falhou, linhas_ruins, estado}."""
    with open(caminho, encoding="utf-8", errors="replace") as f:
        linhas = f.read().splitlines()
    ruins = [l.strip()[:200] for l in linhas if RUIM.search(l)]
    interrupcoes = [l.strip()[:200] for l in linhas if INCOMPLETO.search(l)]
    if interrupcoes:
        ruins.extend("execução interrompida/incompleta: " + l for l in interrupcoes[:20])
    n_ok = sum(1 for l in linhas if OK.search(l))
    n_pulados = sum(1 for l in linhas if PULADO.search(l))
    nome = os.path.basename(caminho)[len("resultado_"):-len(".txt")]
    return {"nome": nome, "arquivo": os.path.basename(caminho), "ok": n_ok, "falhou": len(ruins),
            "pulados": n_pulados, "linhas_ruins": ruins[:20],
            "estado": "FALHOU" if ruins else "PULADO" if n_pulados and not n_ok else
                      "ok (com testes pulados)" if n_pulados else "ok"}


def gravar_resultado_completo(arqs, quando, total_ok, total_pulados, total_falhas):
    """Concatena os relatórios individuais em um TXT, sem carregar tudo na memória."""
    destino = os.path.join(PASTA, "RESULTADO COMPLETO.txt")
    with open(destino, "w", encoding="utf-8", errors="replace", newline="\n") as saida:
        saida.write("RESULTADO COMPLETO - Cofre de Senhas\n")
        saida.write("Gerado em: %s\n" % quando)
        saida.write("Arquivos individuais incluídos: %d\n" % len(arqs))
        saida.write("Verificações [OK]: %d | puladas: %d | relatórios com falha/interrupção: %d\n" %
                    (total_ok, total_pulados, total_falhas))
        saida.write("Este arquivo reúne os resultados individuais da rodada; cada arquivo original continua separado.\n")
        if not arqs:
            saida.write("\nNenhum arquivo individual resultado_*.txt foi encontrado.\n")
        for numero, caminho in enumerate(arqs, 1):
            saida.write("\n" + "=" * 78 + "\n")
            saida.write("ARQUIVO %d/%d: %s\n" % (numero, len(arqs), os.path.basename(caminho)))
            saida.write("-" * 78 + "\n")
            ultima = ""
            with open(caminho, encoding="utf-8", errors="replace") as origem:
                while True:
                    bloco = origem.read(64 * 1024)
                    if not bloco:
                        break
                    saida.write(bloco)
                    ultima = bloco[-1]
            if ultima not in ("\n", "\r"):
                saida.write("\n")
    return destino


def main():
    arqs = [a for a in sorted(glob.glob(os.path.join(PASTA, "resultado_*.txt"))) if os.path.basename(a) not in IGNORAR]
    itens = [analisa(a) for a in arqs]
    pastas = []
    for pasta, esperado in BATERIAS:
        caminho_pasta = os.path.join(TESTES, pasta)
        arquivos = sorted(glob.glob(os.path.join(caminho_pasta, "teste_*.py"))) if os.path.isdir(caminho_pasta) else []
        if pasta == "6_TESTE_ferramentas_dos_testes":
            arquivos = [a for a in arquivos if os.path.basename(a) != "test_pytest.py"]
        elif pasta == "7_TESTE_de_compilacao":
            arquivos = sorted(
                a for a in glob.glob(os.path.join(caminho_pasta, "*.bat"))
                if os.path.basename(a) != "RODAR ESTA PASTA - testes de compilacao.bat"
            )
        resultados = esperado if isinstance(esperado, tuple) else (esperado,) if esperado else ()
        presentes = [nome for nome in resultados if os.path.exists(os.path.join(PASTA, nome))]
        pastas.append({
            "pasta": pasta,
            "arquivos_de_teste": len(arquivos),
            "arquivos_resultado": list(resultados),
            "resultados_presentes": presentes,
        })
    quando = datetime.datetime.now().isoformat(timespec="seconds")
    ruins = [i for i in itens if i["estado"] == "FALHOU"]
    total_ok = sum(i["ok"] for i in itens)
    total_pulados = sum(i["pulados"] for i in itens)
    md = ["# Resumo dos testes", "", "Gerado em %s | %d resultado(s) | %d verificações [OK] | %d resultado(s) com falha ou interrupção" % (
        quando, len(itens), total_ok, len(ruins)) + " | %d teste(s) pulado(s)" % total_pulados, "",
        "Todas as baterias são gravadas diretamente em `testes/resultados/`, sem subpastas por rodada.", "",
        "| Pasta | Testes encontrados | Resultado |", "|---|---:|---|"]
    for pasta in pastas:
        if pasta["pasta"] == "6_TESTE_ferramentas_dos_testes":
            estado = "ferramentas auxiliares; não é bateria"
        elif pasta["pasta"] == "7_TESTE_de_compilacao" and not pasta["resultados_presentes"]:
            estado = "opcional; não executada"
        elif not pasta["arquivos_resultado"]:
            estado = "sem resultado configurado"
        elif len(pasta["resultados_presentes"]) == len(pasta["arquivos_resultado"]):
            estado = "presente"
        else:
            estado = "resultado(s) presente(s): %d/%d" % (
                len(pasta["resultados_presentes"]), len(pasta["arquivos_resultado"]))
        md.append("| %s | %d | %s |" % (pasta["pasta"], pasta["arquivos_de_teste"], estado))
    md += ["", "| Teste | Estado | [OK] | Pulados | Falhas |", "|---|---|---:|---:|---:|"]
    for i in itens:
        estado = "**FALHOU**" if i["estado"] == "FALHOU" else "**PULADO**" if i["estado"] == "PULADO" else i["estado"]
        md.append("| %s | %s | %d | %d | %d |" % (
            i["nome"], estado, i["ok"], i["pulados"], i["falhou"]))
    if ruins:
        md += ["", "## O que falhou"]
        for i in ruins:
            md += ["", "### " + i["nome"]] + ["- `%s`" % l.replace("`", "'") for l in i["linhas_ruins"]]
    md += ["", "TXT com os resultados individuais: `testes/resultados/RESULTADO COMPLETO.txt`.",
           "Detalhes completos (saída inteira, tracebacks): `testes/resultados/log_depuracao.txt`."]
    sarif = {"version": "2.1.0", "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
             "runs": [{"tool": {"driver": {"name": "testes-cofre-de-senhas", "rules": [{"id": "TESTE-FALHOU"}]}},
                       "results": [{"ruleId": "TESTE-FALHOU", "level": "error",
                                    "message": {"text": "%s: %s" % (i["nome"], l)},
                                    "locations": [{"physicalLocation": {"artifactLocation": {"uri": "testes/resultados/" + i["arquivo"]}}}]}
                                   for i in ruins for l in i["linhas_ruins"]]}]}
    print("\n".join(md[:4]))
    try:
        os.makedirs(PASTA, exist_ok=True)
        with open(os.path.join(PASTA, "resumo_testes.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(md) + "\n")
        with open(os.path.join(PASTA, "resumo_testes.json"), "w", encoding="utf-8") as f:
            json.dump({"gerado_em": quando, "pastas_testadas": pastas, "testes": itens}, f, ensure_ascii=False, indent=1)
        with open(os.path.join(PASTA, "resultados.sarif"), "w", encoding="utf-8") as f:
            json.dump(sarif, f, ensure_ascii=False, indent=1)
    except OSError as ex:
        print("(não foi possível gravar os relatórios: %s)" % ex)
    completo_ok = False
    try:
        gravar_resultado_completo(arqs, quando, total_ok, total_pulados, len(ruins))
        completo_ok = True
    except OSError as ex:
        print("ERRO: não foi possível gerar RESULTADO COMPLETO.txt: %s" % ex, file=sys.stderr)
    return 1 if ruins or not completo_ok else 0


if __name__ == "__main__":
    sys.exit(main())
