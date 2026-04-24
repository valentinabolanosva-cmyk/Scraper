@echo off
setlocal
chcp 65001 >nul
title Sistema Automatico - La Polemica Del Huila
color 0B

pushd "%~dp0"

echo.
echo =======================================================
echo          SISTEMA DE SCRAPING Y ANALITICA V3
echo =======================================================
echo.

echo [Paso 1/3] Ejecutando el Scraper de Facebook...
python scraper.py
if errorlevel 1 (
    echo.
    echo [!] El scraper fallo con codigo %errorlevel%. Abortando pipeline.
    goto :error
)

echo.
echo [Paso 2/3] Ejecutando Inteligencia de Sentimientos...
python analizador.py
if errorlevel 1 (
    echo.
    echo [!] El analizador fallo con codigo %errorlevel%. Abortando pipeline.
    goto :error
)

echo.
echo [Paso 3/3] Sincronizando datos con Supabase...
python subir_supabase.py
if errorlevel 1 (
    echo.
    echo [!] La subida a Supabase fallo con codigo %errorlevel%.
    echo     Revisa .env (SUPABASE_URL y SUPABASE_KEY).
    goto :error
)

echo.
echo =======================================================
echo          TODO ACTUALIZADO CORRECTAMENTE
echo =======================================================
echo.
popd
endlocal
pause
exit /b 0

:error
echo.
echo =======================================================
echo          PIPELINE INTERRUMPIDO
echo =======================================================
echo.
popd
endlocal
pause
exit /b 1
