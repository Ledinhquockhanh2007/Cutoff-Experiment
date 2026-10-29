@echo off
rem ======================================================================
rem  run_pilot.bat : pilot only (1 fork, small subset, R = 2)
rem    scripts\run_pilot.bat [--high]
rem  Output: results\pilot\{raw_fork1.csv, warmup_fork1.csv, env_fork1.txt, estimate.txt}
rem ======================================================================
setlocal EnableExtensions
cd /d "%~dp0.."

set "JVM_BENCH=-Xms2g -Xmx2g -XX:+UseSerialGC -XX:+AlwaysPreTouch"
set "RUN="
if /i "%~1"=="--high" set "RUN=start "java" /b /wait /high"

javac -encoding UTF-8 -d build src\*.java
if errorlevel 1 (
  echo javac FAILED
  exit /b 1
)
if not exist data\manifest.csv (
  echo data\manifest.csv not found - run: java -cp build DataGenerator
  exit /b 1
)
call :now T0
%RUN% java %JVM_BENCH% -cp build Benchmark --pilot
if errorlevel 1 (
  echo pilot FAILED
  exit /b 1
)
call :now T1
set /a "_D=T1-T0"
set /a "_M=_D/60"
set /a "_S=_D%%60"
echo [pilot] %_M%m %_S%s  -  estimate saved to results\pilot\estimate.txt
exit /b 0

:now
for /f %%t in ('powershell -NoProfile -Command "[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()"') do set "%~1=%%t"
exit /b 0
