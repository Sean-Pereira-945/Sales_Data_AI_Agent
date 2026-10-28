@echo off
REM ====================================================================
REM  Sales Intelligence Platform - one-click local launcher (Windows)
REM  Starts the FastAPI backend and the Vite frontend, each in
REM  its own window, then opens the dashboard in your browser.
REM
REM  Usage:   start.bat            (backend starts at :8000)
REM           start.bat 8010       (backend starts at :8010)
REM  If the requested port is unavailable, the next available port is used.
REM  The frontend proxy follows the chosen backend port automatically.
REM  Close the two opened windows to stop the servers.
REM ====================================================================
setlocal
set "ROOT=%~dp0"

REM --- Backend -----------------------------------------------------------
set "PY=%ROOT%backend\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo [ERROR] Backend virtual environment not found:
  echo         %PY%
  echo(
  echo Create it first:
  echo         cd backend
  echo         python -m venv .venv
  echo         .venv\Scripts\python -m pip install -e ".[dev]"
  echo(
  pause
  exit /b 1
)

set "BACKEND_PORT=8000"
if not "%~1"=="" set "BACKEND_PORT=%~1"
set "REQUESTED_BACKEND_PORT=%BACKEND_PORT%"

REM Probe the port with Python so occupied and Windows-reserved ports are skipped.
:find_backend_port
"%PY%" -c "import socket,sys; s=socket.socket(socket.AF_INET,socket.SOCK_STREAM); s.bind(('127.0.0.1',int(sys.argv[1]))); s.close()" %BACKEND_PORT% >nul 2>&1
if not errorlevel 1 goto backend_port_available
if %BACKEND_PORT% GEQ 65535 (
  echo [ERROR] No available backend port was found.
  pause
  exit /b 1
)
set /a BACKEND_PORT+=1 >nul
goto find_backend_port

:backend_port_available
if not "%BACKEND_PORT%"=="%REQUESTED_BACKEND_PORT%" (
  echo [WARN] Backend port %REQUESTED_BACKEND_PORT% is unavailable.
  echo        Using available port %BACKEND_PORT% instead.
)

REM The Vite dev proxy reads this (see vite.config.ts); child windows inherit it.
set "VITE_API_TARGET=http://127.0.0.1:%BACKEND_PORT%"

echo(
echo  Sales Intelligence Platform - starting locally (backend port %BACKEND_PORT%)...
echo(

if not exist "%ROOT%.env" (
  echo [WARN] No .env at the repo root - the backend needs DATABASE_URL.
  echo        Copy .env.example to .env and fill it in.
  echo(
)

cd /d "%ROOT%backend"
start "Sales Intel - Backend (:%BACKEND_PORT%)" cmd /k .venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port %BACKEND_PORT%

REM --- Frontend ----------------------------------------------------------
set "FRONTEND_PORT=5173"
REM Probe the frontend port with the same Python environment.
:find_frontend_port
"%PY%" -c "import socket,sys; s=socket.socket(socket.AF_INET,socket.SOCK_STREAM); s.bind(('127.0.0.1',int(sys.argv[1]))); s.close()" %FRONTEND_PORT% >nul 2>&1
if not errorlevel 1 goto frontend_port_available
if %FRONTEND_PORT% GEQ 65535 (
  echo [ERROR] No available frontend port was found.
  pause
  exit /b 1
)
set /a FRONTEND_PORT+=1 >nul
goto find_frontend_port

:frontend_port_available
if not "%FRONTEND_PORT%"=="5173" (
  echo [WARN] Frontend port 5173 is unavailable.
  echo        Using available port %FRONTEND_PORT% instead.
)

cd /d "%ROOT%frontend"
where npm >nul 2>nul
if errorlevel 1 (
  echo [ERROR] npm not found on PATH. Install Node.js 18+ and retry.
  pause
  exit /b 1
)
if not exist "node_modules" (
  echo Installing frontend dependencies ^(first run only^)...
  call npm install
)
start "Sales Intel - Frontend (:%FRONTEND_PORT%)" cmd /k npm run dev -- --host 127.0.0.1 --port %FRONTEND_PORT%

REM --- Open the dashboard once Vite has had a moment to boot --------------
timeout /t 6 /nobreak >nul
start "" http://127.0.0.1:%FRONTEND_PORT%

echo(
echo  Backend : http://localhost:%BACKEND_PORT%/docs
echo  Frontend: http://127.0.0.1:%FRONTEND_PORT%   ^(opening in your browser^)
echo(
echo  Two terminal windows were opened - close them to stop the servers.
echo(
endlocal
