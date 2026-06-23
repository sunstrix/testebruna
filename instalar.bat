@echo off
chcp 1252 >nul
title Essencia RH - Instalador de Dependencias
color 0A

echo.
echo ============================================================================
echo   ESSENCIA RH - INSTALADOR DE DEPENDENCIAS
echo   CP FANI - Sistema de Gestao de Departamento Pessoal
echo ============================================================================
echo.

REM Define o diretorio do projeto
set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

echo [INFO] Diretorio do projeto: %PROJECT_DIR%
echo.

REM Verifica se o Python 3.11 esta instalado
echo [INFO] Verificando Python 3.11...
py -3.11 --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python 3.11 nao encontrado!
    echo.
    echo Por favor, instale o Python 3.11 de:
    echo https://www.python.org/downloads/release/python-3119/
    echo.
    echo Certifique-se de marcar "Add Python to PATH" durante a instalacao.
    echo.
    pause
    exit /b 1
)

py -3.11 --version
echo [OK] Python 3.11 encontrado!
echo.

REM Verifica se o venv ja existe
if exist "venv311\Scripts\activate.bat" (
    echo [INFO] Ambiente virtual venv311 ja existe.
    echo [INFO] Recriando ambiente virtual limpo...
    rmdir /s /q venv311
)

REM Cria o ambiente virtual
echo [INFO] Criando ambiente virtual Python 3.11...
py -3.11 -m venv venv311
if errorlevel 1 (
    echo [ERRO] Falha ao criar ambiente virtual!
    pause
    exit /b 1
)
echo [OK] Ambiente virtual criado com sucesso!
echo.

REM Ativa o ambiente virtual
echo [INFO] Ativando ambiente virtual...
call venv311\Scripts\activate.bat

REM Atualiza o pip
echo [INFO] Atualizando pip...
python -m pip install --upgrade pip --quiet

REM Instala as dependencias
echo [INFO] Instalando dependencias do requirements.txt...
echo.
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao instalar dependencias!
    pause
    exit /b 1
)

echo.
echo ============================================================================
echo   INSTALACAO CONCLUIDA COM SUCESSO!
echo ============================================================================
echo.
echo Proximos passos:
echo   1. Verifique se o arquivo .env esta configurado corretamente
echo   2. Execute "executar.bat" para iniciar o sistema
echo   3. Acesse http://127.0.0.1:5000 no navegador
echo.
echo Usuario padrao (se ja configurado):
echo   Usuario: admin
echo   Senha:   admin123
echo.
pause