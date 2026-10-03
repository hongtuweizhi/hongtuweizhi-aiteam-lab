"""aiteam 实验室任务注册：T 系列边界任务。

设计稿：D:\\aiteam-lab\\BOUNDARY_TASKS.md。导入本模块即注入 TASK_DEFINITIONS
（run_evaluation.py 已挂 try-import，上游文件零改动）。

T3：钉死实例的 3×3 JSSP。与 P11 的本质区别：实例数据由任务给定（不允许发明），
判分不信任自报——t3_checker.py 离线穷举精确最优 makespan（=9），并机器核验
工序覆盖 / 工件先后 / 机器不重叠 / 工时一致。
实例的唯一事实源在 t3_checker.py（判分与任务文本共用同一份，防止口径漂移）。
"""
import sys

sys.path.insert(0, r"D:\aiteam-lab")

from evaluation.task_definitions import (  # noqa: E402
    TASK_DEFINITIONS,
    TaskCategory,
    TaskConstraint,
    TaskGoal,
    TaskDefinition,
)
from t3_checker import INSTANCE, solve_optimum  # noqa: E402

_OPT, _OPT_COUNT = solve_optimum()

_T3_DESCRIPTION = """为下面这个钉死的 Job-Shop 调度实例制定排程。实例数据如下（必须原样使用，不得发明、修改或遗漏任何工序）：
3 台机器：M1、M2、M3。
J1：J1-O11 在 M1 加工 2 小时 → J1-O12 在 M2 加工 3 小时 → J1-O13 在 M3 加工 2 小时。
J2：J2-O21 在 M2 加工 4 小时 → J2-O22 在 M3 加工 1 小时 → J2-O23 在 M1 加工 3 小时。
J3：J3-O31 在 M3 加工 2 小时 → J3-O32 在 M1 加工 3 小时 → J3-O33 在 M2 加工 2 小时。
要求：每个工序的机器与工时固定；同工件内工序按给定顺序先后加工；同一机器上的工序时间不得重叠。
从 0 时刻开始，给出全部 9 个工序的开始/结束时间（小时），并最小化总完工时间（makespan）。"""

TASK_DEFINITIONS["T3"] = TaskDefinition(
    task_id="T3",
    name="JSSP Objective (Pinned Instance)",
    category=TaskCategory.SCHEDULING,
    description=_T3_DESCRIPTION,
    goals=[
        TaskGoal(
            goal_id="minimize_makespan",
            description="Minimize total completion time (makespan)",
            weight=1.0,
            success_criteria={"optimal_makespan": _OPT},
        ),
        TaskGoal(
            goal_id="feasible_schedule",
            description="All 9 operations scheduled with exact durations, precedence and machine non-overlap",
            weight=1.0,
            success_criteria={},
        ),
    ],
    constraints=[
        TaskConstraint(
            constraint_id="job_precedence",
            constraint_type="dependency",
            description="Operations within each job follow the given order",
            parameters={"jobs": {j: ops for j, ops in
                       [(jj["job_id"], [o["op_id"] for o in jj["operations"]]) for jj in INSTANCE["jobs"]]}},
        ),
        TaskConstraint(
            constraint_id="machine_capacity",
            constraint_type="capacity",
            description="No overlap between operations on the same machine",
            parameters={"machines": INSTANCE["machines"]},
        ),
        TaskConstraint(
            constraint_id="fixed_durations",
            constraint_type="resource",
            description="Each operation runs exactly its specified duration on its specified machine",
            parameters={"processing_times": {o["op_id"]: {"machine": o["machine"], "duration": o["duration"]}
                        for jj in INSTANCE["jobs"] for o in jj["operations"]}},
        ),
    ],
    resources=INSTANCE,
    optimal_solution={"makespan": _OPT, "method": "brute-force 1680 linear extensions", "optimal_count": _OPT_COUNT},
)

