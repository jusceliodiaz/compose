@echo off
REM Atualiza a sala com a imagem nova de renders\sala 2\cam7_.exr e prepara web\dist (opcional: publica na Vercel)
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set OPENCV_IO_ENABLE_OPENEXR=1
set IMAGEM=renders\sala 2\cam7_.exr
set CATALOGO=web\public\assets\catalog\sala_estar.json

if not exist "%IMAGEM%" (
  echo ERRO: nao achei "%IMAGEM%"
  goto fim
)

echo.
echo [1/4] Convertendo a imagem nova...
python tools\replace_beauty.py "%CATALOGO%" "%IMAGEM%" || goto erro

echo.
echo [2/4] Tirando as plantas das mascaras...
python tools\refine_plant_masks.py "%CATALOGO%" || goto erro
REM o replace_beauty limpa as bordas usando as mascaras: roda de novo com as mascaras ja refinadas
python tools\replace_beauty.py "%CATALOGO%" "%IMAGEM%" >nul || goto erro

echo.
echo [3/4] Gerando o site (web\dist)...
REM o build apaga a pasta dist: guarda o vinculo com a Vercel antes
if exist web\dist\.vercel move web\dist\.vercel web\.vercel_link >nul
pushd web
call npm run build >nul 2>&1 || (popd & echo    rode "cd web" e "npm run build" para ver o erro & goto erro)
popd
if exist web\.vercel_link move web\.vercel_link web\dist\.vercel >nul
python tools\prepare_dist.py || goto erro

echo.
echo Pronto! Para ver no computador: abra http://localhost:4173 (Ctrl+F5)
echo    (se o servidor nao estiver ligado: cd web e npm run preview)
echo.
choice /c SN /m "[4/4] Publicar agora na Vercel (site online)"
if errorlevel 2 goto fim
if exist web\dist\.env.local del web\dist\.env.local
pushd web\dist
call npx -y vercel@latest deploy --prod --yes || (popd & goto erro)
popd
echo.
echo Publicado: https://living-room-configurator-seven.vercel.app
goto fim

:erro
echo.
echo *** Deu erro no passo acima. Nada foi publicado. ***

:fim
echo.
pause
