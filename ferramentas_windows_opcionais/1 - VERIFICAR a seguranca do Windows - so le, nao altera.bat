@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_scripts_internos_nao_mexer\verificar_seguranca.ps1"
