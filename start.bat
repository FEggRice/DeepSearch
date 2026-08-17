@echo off
chcp 65001 >nul 2>nul
title Deep Search Agent Launcher
cd /d "%~dp0"

echo.
echo ============================================
echo     Deep Search Agent  -  one key launcher
echo ============================================
echo.

python --version >nul 2>nul
if errorlevel 1 goto try_py
set PY_CMD=python
goto python_ok

:try_py
py --version >nul 2>nul
if errorlevel 1 goto no_python
set PY_CMD=py
goto python_ok

:python_ok

echo [1/3] Checking dependencies ...
%PY_CMD% -c "import streamlit, tavily, openai, pydantic, rich" >nul 2>nul
if errorlevel 1 goto install_deps
goto deps_ok

:no_python
echo [ERROR] Python not found. Please install Python 3.9+ first.
pause
exit /b 1

:install_deps
echo [2/3] Dependencies missing, installing ...
%PY_CMD% -m pip install -r requirements.txt
if errorlevel 1 goto install_fail
echo [OK] Dependencies installed.
goto deps_ok

:install_fail
echo [ERROR] Dependency installation failed. Check your network and retry.
pause
exit /b 1

:deps_ok
echo [3/3] All ready.
echo.
echo ============================================
echo   Please choose how to run:
echo.
echo     [1]  Web UI  (Streamlit, recommended)
echo     [2]  Basic example  (command line)
echo     [3]  Advanced example (command line)
echo     [4]  Debug trace  (full data flow viewer)
echo     [0]  Exit
echo ============================================
echo.
set /p choice=Your choice [default 1]: 

if "%choice%"=="2" goto basic
if "%choice%"=="3" goto advanced
if "%choice%"=="4" goto debug
if "%choice%"=="0" goto end
goto web

:web
echo.
echo Starting Web UI ... browser will open at http://localhost:8501
%PY_CMD% -m streamlit run examples/streamlit_app.py
goto end

:basic
echo.
echo Running basic example ...
%PY_CMD% examples/basic_usage.py
goto end

:advanced
echo.
echo Running advanced example ...
%PY_CMD% examples/advanced_usage.py
goto end

:debug
echo.
echo Running debug trace (input your topic when prompted) ...
%PY_CMD% examples/debug_trace.py
goto end

:end
echo.
pause