# ── T4：交接保真探针（5 条机器可核验约束过 4 次角色交接）──
# 判分不靠 evaluator 的 goal% 主表，靠 probe_handoff.py 的约束存活率
# （fixed 可画逐跳存活曲线，free / free-shared 测终局存活率）。
TASK_DEFINITIONS["T4"] = TaskDefinition(
    task_id="T4",
    name="Handoff Fidelity Probe (Tech Salon Plan)",
    category=TaskCategory.LOGISTICS,
    description=(
        "为一场技术沙龙做完整筹备计划。已知条件：场地『云轩厅』只在周六 14:00-18:00 可用；"
        "总预算上限 ¥8,000（场地费 ¥2,000 + 餐费 ¥58/人）；报名 64 人、按 75% 出席率折算实际人数；"
        "主讲嘉宾『林岚』的演讲不得少于 45 分钟；议程必须包含不少于 30 分钟的 Q&A 环节。"
        "产出完整筹备计划：场地使用时段、完整议程时间表（每环节名称与起止时间）、"
        "预算明细（人数折算、餐费、场地费、总额与上限对比）、嘉宾安排。"
        "所有给定的数字与专有名词必须逐字保留在最终计划里。"
    ),
    goals=[
        TaskGoal(goal_id="complete_plan", description="Complete salon preparation plan with venue, agenda, budget, guest arrangement", weight=1.0),
        TaskGoal(goal_id="constraint_fidelity", description="All given numbers and proper nouns preserved verbatim in the final plan", weight=1.0),
    ],
    constraints=[
        TaskConstraint(constraint_id="venue_window", constraint_type="deadline",
                       description="云轩厅 only available Saturday 14:00-18:00", parameters={"venue": "云轩厅", "window": [14, 18]}),
        TaskConstraint(constraint_id="budget_cap", constraint_type="resource",
                       description="Total budget ≤ ¥8,000 (venue ¥2,000 + catering ¥58/person)",
                       parameters={"cap": 8000, "venue_fee": 2000, "catering_per_person": 58}),
        TaskConstraint(constraint_id="headcount", constraint_type="resource",
                       description="64 registered × 75% attendance = 48 attendees",
                       parameters={"registered": 64, "attendance_rate": 0.75, "expected": 48}),
        TaskConstraint(constraint_id="keynote_min", constraint_type="deadline",
                       description="Keynote by 林岚 must be ≥ 45 minutes", parameters={"speaker": "林岚", "min_minutes": 45}),
        TaskConstraint(constraint_id="qa_min", constraint_type="deadline",
                       description="Q&A session must be ≥ 30 minutes", parameters={"min_minutes": 30}),
    ],
    resources={"registered": 64, "attendance_rate": 0.75, "budget_cap": 8000,
               "venue_fee": 2000, "catering_per_person": 58,
               "venue": "云轩厅", "venue_window": [14, 18], "speaker": "林岚",
               "keynote_min_minutes": 45, "qa_min_minutes": 30},
)

# ── T4b：数据依赖链（课题 4 的真正测试场）──
# 3 个 worker 严格依赖：物料缺口 → 采购排期 → 预算审核。
# 全链数字有确定性标准答案（t4b_checker.py 本地重算），判分逐字段核对，零主观。
# 实验设计：forceSpawn=3 + isolated（lead 中继数据）vs shared（黑板传递数据），
# 同任务同模型同 N，度量：终局数字正确率、token 开销、错误传播位置。
_T4B_DATA = {
    "product": "智能水杯", "unit_price": 85, "first_order": 1200,
    "bom": {"杯体": 1, "电路板": 2, "电池": 1},
    "stock": {"杯体": 400, "电路板": 900, "电池": 380},
    "purchase": {"杯体": {"price": 30, "lead_days": 5},
                 "电路板": {"price": 12, "lead_days": 3},
                 "电池": {"price": 8, "lead_days": 7}},
    "assembly_cost_per_unit": 15,
    "delivery_days": 30,
}

