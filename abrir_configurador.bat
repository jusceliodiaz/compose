@echo off
REM Abre o configurador em modo desenvolvimento (http://localhost:5173)
cd /d "%~dp0web"
if not exist node_modules call npm install
start "" http://localhost:5173
call npm run dev
