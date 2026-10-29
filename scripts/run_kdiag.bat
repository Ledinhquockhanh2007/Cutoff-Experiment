@echo off
rem ======================================================================
rem  run_kdiag.bat : Chạy KDiag 3 fork tuần tự, ghim nhân vật lý 5 (/affinity C00)
rem    scripts\run_kdiag.bat [--smoke]
rem      --smoke : chạy chế độ smoke test nhanh (1 trial, 1 N)
rem ======================================================================
setlocal EnableExtensions
cd /d "%~dp0.."

set "JVM_BENCH=-Xms2g -Xmx2g -XX:+UseSerialGC -XX:+AlwaysPreTouch"
set "EXTRA_ARGS="

:parse
if "%~1"=="" goto parsed
if /i "%~1"=="--smoke" set "EXTRA_ARGS=--smoke"
if /i not "%~1"=="--smoke" (
  echo unknown option: %~1
  exit /b 2
)
shift
goto parse
:parsed

if not exist results_kdiag mkdir results_kdiag

rem ---------------------------------------------------------------- 1. compile
echo === [1/4] Biên dịch KDiag
javac -encoding UTF-8 -d build src\*.java
if errorlevel 1 (
  echo javac FAILED
  exit /b 1
)

rem ---------------------------------------------------------------- 2-4. KDiag 3 forks
echo === [2/4] KDiag fork 1 (ghim nhân 5, affinity C00)
start "kdiag" /affinity C00 /wait java %JVM_BENCH% -cp build KDiag --fork 1 %EXTRA_ARGS%
if errorlevel 1 (
  echo KDiag fork 1 FAILED
  exit /b 1
)

echo === [3/4] KDiag fork 2 (ghim nhân 5, affinity C00)
start "kdiag" /affinity C00 /wait java %JVM_BENCH% -cp build KDiag --fork 2 %EXTRA_ARGS%
if errorlevel 1 (
  echo KDiag fork 2 FAILED
  exit /b 1
)

echo === [4/4] KDiag fork 3 (ghim nhân 5, affinity C00)
start "kdiag" /affinity C00 /wait java %JVM_BENCH% -cp build KDiag --fork 3 %EXTRA_ARGS%
if errorlevel 1 (
  echo KDiag fork 3 FAILED
  exit /b 1
)

echo === Hoàn tất KDiag 3 fork!
exit /b 0
