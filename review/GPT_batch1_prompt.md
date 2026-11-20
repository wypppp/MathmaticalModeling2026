# GPT 第一批复算（与路线无关，可立即做）

> 分支 `work/primary`（提交号见推送记录）。不读 `src/`；不读 `review/claude_*`、`review/A_layer_report.md`、`review/A5_compare.md`。产出推送到 `review/independent-F` 分支，放 `review/gpt_A_layer/`。

1. **V25（反写对照）**：读 `review/gemini_A5/gemini_A5_1.md`（Gemini 只看 spec v2.2 反写的题面）和原题 `problem/F/original/F.docx`。逐条列出反写稿与原题不一致的地方，并判断每一处是否已在 `spec.md` §6（自补假设）或 §7、§10–§13（裁决记录）中登记。只列不一致的条目。
2. **抽审映射表**：在 `review/A4_trace.csv`（原题 217 句 → spec 条目）中随机抽 40 句，再加上全部“约束”类句子，判断映射是否正确：一致 / 映射错 / spec 漏了 / spec 比原文松 / spec 比原文紧。
3. **R16 复核（问题 1，附件 3）**：
   - (a) 附件 3 的 27 批中，表列天数（结束日 − 开始日 + 1）等于附件 2 对应批次提报时段长度的批数（Claude 得 19/27）；
   - (b) 按录 4.3 的表中顺序、统一行动、spec §5.3 的时间规则回放，表列天数少于回放天数的批数（Claude 得 11）；
   - (c) 把规则改为“任何路段可随时出发，行驶到 16:00 停、次日 8:00 续行”，再数一次（Claude 得 3）。
   附件 2 与附件 3 的批次对应方式按你在问题 1 复算中的做法。
