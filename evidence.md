# 证据登记（evidence.md）

> 检验标准必须在看到结果之前登记。"可证明性质"失败 = 判错；"经验预期"失败 = 报警，人工检查。

## 检验标准（先写）
| 编号 | 对象 | 标准 | 类型（可证明/经验预期） | 登记时间 |
|---|---|---|---|---|
| ENV-01 | Gurobi 环境测试（不涉及赛题结论） | gurobipy 版本为 13.0.0；GRB_LICENSE_FILE 指向用户指定文件；运行 test/gb_exp.py 后必须为 OPTIMAL，变量和约束各 3000，目标值与 3000 的偏差小于 1e-6，每个解分量与 1 的偏差小于 1e-6 | 可证明 | 2026-11-19，运行求解前 |
| ENV-02 | Pyomo 和基础建模库 | 所安装库均可导入；Pyomo gurobi_direct 求解 max x、0≤x≤1 必须最优且 x=1（容差 1e-6）；pip check 无依赖冲突 | 可证明 | 2026-11-19，运行求解前 |

## 实验记录
| 编号 | 对应结论 | 代码提交号 | 输入/数据版本 | 参数/种子/求解器配置 | 输出文件 | 验证层 A/B/C | 状态 |
|---|---|---|---|---|---|---|---|
| ENV-01 | 指定许可证支持测试规模，修复后的测试得到预期最优解 | 基于 ddf46c2f6ef2e6fccd67303f7230cdb25d19709a 的未提交工作区；test/gb_exp.py 已修改 | 人工构造 max Σx_i，0≤x_i≤1，无赛题数据 | n=3000；无随机数；Gurobi 13.0.0 默认配置；Python 3.12.3；GRB_LICENSE_FILE 使用用户指定路径 | test/environment_check.log；test/environment_freeze.txt | B（环境冒烟测试） | 通过：OPTIMAL，目标值 3000，各分量为 1 |
| ENV-02 | Pyomo 能通过 gurobipy 调用求解器，基础库依赖正常 | 同上工作区 | 人工构造 max x，0≤x≤1 | Pyomo gurobi_direct；默认配置；无随机数；版本见 freeze 文件 | test/environment_check.log；test/environment_freeze.txt | B（环境冒烟测试） | 通过：最优 x=1，全部库可导入，pip check 无冲突 |

## 论文数字溯源
| 论文位置 | 数字 | 来源文件 | 已核对 |
|---|---|---|---|
