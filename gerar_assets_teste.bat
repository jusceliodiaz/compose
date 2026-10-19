@echo off
REM Gera a sala de teste sintética e o catálogo (Marcos 1 e 2)
cd /d "%~dp0"
python -m pip install -r tools\requirements.txt
python tools\make_test_assets.py
pause
