@echo off
rem ======================================================================
rem  run_jmh_v2.bat : JMH v2 Diagnostic Benchmark (T11 / S6 + Phu luc A1-A3)
rem    Run 1: reset=none, input={same,fresh}, profile={pure,mixed} (48 configs x 3 forks)
rem           -> jmh_v2.json, jmh_v2_console.txt
rem    Run 2: reset=gc, profile=mixed, input={same,fresh} (24 configs x 3 forks)
rem           -> jmh_v2_gc.json, jmh_v2_gc_console.txt
rem    N: 4096, 65536, 524288  |  cutoff: 1, 7, 10, 30
rem    Warmup: 5x1s, Measurement: 10x1s, Mode: AverageTime
rem    Pinned physical core 5 (/affinity C00), typeperf across BOTH runs
rem    Usage: scripts\run_jmh_v2.bat [--quick] [--results DIR]
rem ======================================================================
setlocal EnableExtensions
cd /d "%~dp0.."

set "JVM_ARGS=-Xms2g -Xmx2g -XX:+UseSerialGC -XX:+AlwaysPreTouch"
set "RESULTS_DIR=results_jmh_v2"
set "JMH_BENCH=bench\.MergeCutoffBenchmarkV2\.sort"
set "JMH_OPTS_RUN1=-f 3 -wi 5 -i 10 -r 1s -w 1s -p reset=none"
set "JMH_OPTS_RUN2=-f 3 -wi 5 -i 10 -r 1s -w 1s -p reset=gc -p profile=mixed"
set "QUICK="

:parse
if "%~1"=="" goto parsed
if /i "%~1"=="--quick" (
  set "QUICK=1"
  shift
  goto parse
)
if /i "%~1"=="--results" (
  set "RESULTS_DIR=%~2"
  shift
  shift
  goto parse
)
echo Unknown option: %~1
echo Usage: %~nx0 [--quick] [--results DIR]
exit /b 2

:parsed
if defined QUICK (
  set "JMH_OPTS_RUN1=-f 0 -wi 0 -i 1 -r 100ms -p n=4096 -p cutoff=1 -p reset=none"
  set "JMH_OPTS_RUN2=-f 0 -wi 0 -i 1 -r 100ms -p n=4096 -p cutoff=1 -p reset=gc -p profile=mixed"
)
echo ======================================================================
echo  DANH SACH KIEM TRA TRUOC KHI DO - PRE-FLIGHT CHECKLIST - S6 JMH v2
echo ======================================================================
echo  1. Cam nguon AC / sac pin
echo  2. Goi nguon: Balanced, PROCTHROTTLEMIN AC = 80%%
echo  3. Dong tat ca ung dung khac: trinh duyet, IDE, chat
echo  4. Tat/tam dung cac dich vu mang nen: Tailscale, WARP, Radmin VPN
echo  5. Tam dung Windows Update
echo  6. Ket qua se ghi vao: %RESULTS_DIR%
echo  7. Tien trinh se duoc ghim nhan 5, affinity C00
echo  8. Run 1: reset=none 48 configs x 3 forks; Run 2: reset=gc mixed 24 configs x 3 forks
echo ======================================================================
if not defined QUICK (
  echo Nhan phim bat ky de bat dau do ...
  pause >nul
)

if not exist "%RESULTS_DIR%" mkdir "%RESULTS_DIR%"
call :now T_ALL0

rem ---------------------------------------------------------------- 1. compile
echo === [1/4] javac core and JMH v2
call :now T0
javac -encoding UTF-8 -cp "lib/*;src" -d build src\*.java
if errorlevel 1 (
  echo javac core FAILED
  exit /b 1
)
if not exist jmh\build mkdir jmh\build
if not exist jmh\src_gen mkdir jmh\src_gen
javac -encoding UTF-8 -cp "lib/*;build" -processorpath "lib/jmh-core-1.37.jar;lib/jmh-generator-annprocess-1.37.jar" -s jmh/src_gen -d jmh/build jmh/src/bench/*.java jmh/src/*.java
if errorlevel 1 (
  echo javac JMH FAILED
  exit /b 1
)
call :now T1
call :report %T0% %T1% "javac"

rem ---------------------------------------------------------------- 2. typeperf
echo === [2/4] Bat dau typeperf ghi nhan 5 va cac LP
taskkill /F /IM typeperf.exe >nul 2>&1
start "typeperf" /min typeperf "\Processor Information(*)\%% Processor Performance" "\Processor Information(*)\%% Processor Utility" -si 1 -y -o "%RESULTS_DIR%\typeperf_%T_ALL0%.csv"

rem ---------------------------------------------------------------- 3. Run 1: reset=none (48 configs)
echo === [3/4] Run 1: JMH v2 reset=none - ghim nhan 5, affinity C00
call :now TB1_0
start "bench" /affinity C00 /wait java %JVM_ARGS% -cp "jmh/build;build;lib/*" org.openjdk.jmh.Main %JMH_BENCH% %JMH_OPTS_RUN1% -jvmArgs "%JVM_ARGS%" -rf json -rff "%RESULTS_DIR%\jmh_v2.json" -o "%RESULTS_DIR%\jmh_v2_console.txt"
if errorlevel 1 (
  echo JMH v2 Run 1 FAILED
  taskkill /F /IM typeperf.exe >nul 2>&1
  exit /b 1
)
call :now TB1_1
call :report %TB1_0% %TB1_1% "JMH v2 Run 1 reset=none"

rem ---------------------------------------------------------------- 4. Run 2: reset=gc, profile=mixed (24 configs)
echo === [4/4] Run 2: JMH v2 reset=gc profile=mixed - ghim nhan 5, affinity C00
call :now TB2_0
start "bench" /affinity C00 /wait java %JVM_ARGS% -cp "jmh/build;build;lib/*" org.openjdk.jmh.Main %JMH_BENCH% %JMH_OPTS_RUN2% -jvmArgs "%JVM_ARGS%" -rf json -rff "%RESULTS_DIR%\jmh_v2_gc.json" -o "%RESULTS_DIR%\jmh_v2_gc_console.txt"
if errorlevel 1 (
  echo JMH v2 Run 2 FAILED
  taskkill /F /IM typeperf.exe >nul 2>&1
  exit /b 1
)
call :now TB2_1
call :report %TB2_0% %TB2_1% "JMH v2 Run 2 reset=gc mixed"

rem ---------------------------------------------------------------- Stop typeperf
taskkill /F /IM typeperf.exe >nul 2>&1

echo === Hoan tat JMH v2 Run 1 + Run 2! Ket qua trong: %RESULTS_DIR%
call :now T_ALL1
call :report %T_ALL0% %T_ALL1% "TOTAL JMH v2"
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
