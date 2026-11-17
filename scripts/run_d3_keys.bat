@echo off
rem ======================================================================
rem  run_d3_keys.bat : D3 Key Types Benchmark (Integer[], Double[], int[])
rem    Thang: 2^12, 2^16, 2^19 (random tu data_run5)
rem    Luoi: 37 cutoffs (FULL_GRID 35 cutoffs + 96, 128)
rem    Kieu khoa: integer, double, int
rem    Forks: 3 forks moi kieu khoa, ghim nhan 5 (/affinity C00)
rem    scripts\run_d3_keys.bat [--resume] [--limit-datasets N] [--results DIR] [--data DIR]
rem ======================================================================
setlocal EnableExtensions
cd /d "%~dp0.."

set "JVM_BENCH=-Xms2g -Xmx2g -XX:+UseSerialGC -XX:+AlwaysPreTouch"
set "RESUME="
set "LIMIT="
set "RESULTS_DIR=results_d3"
set "DATA_DIR=data_run5"
set "GRID=1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,40,48,64,96,128"

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
echo  6. Ket qua se ghi vao: %RESULTS_DIR%\^<key^>
echo  7. Tien trinh se duoc ghim nhan 5 (/affinity C00)
echo  8. 3 kieu khoa: integer, double, int (3 forks moi kieu)
echo ======================================================================
if not defined LIMIT (
  echo Nhan phim bat ky de bat dau do 
  pause
)

if not exist "%RESULTS_DIR%" mkdir "%RESULTS_DIR%"
call :now T_ALL0

rem ---------------------------------------------------------------- 1. compile
echo === [1/10] javac
call :now T0
javac -encoding UTF-8 -cp "lib/*;src" -d build src\*.java
if errorlevel 1 (
  echo javac FAILED
  exit /b 1
)
call :now T1
call :report %T0% %T1% "javac"

rem ---------------------------------------------------------------- 2. Bat dau typeperf
echo === Bat dau typeperf ghi nhan 5 va cac LP
taskkill /F /IM typeperf.exe >nul 2>&1
start "typeperf" /min typeperf "\Processor Information(*)\%% Processor Performance" "\Processor Information(*)\%% Processor Utility" -si 1 -y -o "%RESULTS_DIR%\typeperf_%T_ALL0%.csv"

rem ---------------------------------------------------------------- 3-11. Do 3 kieu khoa (integer, double, int)
for %%k in (integer double int) do (
  if not exist "%RESULTS_DIR%\%%k" mkdir "%RESULTS_DIR%\%%k"
  for /l %%f in (1, 1, 3) do (
    echo === Benchmark key=%%k fork %%f - ghim nhan 5, affinity C00
    call :bench %%k %%f || goto fail
  )
)

rem ---------------------------------------------------------------- Dung typeperf
taskkill /F /IM typeperf.exe >nul 2>&1

echo === Hoan tat D3 Key Types (3 keys x 3 forks)!
call :now T_ALL1
call :report %T_ALL0% %T_ALL1% "TOTAL D3 Keys"
exit /b 0

:fail
taskkill /F /IM typeperf.exe >nul 2>&1
echo D3 benchmark FAILED at fork. Re-run with --resume to continue.
exit /b 1

:bench
call :now TB0
start "bench" /affinity C00 /wait java %JVM_BENCH% -cp "lib/*;build" Benchmark --fork %2 --key %1 --data "%DATA_DIR%" --results "%RESULTS_DIR%\%1" --dists random --scales 4096,65536,524288 --grid %GRID% --fixed-k 1 %RESUME% %LIMIT%
if errorlevel 1 (
  echo Benchmark key %1 fork %2 FAILED
  exit /b 1
)
call :now TB1
call :report %TB0% %TB1% "Benchmark key %1 fork %2"
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
