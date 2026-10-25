@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

rem ------------------------------------------------------------------
rem  Запуск CodeQuest из исходников.
rem  Папка runtime\ — это Python Embeddable для запуска КОДА УЧЕНИКА:
rem  в нём нет pywebview/pywinpty, поэтому само приложение через него
rem  не запускается — нужен обычный Python 3.10+ с зависимостями.
rem ------------------------------------------------------------------

rem --- 1. Виртуальное окружение проекта, если оно есть ---
if exist ".venv\Scripts\pythonw.exe" (
    set "PYW=%~dp0.venv\Scripts\pythonw.exe"
) else if exist "venv\Scripts\pythonw.exe" (
    set "PYW=%~dp0venv\Scripts\pythonw.exe"
) else (
    set "PYW="
)

if defined PYW goto :check_deps

rem --- 2. Системный Python ---
where pythonw >nul 2>nul
if errorlevel 1 goto :no_python
set "PYW=pythonw"

:check_deps
rem Проверка берёт ровно тот интерпретатор, которым потом запускаем.
"%PYW%" -c "import webview, winpty" >nul 2>nul
if errorlevel 1 goto :no_deps

start "" "%PYW%" "%~dp0main.py"
exit /b 0

:no_python
echo CodeQuest не нашла Python 3.10+.
echo.
echo Установите Python с https://www.python.org/downloads/
echo и на первом шаге включите галочку "Add python.exe to PATH".
echo.
pause
exit /b 1

:no_deps
echo CodeQuest не хватает библиотек pywebview и pywinpty.
echo.
echo Установите их одной командой:
echo     pip install -r requirements.txt
echo.
echo После этого запустите этот файл снова.
echo.
pause
exit /b 1
