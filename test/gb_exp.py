"""
    3000约束量的规划求解，以验证证书是否为免费限制证书
    测试包含 3000 个变量和 3000 个约束，检查指定许可证是否支持该规模。
"""
import gurobipy as gp
from gurobipy import GRB

# 创建模型
model = gp.Model("3000_constraints")

# 添加变量
num_vars = 3000 # 约束量
vars = model.addVars(num_vars, vtype=GRB.CONTINUOUS, name="x")

# 添加约束（约束量3000）
for i in range(3000):
    # 示例：每个约束为x_i <= 1
    model.addConstr(vars[i] <= 1, name=f"constraint_{i}")

# 添加目标函数（最大化总和）
model.setObjective(gp.quicksum(vars.values()), GRB.MAXIMIZE)

# 求解
model.optimize()

# 输出结果
if model.status == GRB.OPTIMAL:
    print("最优解：", model.objVal)
    assert model.NumVars == 3000 and model.NumConstrs == 3000
    assert abs(model.ObjVal - 3000) < 1e-6
    assert all(abs(v.X - 1) < 1e-6 for v in vars.values())
else:
    raise RuntimeError(f"求解失败，Gurobi 状态码：{model.status}")
