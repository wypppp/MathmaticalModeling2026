"""从 F.docx 原件直接切句编号（不经过 F.md 转换稿），供 A 层覆盖检查 A4 使用。

用法：python tools/docx_sentences.py problem/F/original/F.docx > review/A4_sentences.csv
只读 word/document.xml 的段落文本；公式图片位置记为【图】。不引用 src/。
"""
import csv
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def paragraphs(path):
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    body = root.find(W + "body")
    for el in body.iter():
        if el.tag == W + "p":
            parts = []
            for node in el.iter():
                if node.tag == W + "t" and node.text:
                    parts.append(node.text)
                elif node.tag == W + "tab":
                    parts.append(" ")
                elif node.tag.endswith("}drawing") or node.tag.endswith("}pict") or node.tag.endswith("}object"):
                    parts.append("【图】")
            t = re.sub(r"\s+", " ", "".join(parts)).strip()
            if t:
                yield t


def sentences(p):
    out, buf = [], ""
    for ch in p:
        buf += ch
        if ch in "。；;！？":
            out.append(buf.strip())
            buf = ""
    if buf.strip():
        out.append(buf.strip())
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    w = csv.writer(sys.stdout)
    w.writerow(["sid", "para", "text"])
    n = 0
    for i, p in enumerate(paragraphs(sys.argv[1]), 1):
        for j, s in enumerate(sentences(p), 1):
            n += 1
            w.writerow([f"S{n:03d}", f"P{i:03d}", s])


if __name__ == "__main__":
    main()
