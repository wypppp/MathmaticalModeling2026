# 当前状态（state.md）

> 两次演练已归档：`archive/rehearsal1_2026B/`、`archive/rehearsal2_2026C/`（含复盘与优秀论文对照）。
> **新窗口先读 `process/比赛作战手册.md`。**

## 当前
- 阶段：**G0 读题（四方独立）进行中**，题目 F（货物调运统筹优化），2026-11-19 定题
- 主工程方 + 整合者：本地 Claude Code（可用 Gurobi）；审查方：GPT；第三方：Gemini 等（局外人）
- 目标：特等奖；赛期 5 天；**今晚 spec 冻结**
- 分支：`work/primary`（尚未提交，等人确认后提交并推送）

## 已完成（Claude Code）
- 原件归位：`problem/F/original/F.docx`、`problem/F/original/附件/`（8 个 xlsx）
- 转换稿 `problem/F/F.md`（两处公式图已渲染核对，图在 `problem/F/figs/`）；数据摘要 `problem/F/数据摘要.md`
- 解析器 `src/f_parse.py`（路径改为 original/附件；修复附件4 半角括号导致收发方解析失败），长表在 `results/F/parsed/`
- 独立读题稿 `review/claude_G0_spec.md`（未读 GPT 稿、人的笔记、选题目录）

## 下一步
1. 人：把仓库推上去，让 GPT 按手册 §6 模板写 `review/gpt_G0_spec.md`；第三方写盲点稿（附 `problem/F/数据摘要.md`，注明提交号）
2. Claude Code：三方稿到齐后整理 `review/G0_compare.md` 裁决单 → GPT 审转述 → 人裁决 → `spec.md` v1 → GPT 审公式
3. 等稿期间 Claude Code 可先做：问题 1 的件2→件3 逐批对照表、只读结果表的独立检查器骨架

## 决策记录
| 日期 | 决策 | 理由 | 决策人 |
|---|---|---|---|
| 2026-11-19 | 选 F 题 | 选题模型报告（`chooseQusetion/`） | 人 |

## 未解决问题
- 附件 2–8 与 F.docx 的修改时间是今天 18:33–18:55（附件 1 是 9 月 19 日），可能被打开后另存过；建议与官网下载的原件核对一次
- `problem/` 下仍有演练目录 2026B、2026C（不影响 F 题）
- 待裁决的读法见 `review/claude_G0_spec.md` §8（A1–A20），其中 A1 车数口径、A2 就近是否单独要求、A3 问题 2 目标结构最关键

## 失误台账（只记严重错误）
| 类别 S/M/E/P | 描述 | 严重程度 | 发现者 | 发现阶段 | 是否已解决 |
|---|---|---|---|---|---|
