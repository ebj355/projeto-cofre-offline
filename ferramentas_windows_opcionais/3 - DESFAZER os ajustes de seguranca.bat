@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_scripts_internos_nao_mexer\desfazer_seguranca.ps1"
