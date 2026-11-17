@echo off
rem ======================================================================
rem  run_doubling_v2.bat : Doubling Test v2 (k = 10..24, 5 forks, heap 4g)
rem    N = 2^10 .. 2^24 (15 bo du lieu)
rem    Luoi: 9 cutoffs (1, 4, 7, 8, 10, 16, 30, 32, 64)
rem    Trial: 10 (k <= 16), 5 (17 <= k <= 20), 3 (21 <= k <= 24)
rem    Forks: 1..5, ghim nhan 5 (/affinity C00), typeperf song song
rem    JVM Heap: -Xms4g -Xmx4g (cho N = 2^24 = 16,777,216)
rem    scripts\run_doubling_v2.bat [--resume] [--limit-datasets N] [--results DIR] [--data DIR]
rem ======================================================================
setlocal EnableExtensions
cd /d "%~dp0.."

set "JVM_BENCH=-Xms4g -Xmx4g -XX:+UseSerialGC -XX:+AlwaysPreTouch"
set "RESUME="
set "LIMIT="
set "RESULTS_DIR=results_doubling_v2"
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
echo ======================================================================
echo  DANH SACH KIEM TRA TRUOC KHI DO (PRE-FLIGHT CHECKLIST)
echo ======================================================================
echo  1. Cam nguon AC (sac pin)
echo  2. Goi nguon: Balanced, PROCTHROTTLEMIN AC = 80%%
echo  3. Dong tat ca ung dung khac (trinh duyet, IDE, chat)
echo  4. Tat/tam dung cac dich vu mang nen (Tailscale, WARP, Radmin VPN)
echo  5. Tam dung Windows Update
echo  6. Ket qua se ghi vao: %RESULTS_DIR%
echo  7. Tien trinh se duoc ghim nhan 5 (/affinity C00)
echo  8. JVM Heap: 4GB (-Xms4g -Xmx4g)
echo ======================================================================
if not defined LIMIT (
  echo Nhan phim bat ky de bat dau do ...
  pause >nul
)

if not exist "%RESULTS_DIR%" mkdir "%RESULTS_DIR%"
call :now T_ALL0

rem ---------------------------------------------------------------- 1. compile
echo === [1/6] javac
call :now T0
javac -encoding UTF-8 -cp "lib/*;src" -d build src\*.java
if errorlevel 1 (
  echo javac FAILED
  exit /b 1
)
call :now T1
call :report %T0% %T1% "javac"

rem ---------------------------------------------------------------- 2. Bat dau typeperf
echo === Bat dau typeperf ghi nhan 5 va cac LP...
taskkill /F /IM typeperf.exe >nul 2>&1
start "typeperf" /min typeperf "\Processor Information(*)\%% Processor Performance" "\Processor Information(*)\%% Processor Utility" -si 1 -o "%RESULTS_DIR%\typeperf.csv"

rem ---------------------------------------------------------------- 3-7. Benchmark forks 1..5
for /l %%f in (1, 1, 5) do (
  echo === [%%f/5] Benchmark fork %%f (ghim nhan 5, affinity C00)
  call :bench %%f || goto fail
)

rem ---------------------------------------------------------------- Dung typeperf
taskkill /F /IM typeperf.exe >nul 2>&1

echo === Hoan tat Doubling test v2 (5 forks)!
call :now T_ALL1
call :report %T_ALL0% %T_ALL1% "TOTAL Doubling v2"
exit /b 0

:fail
taskkill /F /IM typeperf.exe >nul 2>&1
echo Doubling v2 FAILED at fork. Re-run with --resume to continue.
exit /b 1

:bench
call :now TB0
start "bench" /affinity C00 /wait java %JVM_BENCH% -cp "lib/*;build" Benchmark --fork %1 --data "%DATA_DIR%" --results "%RESULTS_DIR%" --fixed-k 1 --grid %GRID% %RESUME% %LIMIT%
if errorlevel 1 (
  echo Benchmark fork %1 FAILED
  exit /b 1
)
call :now TB1
call :report %TB0% %TB1% "Benchmark fork %1"
exit /b 0

:now
for /f %%t in ('powershell -NoProfile -Command "[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()"') do set "%~1=%%t"
exit /b 0

:report
set /a "_D=%~2-%~1"
set /a "_H=_D/3600"
set /a "_M=(_D%%3600)/60"
set /a "_S=_D%%60"
echo [%~3] %_H%h %_M%m %_S%s
exit /b 0
