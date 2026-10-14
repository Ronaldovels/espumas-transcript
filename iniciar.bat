@echo off
rem Abre a interface do espumas-transcript no navegador.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Ambiente nao encontrado. Siga a instalacao do README primeiro.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m espumas web
pause
