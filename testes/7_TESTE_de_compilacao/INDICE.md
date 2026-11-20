# Testes do EXECUTÁVEL COMPILADO (pós-compilação)

**Para que serve esta pasta:** Verificam o executável gerado: proteções PE, varredura do Defender e conexões de rede do processo. Compile o programa antes; esta pasta pode ser incluída opcionalmente no Testar Tudo com POS-COMPILACAO.

_Gerado por `testes/6_TESTE_ferramentas_dos_testes/gerar_indices.py` (não edite à mão: rode o script)._

| Arquivo | Para que serve |
|---|---|
| `06_PEFILE_EXE.bat` | Confere as proteções ASLR, DEP, High-Entropy ASLR e CFG do CofreSenhas.exe compilado. |
| `07_DEFENDER_EXE.bat` | Varre apenas o executável compilado com o Windows Defender, sem enviar dados do cofre a scanners externos. |
| `11_REDE_DO_PROCESSO.bat` | Com o CofreSenhas.exe aberto, lista as conexões TCP/UDP do processo; o esperado é nenhuma. |
| `RODAR ESTA PASTA - testes de compilacao.bat` | Roda as verificações pós-compilação: pefile, Defender e rede do processo. Grava o resumo e os relatórios individuais em testes/resultados/. Compile primeiro; se o executável ou o processo não estiverem disponíveis, registra PULADO. |
| `_achar_exe.bat` | Localiza o CofreSenhas.exe por COFRE_EXE, argumento ou caminhos padrão do projeto. |
| `verificar_pe.py` | Verifica as flags de segurança PE do executável compilado com pefile. |
