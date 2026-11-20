@echo off
rem run_correctness.bat (T14b): chay lai CorrectnessTest tren JDK cua may (JDK 25) va ghi
rem report\_check\correctness_output.txt dung dinh dang ma report\make_tables_p2.py doc (bang t01_correctness).
rem Chay tu bat ky dau:  scripts\run_correctness.bat
rem Sau do (tu thu muc goc):  python report\make_tables_p2.py   (KHONG can chay lai gen_main.py)
rem Can: java, javac, python trong PATH; git (khong bat buoc, chi de ghi hash commit).
setlocal EnableExtensions
cd /d "%~dp0.."
set "OUT=report\_check\correctness_output.txt"

echo [1/3] Bien dich src\*.java vao build\ ...
javac -encoding UTF-8 -cp "lib/*;src" -d build src\*.java
if errorlevel 1 (
  echo LOI: javac that bai.
  exit /b 1
)

rem Dong dau cua "java -version" (java in ra stderr)
set "JV="
for /f "usebackq delims=" %%v in (`java -version 2^>^&1`) do if not defined JV set "JV=%%v"
set "GH=khong co git"
for /f %%h in ('git rev-parse --short HEAD 2^>nul') do set "GH=%%h"

echo [2/3] Ghi tieu de (UTF-8) vao %OUT% ...
set "PYTHONUTF8=1"
python -c "import os,datetime;print('# L\u1ec7nh: java -ea -cp build CorrectnessTest   (build bi\u00ean d\u1ecbch t\u1eeb src/*.java t\u1ea1i commit '+os.environ['GH']+')');print('# java.version: '+os.environ['JV']+'; m\u00e1y \u0111o (scripts/run_correctness.bat)');print('# Ng\u00e0y ch\u1ea1y: '+datetime.datetime.now(datetime.timezone.utc).strftime('%%Y-%%m-%%dT%%H:%%M:%%SZ'));print('# --- output nguy\u00ean v\u0103n ---')" > "%OUT%"
if errorlevel 1 (
  echo LOI: python khong chay duoc.
  exit /b 1
)

echo [3/3] java -ea -cp build CorrectnessTest ...
java -ea -cp build CorrectnessTest >> "%OUT%" 2>&1
set "RC=%ERRORLEVEL%"
type "%OUT%"
echo.
echo Da ghi %OUT% (ma thoat CorrectnessTest: %RC%). Tiep theo: python report\make_tables_p2.py
exit /b %RC%
