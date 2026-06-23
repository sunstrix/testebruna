@echo off
chcp 1252 >nul
title Essencia RH - Servidor Flask
color 0B

echo.
echo ============================================================================
echo   ESSENCIA RH - SERVIDOR FLASK
echo   CP FANI - Sistema de Gestao de Departamento Pessoal
echo ============================================================================
echo.

REM Define o diretorio do projeto
set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

echo [INFO] Diretorio do projeto: %PROJECT_DIR%
echo.

REM Verifica se o venv existe
if not exist "venv311\Scripts\activate.bat" (
    echo [ERRO] Ambiente virtual venv311 nao encontrado!
    echo.
    echo Execute "instalar.bat" primeiro para criar o ambiente virtual.
    echo.
    pause
    exit /b 1
)

REM Verifica se o app.py existe
if not exist "app.py" (
    echo [ERRO] Arquivo app.py nao encontrado!
    echo.
    pause
    exit /b 1
)

REM Verifica se o .env existe
if not exist ".env" (
    echo [AVISO] Arquivo .env nao encontrado!
    echo.
    echo O sistema pode nao funcionar corretamente sem o arquivo .env.
    echo Certifique-se de configurar as variaveis de ambiente.
    echo.
    pause
)

REM Ativa o ambiente virtual
echo [INFO] Ativando ambiente virtual Python 3.11...
call venv311\Scripts\activate.bat

echo [INFO] Ambiente virtual ativado!
echo.
echo ============================================================================
echo   INICIANDO SERVIDOR FLASK...
echo ============================================================================
echo.
echo   URL de acesso: http://127.0.0.1:5000
echo.
echo   Para parar o servidor, pressione: CTRL+C
echo.
echo ============================================================================
echo.

REM Inicia o aplicativo Flask
python app.py

REM Se o Flask sair, mostra mensagem
echo.
echo [INFO] Servidor Flask encerrado.
echo.
pause