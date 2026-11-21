"""把 f_p3_cert4 的任务表按预计回放数拆成两份（离线服务器 / 本机），并生成服务器附加包。

用法：python tools/cert4_split.py <任务目录> <服务器份额 0–1> <附加包目录> <作业名>
  例：python tools/cert4_split.py results/F/p3_cert4_d2 0.75 D:/WYP/MM2026/cert_offline_d2 job_d2
产出：
  <任务目录>/local/{bundle.pkl,tasks.csv}   本机：python src/f_p3_cert4.py work 18 <任务目录>/local
  <附加包目录>/<作业名>/{bundle.pkl,tasks.csv} 与 4_run_<作业名>.bat、5_progress_<作业名>.bat（拷进服务器上已有的 cert_offline 文件夹）
合并：把两边的 out/*.csv 都放进 <任务目录>/out/，再 CERT4_OUT=<任务目录> python src/f_p3_cert4.py merge
"""
import csv
import shutil
import sys
from pathlib import Path

base, share, addon, job = Path(sys.argv[1]), float(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
with open(base / "tasks.csv", encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))
fields = list(rows[0].keys())
srv, loc, ws, wl = [], [], 0.0, 0.0
for r in sorted(rows, key=lambda r: -float(r["est"])):  # 贪心：哪边相对份额落后就给哪边
    e = float(r["est"])
    if ws / share <= wl / (1 - share):
        srv.append(r); ws += e
    else:
        loc.append(r); wl += e


def dump(rs, d):
    d.mkdir(parents=True, exist_ok=True)
    shutil.copy(base / "bundle.pkl", d / "bundle.pkl")
    with open(d / "tasks.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rs)


dump(loc, base / "local")
if addon.exists():
    shutil.rmtree(addon)
dump(srv, addon / job)
(addon / f"4_run_{job}.bat").write_text(
    "@echo off\r\nrem Run after the delta-1 job is finished. Same usage as 2_run.bat.\r\n"
    'cd /d "%~dp0"\r\nset N=%1\r\nif "%N%"=="" set /a N=%NUMBER_OF_PROCESSORS%-1\r\nif %N% GTR 60 set N=60\r\necho workers=%N%\r\n'
    f"python\\python.exe -u src\\f_p3_cert4.py work %N% {job} >> {job}\\work.log 2>&1\r\n", encoding="ascii")
(addon / f"5_progress_{job}.bat").write_text(
    '@echo off\r\ncd /d "%~dp0"\r\n'
    f"python\\python.exe -c \"import csv,glob;t=list(csv.DictReader(open('{job}/tasks.csv',encoding='utf-8-sig')));print('tasks done',len(glob.glob('{job}/out/*.csv')),'/',len(t))\"\r\n"
    f'powershell -NoProfile -Command "Get-Content {job}\\work.log -Tail 3"\r\npause\r\n', encoding="ascii")
print(f"服务器 {len(srv)} 个任务，预计回放 {ws:.3e}；本机 {len(loc)} 个任务，预计回放 {wl:.3e}")
