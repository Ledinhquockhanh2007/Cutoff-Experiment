@echo off
rem ======================================================================
rem  run_all.bat : full CUTOFF experiment (can be started from any folder)
rem    scripts\run_all.bat [--high] [--resume]
rem      --high   : run java at high priority (start /b /wait /high)
rem      --resume : Benchmark continues from results\raw_fork*.csv;
rem                 CountRunner is skipped if results\counts.csv exists
rem  Order: javac -> CorrectnessTest (-ea) -> DataGenerator --verify
rem          -> CountRunner -> Benchmark fork 1, 2, 3 (no -ea)
rem ======================================================================
setlocal EnableExtensions
cd /d "%~dp0.."

set "JVM_BENCH=-Xms2g -Xmx2g -XX:+UseSerialGC -XX:+AlwaysPreTouch"
set "RUN="
set "RESUME="

:parse
if "%~1"=="" goto parsed
if /i "%~1"=="--high"   set "RUN=start "java" /b /wait /high"
if /i "%~1"=="--resume" set "RESUME=--resume"
if /i not "%~1"=="--high" if /i not "%~1"=="--resume" (
  echo unknown option: %~1
  exit /b 2
)
shift
goto parse
:parsed

if not exist results mkdir results
call :now T_ALL0

rem ---------------------------------------------------------------- 1. compile
echo === [1/6] javac
call :now T0
javac -encoding UTF-8 -d build src\*.java
if errorlevel 1 (
  echo javac FAILED
  exit /b 1
)
call :now T1
call :report %T0% %T1% "javac"

rem ---------------------------------------------------------------- 2. correctness
echo === [2/6] CorrectnessTest ^(-ea^)
call :now T0
java -ea -cp build CorrectnessTest > results\correctness_test_output.txt 2>&1
if errorlevel 1 (
  type results\correctness_test_output.txt
  echo CorrectnessTest FAILED - stop.
  exit /b 1
)
findstr /b /c:"TOTAL" results\correctness_test_output.txt
call :now T1
call :report %T0% %T1% "CorrectnessTest"

rem ---------------------------------------------------------------- 3. data
echo === [3/6] DataGenerator --verify
call :now T0
if not exist data\manifest.csv (
  echo data\manifest.csv not found - generating data first
  java -cp build DataGenerator > results\datagen_output.txt 2>&1
  if errorlevel 1 (
    type results\datagen_output.txt
    echo DataGenerator FAILED - stop.
    exit /b 1
  )
)
java -cp build DataGenerator --verify > results\verify_output.txt 2>&1
if errorlevel 1 (
  type results\verify_output.txt
  echo DataGenerator --verify FAILED - stop.
  exit /b 1
)
type results\verify_output.txt
call :now T1
call :report %T0% %T1% "DataGenerator --verify"

rem ---------------------------------------------------------------- 4. counts
echo === [4/6] CountRunner
call :now T0
if defined RESUME if exist results\counts.csv (
  echo results\counts.csv exists - skipped ^(--resume^)
  goto counts_done
)
java -Xmx2g -cp build CountRunner > results\countrunner_output.txt 2>&1
if errorlevel 1 (
  type results\countrunner_output.txt
  echo CountRunner FAILED - stop.
  exit /b 1
)
findstr /c:"sha256" /c:"wrote" results\countrunner_output.txt
:counts_done
call :now T1
call :report %T0% %T1% "CountRunner"

rem ---------------------------------------------------------------- 5-6. benchmark
echo === [5/6] Benchmark: 3 forks ^(%JVM_BENCH%^)
call :bench 1 || exit /b 1
call :bench 2 || exit /b 1
call :bench 3 || exit /b 1

echo === [6/6] done
call :now T_ALL1
call :report %T_ALL0% %T_ALL1% "TOTAL"
exit /b 0

rem ======================================================================
:bench
echo --- Benchmark fork %1
call :now TB0
%RUN% java %JVM_BENCH% -cp build Benchmark --fork %1 %RESUME%
if errorlevel 1 (
  echo Benchmark fork %1 FAILED - stop. Re-run with --resume to continue.
  exit /b 1
)
call :now TB1
call :report %TB0% %TB1% "Benchmark fork %1"
exit /b 0

:now
rem sets variable %1 = current Unix time in seconds (independent of the locale format of %TIME%)
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
