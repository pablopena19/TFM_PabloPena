@echo off
echo.
echo ============================================
echo  Variant Classifier - Setup Windows
echo ============================================
echo.

REM Detectar Python
SET PY=
py --version >nul 2>&1
if not errorlevel 1 (SET PY=py & goto :found)
python --version >nul 2>&1
if not errorlevel 1 (SET PY=python & goto :found)
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    SET PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe" & goto :found)
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    SET PY="%LOCALAPPDATA%\Programs\Python\Python311\python.exe" & goto :found)

echo ERROR: Python no encontrado.
echo Instala Python desde https://www.python.org o la Microsoft Store.
echo IMPORTANTE: marca "Add Python to PATH" durante la instalacion.
pause & exit /b 1

:found
echo [OK] Python: %PY%
%PY% --version
echo.

echo [1/3] Creando entorno virtual...
if exist venv (
    echo       Ya existe, reutilizando.
) else (
    %PY% -m venv venv
    if errorlevel 1 (echo ERROR creando venv & pause & exit /b 1)
)

echo [2/3] Instalando dependencias...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt
if errorlevel 1 (echo ERROR en dependencias & pause & exit /b 1)

echo [3/3] Configurando API key de Groq...
echo.
if exist .env (
    echo       Archivo .env ya existe.
    set /p OW="Sobreescribir? (s/n): "
    if /i not "%OW%"=="s" goto :done
)
echo Para obtener tu API key gratuita de Groq:
echo   1. Ve a https://console.groq.com
echo   2. Registrate con Google o email
echo   3. API Keys -^> Create API key
echo.
set /p GKEY="Pega tu GROQ_API_KEY: "
if "%GKEY%"=="" (echo ERROR: clave vacia & pause & exit /b 1)
echo GROQ_API_KEY=%GKEY%> .env
echo       .env creado.

:done
if not exist results mkdir results

echo.
echo ============================================
echo  Instalacion completada.
echo.
echo  Activa el entorno y ejecuta:
echo    venv\Scripts\activate
echo    python main.py --gene BRCA1 --cdna "c.5266dupC" --protein "p.Gln1756ProfsTer74"
echo ============================================
echo.
pause
