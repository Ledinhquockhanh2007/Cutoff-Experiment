# diag_probe.ps1 - diagnostic run for the warm-up "jump" (does NOT touch Benchmark results).
# Runs WarmupProbe with JIT/deopt/safepoint logging and samples per-CPU frequency/utility with typeperf.
#
#   powershell -ExecutionPolicy Bypass -File scripts\diag_probe.ps1 -Tag E0_1
#   powershell -ExecutionPolicy Bypass -File scripts\diag_probe.ps1 -Tag E1_pin4 -Affinity 10
#   powershell -ExecutionPolicy Bypass -File scripts\diag_probe.ps1 -Tag E4_1 -Sizes "4096,262144" -Rounds 120
#   powershell -ExecutionPolicy Bypass -File scripts\diag_probe.ps1 -Tag T1_1 -ViaCmdStart          # launch like run_all.bat
#   powershell -ExecutionPolicy Bypass -File scripts\diag_probe.ps1 -Tag T2_c0 -ViaCmdStart -Affinity 3 -Main
#       -Main: run "Benchmark --fork 1 --results diag\<Tag>\bench" instead of WarmupProbe (stop with Ctrl+C)
#
# Output: diag\<Tag>\{probe.csv, typeperf.csv, jit.log, stdout.txt, meta.txt}
# Then:   python scripts\diag_align.py --probe diag\<Tag>\probe.csv --typeperf diag\<Tag>\typeperf.csv
param(
    [Parameter(Mandatory = $true)][string]$Tag,
    [int]$Rounds = 300,
    [string]$Sizes = "65536",
    [string]$Affinity = "",          # hex mask of logical processors, e.g. "3" = LP 0+1 (core 0), "C00" = LP 10+11 (core 5)
    [switch]$NoJitLog,
    [switch]$ViaCmdStart,            # launch exactly like run_all.bat: cmd /c start "java" /b /wait /high [/affinity X] java ...
    [switch]$Main                    # run Benchmark --fork 1 (separate results dir) instead of WarmupProbe
)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$dir = "diag\$Tag"
if (Test-Path $dir) { throw "$dir exists - choose another -Tag" }
New-Item -ItemType Directory -Path $dir | Out-Null

# --- metadata: power plan, minimum processor state, java version
"tag=$Tag rounds=$Rounds sizes=$Sizes affinity=$Affinity start=$(Get-Date -Format o)" | Out-File "$dir\meta.txt" -Encoding ascii
powercfg /getactivescheme | Out-File "$dir\meta.txt" -Append -Encoding ascii
powercfg /query SCHEME_CURRENT SUB_PROCESSOR PROCTHROTTLEMIN | Select-String "Current AC" | Out-File "$dir\meta.txt" -Append -Encoding ascii
cmd /c "java -version 2>&1" | Out-File "$dir\meta.txt" -Append -Encoding ascii   # stderr via cmd: PS 5.1 + Stop would abort

# --- typeperf: 1 sample per second, all logical processors
$counters = @('"\Processor Information(*)\% Processor Performance"', '"\Processor Information(*)\% Processor Utility"')
$tp = Start-Process -FilePath typeperf -ArgumentList ($counters + @("-si", "1", "-sc", "100000", "-f", "CSV", "-y", "-o", "$dir\typeperf.csv")) `
      -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 3                     # let typeperf start before the JVM

# --- JVM (same flags as Benchmark), priority High, optional affinity
$jargs = @("-Xms2g", "-Xmx2g", "-XX:+UseSerialGC", "-XX:+AlwaysPreTouch")
if (-not $NoJitLog) {
    $log = ($dir -replace '\\', '/') + "/jit.log"
    $jargs += "-Xlog:jit+compilation=debug,deoptimization=trace,safepoint=info:file=${log}:uptime,tid"
}
if ($Main) { $jargs += @("-cp", "build", "Benchmark", "--fork", "1", "--results", "$dir\bench") }
else       { $jargs += @("-cp", "build", "WarmupProbe", "$Rounds", "$dir\probe.csv", $Sizes) }
$t0 = Get-Date
if ($ViaCmdStart) {
    $aff = if ($Affinity -ne "") { "/affinity $Affinity " } else { "" }
    $cmdline = 'start "java" /b /wait /high ' + $aff + 'java ' + ($jargs -join ' ')
    cmd /c $cmdline
    $exit = $LASTEXITCODE
} else {
    $p = Start-Process -FilePath java -ArgumentList $jargs -NoNewWindow -PassThru -RedirectStandardOutput "$dir\stdout.txt"
    $p.PriorityClass = "High"
    if ($Affinity -ne "") { $p.ProcessorAffinity = [IntPtr][Convert]::ToInt64($Affinity, 16) }
    $p.WaitForExit()
    $exit = $p.ExitCode
}
$secs = [int]((Get-Date) - $t0).TotalSeconds

Start-Sleep -Seconds 2
Stop-Process -Id $tp.Id -ErrorAction SilentlyContinue
"end=$(Get-Date -Format o) java_exit=$exit seconds=$secs via_cmd_start=$ViaCmdStart main=$Main" | Out-File "$dir\meta.txt" -Append -Encoding ascii
Write-Host "done: $dir ($secs s, exit $exit)"
