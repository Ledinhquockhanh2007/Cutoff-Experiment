@echo off
rem ======================================================================
rem  run_doubling.bat : Doubling test benchmark (N = 2^10..2^22, fixed K = 1, 3 forks)
rem    scripts\run_doubling.bat [--resume] [--limit-datasets N] [--results DIR] [--data DIR]
rem      --resume           : resume incomplete run in results_doubling
rem      --limit-datasets N : limit to first N datasets per fork (for testing)
rem      --results DIR      : results directory (default: results_doubling)
rem      --data DIR         : data directory (default: data_doubling)
rem  Forks 1, 2, 3 run sequentially, pinned to physical core 5 (/affinity C00).
rem  Grid: 1,4,7,8,10,16,30,32,64 (9 cutoffs)
rem ======================================================================
setlocal EnableExtensions
cd /d "%~dp0.."

set "JVM_BENCH=-Xms2g -Xmx2g -XX:+UseSerialGC -XX:+AlwaysPreTouch"
set "RESUME="
set "LIMIT="
set "RESULTS_DIR=results_doubling"
set "DATA_DIR=data_doubling"
set "GRID=1,4,7,8,10,16,30,32,64"

:parse
if "%~1"=="" goto parsed
if /i "%~1"=="--resume" (
  set "RESUME=--resume"
  shift
  goto parse
)
if /i "%~1"=="--limit-datasets" (
  set "LIMIT=--limit-datasets %~2"
  shift
  shift
  goto parse
)
if /i "%~1"=="--results" (
  set "RESULTS_DIR=%~2"
  shift
  shift
  goto parse
)
if /i "%~1"=="--data" (
  set "DATA_DIR=%~2"
  shift
  shift
  goto parse
)
echo Unknown option: %~1
echo Usage: %~nx0 [--resume] [--limit-datasets N] [--results DIR] [--data DIR]
exit /b 2

:parsed

if not exist "%RESULTS_DIR%" mkdir "%RESULTS_DIR%"
call :now T_ALL0

rem ---------------------------------------------------------------- 1. compile
echo === [1/4] javac
call :now T0
javac -encoding UTF-8 -d build src\*.java
if errorlevel 1 (
  echo javac FAILED
  exit /b 1
)
call :now T1
call :report %T0% %T1% "javac"

rem ---------------------------------------------------------------- 2-4. benchmark forks 1..3
echo === [2/4] Benchmark fork 1 (ghim nhan 5, affinity C00)
call :bench 1 || exit /b 1

echo === [3/4] Benchmark fork 2 (ghim nhan 5, affinity C00)
call :bench 2 || exit /b 1

echo === [4/4] Benchmark fork 3 (ghim nhan 5, affinity C00)
call :bench 3 || exit /b 1

echo === Hoan tat Doubling test (3 forks)!
call :now T_ALL1
call :report %T_ALL0% %T_ALL1% "TOTAL Doubling"
exit /b 0

rem ======================================================================
:bench
call :now TB0
start "bench" /affinity C00 /wait java %JVM_BENCH% -cp build Benchmark --fork %1 --data "%DATA_DIR%" --results "%RESULTS_DIR%" --fixed-k 1 --grid %GRID% %RESUME% %LIMIT%
if errorlevel 1 (
  echo Benchmark fork %1 FAILED - stop. Re-run with --resume to continue.
  exit /b 1
)
call :now TB1
call :report %TB0% %TB1% "Benchmark fork %1"
exit /b 0

:now
rem sets variable %1 = current Unix time in seconds
for /f %%t in ('powershell -NoProfile -Command "[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()"') do set "%~1=%%t"
exit /b 0

:report
rem %1 = start, %2 = end (seconds), %3 = stage name
set /a "_D=%~2-%~1"
set /a "_H=_D/3600"
set /a "_M=(_D%%3600)/60"
set /a "_S=_D%%60"
echo [%~3] %_H%h %_M%m %_S%s
exit /b 0
