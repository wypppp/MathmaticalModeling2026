"""A 层覆盖检查 A4（预注册 V24）：原题句子 ↔ spec 的双向追溯，加附表 1 与数值参数的机器比对。

用法：python tools/a4_check.py
输入：review/A4_sentences.csv（tools/docx_sentences.py 直接从 F.docx 切出）、review/A4_trace.csv（人工映射）、spec.md
只做“覆盖是否完整、引用是否存在”的机械检查；映射是否读对，仍需他方抽审。
"""
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")
spec = (ROOT / "spec.md").read_text(encoding="utf-8")
sent = list(csv.DictReader(open(ROOT / "review/A4_sentences.csv", encoding="utf-8")))
trace = list(csv.DictReader(open(ROOT / "review/A4_trace.csv", encoding="utf-8-sig")))
problems = []

# 1. 句子表与映射表一致，且每句都有归类；非背景、结构的句子必须有 spec 引用
if [s["sid"] for s in sent] != [t["sid"] for t in trace] or any(s["text"] != t["text"] for s, t in zip(sent, trace)):
    problems.append("映射表与句子表不一致（句子表重新生成过？）")
for t in trace:
    if not t["kind"]:
        problems.append(f"{t['sid']} 未归类")
    elif t["kind"] not in ("背景", "结构") and not t["spec_ref"]:
        problems.append(f"{t['sid']}（{t['kind']}）没有 spec 引用：{t['text'][:40]}")

# 2. 引用的 spec 编号都存在
ids_in_spec = set(re.findall(r"^\| \**([ACRSGP]\d+)\**", spec, re.M)) | set(re.findall(r"\*\*(R\d+)\*\*", spec))
for x in ("P0", "P1", "P2", "P3", "P4"):
    if f"| {x} |" in spec:
        ids_in_spec.add(x)
heads = set(re.findall(r"^#{2,3} (\d+(?:\.\d+)?)", spec, re.M))
used = set()
for t in trace:
    for tok in filter(None, (x.strip() for x in t["spec_ref"].split("；"))):
        m = re.match(r"^([ACRSGP])(\d+)[–-]\1?(\d+)$", tok)
        if m:
            for i in range(int(m.group(2)), int(m.group(3)) + 1):
                used.add(f"{m.group(1)}{i}")
                if f"{m.group(1)}{i}" not in ids_in_spec:
                    problems.append(f"{t['sid']} 引用了不存在的 {m.group(1)}{i}")
            continue
        m = re.match(r"^§(\d+(?:\.\d+)?)", tok)
        if m:
            if m.group(1) not in heads:
                problems.append(f"{t['sid']} 引用了不存在的章节 §{m.group(1)}")
            continue
        if re.match(r"^[ACRSGP]\d+$", tok):
            used.add(tok)
            if tok not in ids_in_spec:
                problems.append(f"{t['sid']} 引用了不存在的 {tok}")
            continue
        problems.append(f"{t['sid']} 无法解析的引用 {tok}")

# 3. spec → 原题：A、C、S 条目的出处列必须指向原题或裁决；G 条目在 §6（自补假设）
SRC = re.compile(r"录|件|术|题|附表|核|裁|需求守恒|G0 稿")
for line in spec.splitlines():
    m = re.match(r"^\| ([ACS]\d+) \|(.*)\|\s*$", line)
    if m:
        last = m.group(2).split("|")[-1]
        if not SRC.search(last):
            problems.append(f"spec {m.group(1)} 的出处列没有原题或裁决依据：{last.strip()[:40]}")
# 没有被原题句子引用的 spec 条目：出处不在 F.docx 正文（附件表注、需求守恒）或属于 §6 自补假设，须逐条有说明
ORPHAN_OK = {"A1": "附件 2/4 的日期单元格格式（件2/4、件7 样例）", "A6": "件6 注 1、件7 注 3", "A7": "件6 注 2、3", "A8": "件7 样例",
             "C7": "需求守恒（每块恰由一个批次执行），原题未明说的隐含要求", "G8": "§6 自补假设", "G9": "§6 自补假设（录4.2 备注）", "G16": "§6 自补假设（K1 裁决）"}
orphans = sorted(ids_in_spec - used, key=lambda s: (s[0], int(s[1:])))
print("spec 中没有被任何原题句子引用的条目：", {o: ORPHAN_OK.get(o, "【无说明】") for o in orphans})
problems += [f"spec {o} 没有原题句子引用，也没有说明" for o in orphans if o not in ORPHAN_OK]

# 4. 附表 1（F.docx 原件）与 spec §3.1 的 H(u) 逐项比对，再与代码比对
import zipfile
import xml.etree.ElementTree as ET
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
with zipfile.ZipFile(ROOT / "problem/F/original/F.docx") as z:
    body = ET.fromstring(z.read("word/document.xml")).find(W + "body")
tbl = next(t for t in body.iter(W + "tbl") if "队属货物仓库编号" in "".join(x.text or "" for x in t.iter(W + "t")))
rows = [["".join(x.text or "" for x in tc.iter(W + "t")).strip() for tc in tr.iter(W + "tc")] for tr in tbl.iter(W + "tr")]
assert rows[0] == ["队属货物仓库编号", "所属需求单位编号", "可使用该仓库的其他需求单位编号"], rows[0]
rows = rows[1:]
H_doc = {}
for wh, owner, others in rows:
    for u in [owner] + [x for x in re.split(r"[,，、\s]+", others) if x]:
        H_doc.setdefault(u, set()).add(wh)
H_spec = {u: set(re.findall(r"W[A-Z]", v)) for u, v in re.findall(r"H\((U\d+)\)=\{([^}]*)\}", spec)}
if H_doc != H_spec:
    problems.append(f"附表 1 与 spec 的 H(u) 不一致：原件 {H_doc}，spec {H_spec}")
sys.path.insert(0, str(ROOT / "src"))
try:
    import f_parse
    H_code = {u: set(v) for u, v in f_parse.OWN_WH.items()}
    if H_code != H_doc:
        problems.append(f"附表 1 与 f_parse.OWN_WH 不一致：代码 {H_code}")
except Exception as e:  # noqa: BLE001
    problems.append(f"无法读取 f_parse.OWN_WH：{e}")
print(f"附表 1：{len(rows)} 个仓库、{len(H_doc)} 个单位，原件 / spec / 代码三者{'一致' if H_doc == H_spec else '不一致'}")

# 5. 附录 2、3 中的每个数值都出现在 spec 中（S120–S172）；S172 是日期格式示例，豁免
EXEMPT = {"S172": "日期格式示例“4 月 22 日至 4 月 24 日”，不是参数"}
miss = []
for s in sent[119:172]:
    if s["sid"] in EXEMPT:
        continue
    body = re.sub(r"^\d+\s*[.．]", "", s["text"])
    for num in re.findall(r"\d+(?:\.\d+)?", body):
        if not re.search(rf"(?<![\d.]){re.escape(num)}(?![\d.])", spec):
            miss.append((s["sid"], num, s["text"][:40]))
print("附录 2、3 中未出现在 spec 的数值：", miss or "无")
problems += [f"{a} 的数值 {b} 未出现在 spec：{c}" for a, b, c in miss]

kinds = {}
for t in trace:
    kinds[t["kind"]] = kinds.get(t["kind"], 0) + 1
print(f"共 {len(trace)} 句，归类：{kinds}")
print("问题：", problems or "无")
sys.exit(1 if problems else 0)
