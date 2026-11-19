# 当前状态（state.md）

> 两次演练已归档：`archive/rehearsal1_2026B/`、`archive/rehearsal2_2026C/`（含复盘与优秀论文对照）。
> **新窗口先读 `process/比赛作战手册.md`。**

## 当前
- 阶段：**G1 洞察**（`spec.md` v1.1 已冻结）
- 主工程方 + 整合者：本地 Claude Code（可用 Gurobi）；审查方：GPT；第三方：**Gemini**（局外人；G0 稿由千问写，此后由 Gemini 接替）
- 目标：特等奖；赛期 5 天；**今晚 spec 冻结**
- 分支：`work/primary`（已推送）

## 已完成（Claude Code）
- 原件归位：`problem/F/original/F.docx`、`problem/F/original/附件/`（8 个 xlsx）
- 转换稿 `problem/F/F.md`（两处公式图已渲染核对，图在 `problem/F/figs/`）；数据摘要 `problem/F/数据摘要.md`
- 解析器 `src/f_parse.py`（路径改为 original/附件；修复附件4 半角括号导致收发方解析失败），长表在 `results/F/parsed/`
- 独立读题稿 `review/claude_G0_spec.md`（独立完成后已提交 4bed68d）
- G1：统一行列清单 `review/G1_grid.md`；需求块构造 `src/f_blocks.py`（Y2 = 90 块）；Claude 的网格稿（初步：批次下界 28、简化整数规划 31 批，均未进 evidence）
- `spec.md` v1：按裁决生成，10 条自补假设单列（§6），其中 5 条安排了敏感性分析
- 四方稿到齐（人、Claude、GPT、千问），裁决单 `review/G0_compare.md` v2（已并入人补全后的初稿）：一致点、12 条数据定案的事实、22 条分歧（D1–D22）、15 条单方独有点

## 下一步
1. GPT、Gemini：按 `review/G1_grid.md` 各自独立填 N1–N5，写入 `review/gpt_G1_grids.md`、`review/gemini_G1_grids.md`（Claude 的已完成：`review/claude_G1_grids.md`）
2. Claude Code：三方到齐后逐格取并集 → `review/G1_compare.md` 裁决单 + `review/insights.md` → 人裁决 → spec v2
3. Claude Code 同时做：问题 1 的件2→件3 逐批精确对照、独立检查器骨架（只读结果 xlsx）

## 决策记录
| 日期 | 决策 | 理由 | 决策人 |
|---|---|---|---|
| 2026-11-19 | 选 F 题 | 选题模型报告（`chooseQusetion/`） | 人 |
| 2026-11-19 | G0 裁决单 D1–D22 全部取默认 a | `review/G0_compare.md` v2 | 人 |
| 2026-11-19 | 第三方由千问改为 Gemini | 人指定 | 人 |
| 2026-11-19 | spec v1.1 冻结；E1（被代方时段为软约束）、E2（留置也受等待 1 天限制）取默认 | `spec.md` §10 | 人 |

## 未解决问题
- 附件 2–8 与 F.docx 的修改时间是今天 18:33–18:55（附件 1 是 9 月 19 日），可能被打开后另存过；建议与官网下载的原件核对一次
- `problem/` 下仍有演练目录 2026B、2026C（不影响 F 题）
- GPT 稿没有涉及约束读法、路线、时序，审公式时可能只覆盖一部分，见裁决单 D20
- 人于 11-19 晚改过原件（表头文字、F.docx 术语 3 措辞），解析数据不变（裁决单 F12）

## 失误台账（只记严重错误）
| 类别 S/M/E/P | 描述 | 严重程度 | 发现者 | 发现阶段 | 是否已解决 |
|---|---|---|---|---|---|
