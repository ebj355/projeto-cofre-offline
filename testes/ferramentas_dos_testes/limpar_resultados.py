"""Apaga os resultados da bateria ANTERIOR (testes/resultados/) e guarda cada coisa na pasta certa.
Roda sozinho no começo do Testar_Tudo / rodar_todos: bateria nova SUBSTITUI a antiga (nunca mistura 'ontem' com 'hoje').
Uso: python testes/ferramentas_dos_testes/limpar_resultados.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _resultado

if __name__ == "__main__":
    feitos = _resultado.limpar_resultados_antigos()
    print("Resultados antigos: %d item(ns) tratado(s)." % len(feitos))
    for f in feitos:
        print("  -", f)
