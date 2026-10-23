@echo off
REM Importa os passes 360 e prepara o site para visualizacao e deploy
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set OPENCV_IO_ENABLE_OPENEXR=1

echo.
echo [1/3] Processando passes da camera 360...
python tools\import_sala_360.py || goto erro

echo.
echo [2/3] Gerando o site (web\dist)...
if exist web\dist\.vercel move web\dist\.vercel web\.vercel_link >nul
pushd web
call npm run build >nul 2>&1 || (popd & echo    rode "cd web" e "npm run build" para ver o erro & goto erro)
popd
if exist web\.vercel_link move web\.vercel_link web\dist\.vercel >nul
python tools\prepare_dist.py || goto erro

echo.
echo Pronto! Para ver no computador: abra http://localhost:4173?project=sala_estar_360 (Ctrl+F5)
echo.
choice /c SN /m "[3/3] Publicar agora na Vercel (site online)"
if errorlevel 2 goto fim
if exist web\dist\.env.local del web\dist\.env.local
pushd web\dist
call npx -y vercel@latest deploy --prod --yes || (popd & goto erro)
popd
echo.
echo Publicado com sucesso!
goto fim

:erro
echo.
echo *** Deu erro no passo acima. Nada foi publicado. ***

:fim
echo.
pause
