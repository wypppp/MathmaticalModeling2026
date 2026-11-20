# Build the offline package for f_p3_cert4 (Windows, no install needed on target).
# Usage: powershell -ExecutionPolicy Bypass -File tools\pack_cert_offline.ps1 [-Dest D:\WYP\MM2026\cert_offline] [-SelfTest <dir>]
param(
  [string]$Dest = "D:\WYP\MM2026\cert_offline",
  [string]$SelfTest = ""
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Py = "C:\Users\Admin\AppData\Roaming\uv\python\cpython-3.12.3-windows-x86_64-none"
$Site = Join-Path $Root ".venv\Lib\site-packages"

if (Test-Path $Dest) { Remove-Item -Recurse -Force $Dest }
New-Item -ItemType Directory -Force "$Dest\src", "$Dest\job", "$Dest\selftest" | Out-Null

# 1. portable Python 3.12 (drop debug symbols, tcl, headers)
robocopy $Py "$Dest\python" /E /XF *.pdb /XD tcl include libs __pycache__ /NFL /NDL /NJH /NJS /NP | Out-Null
# 2. only the packages the worker imports (pandas, numpy, dateutil, tzdata, openpyxl, et_xmlfile, six, pytz if present)
$pk = Get-ChildItem $Site | Where-Object { $_.Name -match '^(pandas|numpy|dateutil|python_dateutil|tzdata|openpyxl|et_xmlfile|six|pytz)' }
foreach ($p in $pk) { Copy-Item -Recurse -Force $p.FullName "$Dest\python\Lib\site-packages\" }
# 3. code
foreach ($f in "f_p3_cert4.py", "f_p3.py", "f_engine.py", "f_routes.py", "f_blocks.py", "f_parse.py") { Copy-Item (Join-Path $Root "src\$f") "$Dest\src\" }
# 4. job (delta 1 bundle) and optional self-test bundle
Copy-Item (Join-Path $Root "results\F\p3_cert4\bundle.pkl"), (Join-Path $Root "results\F\p3_cert4\tasks.csv") "$Dest\job\"
if ($SelfTest -ne "") { Copy-Item "$SelfTest\bundle.pkl", "$SelfTest\tasks.csv" "$Dest\selftest\" }

# 5. launchers (ASCII only)
@'
@echo off
rem Self test: 2 vectors already decided at home. Expected total replays = 367865.
set N=%1
if "%N%"=="" set N=8
cd /d "%~dp0"
if exist selftest\out rmdir /s /q selftest\out
python\python.exe -u src\f_p3_cert4.py work %N% selftest
python\python.exe -c "import csv,glob;s=sum(int(r['n_sim'] or 0) for f in glob.glob('selftest/out/*.csv') for r in csv.DictReader(open(f,encoding='utf-8')));print('TOTAL REPLAYS',s,'OK' if s==367865 else 'MISMATCH (expected 367865)')"
pause
'@ | Set-Content -Encoding ascii "$Dest\1_selftest.bat"

@'
@echo off
rem Main run. Argument = number of worker processes (default: logical CPUs - 1, max 60).
rem Safe to stop (close window / Ctrl+C) and restart: finished tasks are skipped.
cd /d "%~dp0"
set N=%1
if "%N%"=="" set /a N=%NUMBER_OF_PROCESSORS%-1
if %N% GTR 60 set N=60
echo workers=%N%
python\python.exe -u src\f_p3_cert4.py work %N% job >> job\work.log 2>&1
'@ | Set-Content -Encoding ascii "$Dest\2_run.bat"

@'
@echo off
cd /d "%~dp0"
python\python.exe -c "import csv,glob;t=list(csv.DictReader(open('job/tasks.csv',encoding='utf-8-sig')));d=len(glob.glob('job/out/*.csv'));e=sum(float(r['est']) for r in t);print('tasks done',d,'/',len(t))"
powershell -NoProfile -Command "Get-Content job\work.log -Tail 3"
pause
'@ | Set-Content -Encoding ascii "$Dest\3_progress.bat"

Copy-Item (Join-Path $Root "tools\cert_offline_README.txt") "$Dest\README.txt"
$mb = [math]::Round(((Get-ChildItem -Recurse $Dest | Measure-Object Length -Sum).Sum) / 1MB)
Write-Output "package: $Dest  ($mb MB)"
