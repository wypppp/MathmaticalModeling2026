"""从原始工作簿复算。运行 python review/gpt_v23b/check.py。"""
from pathlib import Path
import sys

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT.parent/'gpt_v23'))
import audit

original_replay = audit.replay


def replay(plans, stops, distances, all_fcfs=True):
    return original_replay(plans, stops, distances, all_fcfs=True)


def main():
    audit.OUT = OUT
    # 保留上一版的逐批明细输出，两个方案均强制走全仓 FCFS 分支。
    audit.replay = replay
    for n in (3, 4):
        audit.audit(n)


if __name__ == '__main__':
    main()
