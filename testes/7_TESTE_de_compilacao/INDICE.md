# Testes da Arca — executável compilado

**Para que serve esta pasta:** Verificam o executável gerado: proteções PE, varredura do Defender e conexões de rede do processo. Compile o programa antes; esta pasta é incluída automaticamente no Testar Tudo.

_Gerado por `testes/6_TESTE_ferramentas_dos_testes/gerar_indices.py` (não edite à mão: rode o script)._

| Arquivo | Para que serve |
|---|---|
| `06_PEFILE_EXE.bat` | Confere as proteções ASLR, DEP, High-Entropy ASLR e CFG do CofreSenhas.exe compilado. |
| `07_DEFENDER_EXE.bat` | Varre apenas o executável compilado com o Windows Defender, sem enviar dados do cofre a scanners externos; registra PULADO se o Defender estiver desativado ou uma política de segurança impedir a verificacao. |
| `11_REDE_DO_PROCESSO.bat` | Com o CofreSenhas.exe aberto, lista as conexões TCP/UDP do processo; o esperado é nenhuma. |
| `RODAR ESTA PASTA - testes de compilacao.bat` | Roda as verificações pós-compilação: pefile, Defender e rede do processo. Grava o resumo e os relatórios individuais em testes/resultados/. Compile primeiro; se o executável, processo, Defender ou a política de segurança impedirem a verificação, registra PULADO sem contornar o bloqueio. |
| `_achar_exe.bat` | Localiza CofreSenhas.exe por COFRE_EXE, argumento, raiz do drive do pendrive ou caminhos padrão do projeto. |
| `testar_rede_processo.ps1` | Abre uma instância temporária do executável, confere conexões TCP/UDP e encerra apenas os processos dessa instância. |
| `teste_exe_visual_smoke_windows.py` | Smoke visual do CofreSenhas.exe COMPILADO (so Windows). Abre o .exe apontando para um cofre temporario (o seu cofre real NAO e tocado), espera a janela principal |
| `verificar_pe.py` | Verifica as flags de segurança PE do executável compilado com pefile. |
