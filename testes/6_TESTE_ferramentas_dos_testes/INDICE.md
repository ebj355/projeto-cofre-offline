# Ferramentas COMPARTILHADAS pelos testes

**Para que serve esta pasta:** Não são testes do cofre: são os executores (`rodar_*`), os ajudantes (`_resultado`, `_util_mem`), a limpeza, a cobertura e os relatórios. Também os documentos do plano de testes.

_Gerado por `testes/6_TESTE_ferramentas_dos_testes/gerar_indices.py` (não edite à mão: rode o script)._

| Arquivo | Para que serve |
|---|---|
| `_cache_testes.py` | Prepara cache isolado para uma execução e remove-o ao encerrar. |
| `_resultado.py` | Auxiliar dos testes (não é um teste): faz o teste gravar o SEU PRÓPRIO arquivo de resultado em testes/resultados/resultado_<nome-do-teste>.txt, além de mostrar tudo na tela como sempre. |
| `_util_mem.py` | Auxiliar dos testes (não é um teste): pico de memória do processo em KB, no Linux (resource) e no Windows (psapi). |
| `cobertura_codigo.py` | COBERTURA DE CÓDIGO (coverage.py): quais linhas e ramificações de cofre_senhas.py os testes realmente executam. Para quê: achar blocos de tratamento de erro importantes (falha de descriptografia, timeout de E/S em pendrive, queda no meio |
| `cobertura_codigo_windows.bat` | Atalho de dois cliques para medir a cobertura de código no Windows (chama cobertura_codigo.py). Fora do Testar_Tudo de propósito: é lento. |
| `consolidar_resultados.py` | Junta os resultados individuais (testes/resultados/resultado_*.txt) em três relatórios, para ler tudo de uma vez: - resumo_testes.md     : tabela legível (um teste por linha, com contagem de [OK]/[FALHOU] e as linhas que falharam); |
| `gerar_indices.py` | Gera o INDICE.md de cada pasta de testes: uma linha por arquivo dizendo PARA QUE SERVE (primeira linha do texto de abertura de cada .py; descrição escrita à mão para .bat/.ps1/.md) e POR QUE está naquela pasta. |
| `limpar_artefatos_testes.py` | Apaga as pastas temporárias que os testes deixam para trás (cofres de mentira em %TEMP%/tmp) quando um teste é interrompido no meio. Só toca em pastas com os PREFIXOS que os nossos testes usam e que tenham mais de N minutos |
| `limpar_resultados.py` | Apaga os resultados da bateria ANTERIOR (testes/resultados/) e guarda cada coisa na pasta certa. Roda sozinho no começo do Testar_Tudo / rodar_todos: bateria nova SUBSTITUI a antiga (nunca mistura 'ontem' com 'hoje'). |
| `rodar_pip_audit.py` | Executa pip-audit com limite de tempo e sem deixar o BAT preso aguardando a rede. |
| `rodar_todos.py` | Executa TODOS os testes do cofre e mostra um resumo. Uso (na pasta do projeto): |
| `rodar_todos_windows.bat` | Roda as 6 baterias no Windows; a pasta 7 é opcional e pode ser incluída com POS-COMPILACAO, depois de compilar o executável. Junta os resultados em testes/resultados/. |
| `test_pytest.py` | Ponte OPCIONAL para o pytest (cada teste vira um caso do pytest). Não é usada pelo Testar_Tudo. |