TASK_DEFINITIONS["T4b"] = TaskDefinition(
    task_id="T4b",
    name="Data Dependency Chain (Product Launch Prep)",
    category=TaskCategory.SUPPLY_CHAIN,
    description=(
        "为智能水杯的首批订单做供应计划。给定数据（必须原样使用，不得编造或修改任何数字）："
        f"出厂价 {_T4B_DATA['unit_price']} 元/台；首批订单 {_T4B_DATA['first_order']} 台，"
        f"{_T4B_DATA['delivery_days']} 天内交付；单台物料：杯体 1、电路板 2、电池 1；"
        f"当前库存：杯体 400、电路板 900、电池 380；"
        f"采购单价与周期：杯体 30 元/个 5 天、电路板 12 元/个 3 天、电池 8 元/个 7 天；"
        f"组装成本 15 元/台。"
        "请完成三步核算：(1) 物料缺口（订单需求 × BOM − 库存）；"
        "(2) 采购计划（各部件缺口 × 采购单价 = 采购费，总额，以及最长采购周期对应的关键路径天数）；"
        "(3) 预算审核（收入 = 订单 × 出厂价；总成本 = 采购总额 + 组装成本；毛利 = 收入 − 总成本；"
        "给出可行/不可行结论：毛利为正且关键路径 ≤ 交付期则为可行）。"
        "最终产出必须包含以上全部数字。"
    ),
    goals=[
        TaskGoal(goal_id="correct_propagation", description="All chain numbers (gap → procurement → budget) correct vs ground truth", weight=1.0),
        TaskGoal(goal_id="feasibility_verdict", description="Feasibility conclusion consistent with the computed numbers", weight=1.0),
    ],
    constraints=[
        TaskConstraint(constraint_id="bom_fixed", constraint_type="resource",
                       description="BOM and stock are given, do not invent", parameters=_T4B_DATA),
        TaskConstraint(constraint_id="delivery_deadline", constraint_type="deadline",
                       description="Delivery within 30 days; critical path = max purchase lead days",
                       parameters={"delivery_days": 30}),
    ],
    resources=_T4B_DATA,
)

# ── T4c 系列：大中间产物 + 数据分区（规模阶梯 40/20/12，共用同一公式与判分器）──
# worker A 必须读文件算缺口表（数据只存在于工作目录文件里）→ B 的采购成本完全依赖
# A 的表（隔离=lead 中继 N 行，共享=A 写黑板 B 直读）→ C 用总额审预算。
# 判分：t4c_checker.py 逐行 + 汇总字段（公式化实例，确定性重算）。
import sys as _sys
_sys.path.insert(0, r"D:\aiteam-lab")
from t4c_checker import gen_instance as _t4c_gen  # noqa: E402


def _register_t4c(task_id: str, n_parts: int):
    last = f"P{str(n_parts).zfill(2)}"
    TASK_DEFINITIONS[task_id] = TaskDefinition(
        task_id=task_id,
        name=f"Large Intermediate Artifact ({n_parts}-Part Procurement)",
        category=TaskCategory.SUPPLY_CHAIN,
        description=(
            f"为智能水杯的 1200 台首批订单做采购计划。工作目录里有三个数据文件（必须读取使用，不得编造）："
            f"stock.json（{n_parts} 个部件的当前库存，编号 P01–{last}）、"
            f"needs.json（各部件的单台用量）、prices.json（各部件采购单价与采购周期，天）。"
            f"经济常数：组装成本 15 元/台，出厂价 85 元/台，交付期 30 天。"
            f"请完成：(1) 逐个部件核算采购缺口 = 1200 × 单台用量 − 库存（全部 {n_parts} 个部件）；"
            f"(2) 逐个部件核算采购成本 = 缺口 × 单价，汇总采购总额，并取各部件采购周期的最大值作为关键路径天数；"
            f"(3) 预算审核：收入 = 1200 × 85；总成本 = 采购总额 + 组装成本（1200 × 15）；"
            f"毛利 = 收入 − 总成本；可行 = 毛利为正且关键路径 ≤ 30 天。"
            f"最终产出必须包含全部 {n_parts} 个部件的采购成本表与全部汇总字段。"
        ),
        goals=[
            TaskGoal(goal_id="per_part_fidelity", description=f"All {n_parts} part procurement costs correct vs ground truth", weight=1.0),
            TaskGoal(goal_id="correct_totals", description="procurement_total / critical_path / total_cost / profit / feasible all correct", weight=1.0),
        ],
        constraints=[
            TaskConstraint(constraint_id="data_files", constraint_type="resource",
                           description="stock/needs/prices 数据在工作目录文件里，必须读取，不得编造",
                           parameters={"files": ["stock.json", "needs.json", "prices.json"], "parts": n_parts}),
            TaskConstraint(constraint_id="delivery_deadline", constraint_type="deadline",
                           description="Delivery within 30 days", parameters={"delivery_days": 30}),
        ],
        resources={"parts": n_parts, "first_order": 1200, "unit_price": 85,
                   "assembly_cost_per_unit": 15, "delivery_days": 30,
                   "data_files": ["stock.json", "needs.json", "prices.json"]},
    )


_register_t4c("T4c", 40)
_register_t4c("T4c20", 20)
_register_t4c("T4c12", 12)
_register_t4c("T4c9", 9)
_register_t4c("T4c6", 6)
