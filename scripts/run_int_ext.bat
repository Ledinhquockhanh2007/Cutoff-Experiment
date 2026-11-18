@echo off
rem ======================================================================
rem  run_int_ext.bat : S7 int[] Extended Grid Benchmark (T11 / Muc 2)
rem    Thang: 4096, 65536, 524288 (random tu data_run5, 72 bo du lieu)
rem    Luoi: int_ext - 43 cutoffs: 1..32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 256
rem    Kieu khoa: int (MergeCutoffInt), K = 1, 6 forks, ghim nhan 5 (/affinity C00)
rem    Usage: scripts\run_int_ext.bat [--resume] [--limit-datasets N] [--results DIR] [--data DIR]
rem ======================================================================
setlocal EnableExtensions
cd /d "%~dp0.."

set "JVM_BENCH=-Xms2g -Xmx2g -XX:+UseSerialGC -XX:+AlwaysPreTouch"
set "RESUME="
set "LIMIT="
set "RESULTS_DIR=results_int_ext"
set "DATA_DIR=data_run5"

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
echo  DANH SACH KIEM TRA TRUOC KHI DO - PRE-FLIGHT CHECKLIST - S7 int_ext
echo ======================================================================
echo  1. Cam nguon AC / sac pin
echo  2. Goi nguon: Balanced, PROCTHROTTLEMIN AC = 80%%
echo  3. Dong tat ca ung dung khac: trinh duyet, IDE, chat
echo  4. Tat/tam dung cac dich vu mang nen: Tailscale, WARP, Radmin VPN
echo  5. Tam dung Windows Update
echo  6. Ket qua se ghi vao: %RESULTS_DIR%
echo  7. Tien trinh se duoc ghim nhan 5, affinity C00
echo  8. key=int, grid=int_ext 43 cutoffs, 6 forks, fixed-k=1
echo ======================================================================
if not defined LIMIT (
  echo Nhan phim bat ky de bat dau do ...
  pause >nul
)

if not exist "%RESULTS_DIR%" mkdir "%RESULTS_DIR%"
call :now T_ALL0

rem ---------------------------------------------------------------- 1. compile
echo === [1/7] javac
call :now T0
javac -encoding UTF-8 -cp "lib/*;src" -d build src\*.java
if errorlevel 1 (
  echo javac FAILED
  exit /b 1
)
call :now T1
call :report %T0% %T1% "javac"

rem ---------------------------------------------------------------- 2. typeperf
echo === Bat dau typeperf ghi nhan 5 va cac LP
taskkill /F /IM typeperf.exe >nul 2>&1
start "typeperf" /min typeperf "\Processor Information(*)\%% Processor Performance" "\Processor Information(*)\%% Processor Utility" -si 1 -y -o "%RESULTS_DIR%\typeperf_%T_ALL0%.csv"

rem ---------------------------------------------------------------- 3-8. 6 forks
for /l %%f in (1, 1, 6) do (
  echo === Benchmark key=int grid=int_ext fork %%f - ghim nhan 5, affinity C00
  call :bench %%f || goto fail
)

rem ---------------------------------------------------------------- Stop typeperf
taskkill /F /IM typeperf.exe >nul 2>&1

echo === Hoan tat S7 int_ext 6 forks!
call :now T_ALL1
call :report %T_ALL0% %T_ALL1% "TOTAL S7 int_ext"
exit /b 0

:fail
taskkill /F /IM typeperf.exe >nul 2>&1
echo S7 int_ext FAILED at fork. Re-run with --resume to continue.
exit /b 1

:bench
call :now TB0
start "bench" /affinity C00 /wait java %JVM_BENCH% -cp "lib/*;build" Benchmark --fork %1 --key int --data "%DATA_DIR%" --results "%RESULTS_DIR%" --dists random --scales 4096,65536,524288 --grid int_ext --fixed-k 1 %RESUME% %LIMIT%
if errorlevel 1 (
  echo Benchmark int_ext fork %1 FAILED
  exit /b 1
)
call :now TB1
call :report %TB0% %TB1% "Benchmark int_ext fork %1"
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
