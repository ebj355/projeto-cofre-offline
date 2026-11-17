# Testes que SÓ fazem sentido no Windows real

**Para que serve esta pasta:** Conferem o que o Linux só consegue simular: atributos de arquivo, permissões (ACL), DPAPI, SMBIOS, instalador, Windows Sandbox.

_Gerado por `testes/ferramentas_dos_testes/gerar_indices.py` (não edite à mão: rode o script)._

| Arquivo | Para que serve |
|---|---|
| `A - testar o instalador.bat` | Atalho de dois cliques do teste do INSTALADOR no Windows (chama teste_windows.ps1). |
| `B - testar atributos e permissoes do Windows.bat` | Atalho de dois cliques do teste NATIVO (atributos, ACL, DPAPI, SMBIOS, DLLs). Aceita a letra do pendrive: B - testar atributos e permissoes do Windows.bat H. |
| `C - testar o Windows tambem no pendrive H.bat` | Atalho que já roda o teste nativo também no pendrive H: (troque a letra dentro do arquivo se o seu for outro). |
| `D - testar no Windows Sandbox limpo.wsb` | Configuração do Windows Sandbox: abre um Windows LIMPO e descartável com o projeto copiado, para testar a instalação do zero. Opcional. |
| `instalador.Tests.ps1` | Testes Pester (PowerShell) do instalar_cofre.ps1: funções internas do instalador. Chamado por teste_windows.ps1. |
| `teste_nativo_windows.py` | Teste NATIVO no Windows real: confirma o que os testes em Linux só puderam simular. Cobre: atributos de arquivo (oculto/sistema/somente leitura), ACL NTFS (icacls do instalador), leitura do SMBIOS |
| `teste_windows.ps1` | Valida o instalador e o programa no Windows real (pastas, atributos, compilação, SmartScreen etc.). |
