# 当前状态（state.md）

> 每次工作结束前更新。人确认过的决策写进"决策记录"并注明日期。

## 当前
- 赛题：2026 国赛 B 题（无线电干扰源的快速自动定位与清除），用作赛前演练
- 演练目标：只测两件事 ①题意守恒 ②主工程能否从方案跑到可信数值
- 当前阶段：G0 读题
- 主工程方：待定（演练中实测）
- 审查方：待定

## 下一步
1. 人独立读题，写 `notes/human_G0.md`（目标、约束、疑问、直觉想法）
2. Claude、GPT 分别独立写 `review/claude_G0_spec.md`、`review/gpt_G0_spec.md`，互不读取
3. 人对比三份，裁决分歧，合并成 `spec.md` v1

## 决策记录
| 日期 | 决策 | 理由 | 决策人 |
|---|---|---|---|

## 未解决问题
-

## 环境准备记录（2026-11-19，GPT）
- 按用户指令完成环境支持任务；主工程/审查角色仍待人指定，当前阶段保持 G0。
- 终端原有 python 为 Windows 商店占位程序；使用 uv 管理的 Python 3.12.3 创建仓库 `.venv`，从南科大镜像安装 requirements.txt 中全部库；实际版本见 `test/environment_freeze.txt`。
- 用户级 `GRB_LICENSE_FILE` 已持久配置为 `D:\WYP\SOFTWARE\Gurobi\win64\bin\gurobi.lic`；未修改、复制或提交许可证。已有终端/编辑器需重新启动以继承用户环境变量。
- 本地 `.vscode/settings.json`（Git 忽略）配置默认解释器为 `.venv\Scripts\python.exe`；编辑器已有解释器选择时需手动切换。
- 修复 `test/gb_exp.py` 的 `sum(vars)` 累加字典键问题，改为 `gp.quicksum(vars.values())` 并添加结果断言。
- ENV-01/02 均通过：原测试修复后 3000 变量/3000 约束最优值 3000；Pyomo gurobi_direct 求解通过；库可导入且 pip check 无冲突。日志见 `test/environment_check.log`，仅验证环境，不涉及赛题 A/C 层结论。

## 演练失误台账（只记严重错误）
| 类别 S语义/M建模/E工程/P论证 | 描述 | 严重程度 | 发现者 | 发现阶段 | 是否提交前解决 |
|---|---|---|---|---|---|
