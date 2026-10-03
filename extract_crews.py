# 从 REALM-Bench 的 per-task notebook 里抽取 crew 配置（固定流程的"标准答案"）。
# 方法：stub 掉 src/multi_agent 的运行时，直接 exec notebook 的代码 cell，
# 用假 Agent/假 Crew 捕获角色定义与依赖边 —— 不跑任何模型，零成本。
# 产物：D:/aiteam-lab/crews/<TASK>.json
import json
import re
import sys
import types
from pathlib import Path

REPO = Path(r"D:\aiteam-lab\repos\REALM-Bench")
OUT = Path(r"D:\aiteam-lab\crews")
OUT.mkdir(parents=True, exist_ok=True)

# ── 假运行时：与 src/multi_agent/agent.py 的操作符语义一致 ──
AGENTS = []  # 所有 FakeAgent 实例按创建顺序


class FakeAgent:
    def __init__(self, name="", backstory="", task_description="", task_expected_output="",
                 tools=None, llm="gpt-4o", **kw):
        self.name = name
        # notebook 里 tools 可能传裸函数（如 write_str_to_txt），统一成列表
        if tools is None:
            tools = []
        elif not isinstance(tools, (list, tuple)):
            tools = [tools]
        self.cfg = {
            "name": name,
            "backstory": backstory,
            "task_description": task_description,
            "task_expected_output": task_expected_output,
            "tools": [getattr(t, "__name__", str(t)) for t in tools],
            "llm": llm,
        }
        self.dependencies = []
        self.dependents = []
        AGENTS.append(self)

    def _dep(self, other):
        if isinstance(other, FakeAgent):
            self.dependencies.append(other)
            other.dependents.append(self)
            return other
        if isinstance(other, list):
            for o in other:
                self._dep(o)
            return other
        raise TypeError("dependency must be FakeAgent")

    def _depedent(self, other):
        if isinstance(other, FakeAgent):
            other.dependencies.append(self)
            self.dependents.append(other)
            return other
        if isinstance(other, list):
            for o in other:
                self._depedent(o)
            return other
        raise TypeError("dependent must be FakeAgent")

    def __rshift__(self, other):
        return self._depedent(other)

    def __lshift__(self, other):
        return self._dep(other)

    __rrshift__ = __lshift__
    __rlshift__ = __rshift__

    def receive_context(self, x):
        pass


class FakeCrew:
    current = None

    def __init__(self):
        self.agents = []

    def __enter__(self):
        FakeCrew.current = self
        return self

    def __exit__(self, *a):
        FakeCrew.current = None

    def add_agent(self, a):
        self.agents.append(a)

    @staticmethod
    def register_agent(a):
        if FakeCrew.current is not None:
            FakeCrew.current.add_agent(a)

    def run(self):
        pass


def stub_modules():
    """把 notebook 会 import 的 src.* 模块换成假货。"""
    m_crew = types.ModuleType("src.multi_agent.crew")
    m_crew.Crew = FakeCrew
    m_agent = types.ModuleType("src.multi_agent.agent")
    m_agent.Agent = FakeAgent
    m_ma = types.ModuleType("src.multi_agent")
    m_ma.crew = m_crew
    m_ma.agent = m_agent
    m_src = types.ModuleType("src")
    m_src.multi_agent = m_ma
    m_tool = types.ModuleType("src.tool_agent.tool")

    def tool(fn=None, *a, **kw):
        if fn is not None:
            fn.is_tool = True
            return fn
        return lambda f: f

    m_tool.tool = tool
    m_ta = types.ModuleType("src.tool_agent")
    m_ta.tool = m_tool
    m_src.tool_agent = m_ta
    m_log = types.ModuleType("src.utils.logging")
    m_log.custom_print = print
    m_utils = types.ModuleType("src.utils")
    m_utils.logging = m_log
    m_src.utils = m_utils
    for name, mod in {
        "src": m_src,
        "src.multi_agent": m_ma,
        "src.multi_agent.crew": m_crew,
        "src.multi_agent.agent": m_agent,
        "src.tool_agent": m_ta,
        "src.tool_agent.tool": m_tool,
        "src.utils": m_utils,
        "src.utils.logging": m_log,
    }.items():
        sys.modules[name] = mod


def extract(nb_path: Path):
    nb = json.loads(nb_path.read_text(encoding="utf-8"))
    AGENTS.clear()
    crew_cells = []
    for cell in nb["cells"]:
        if cell["cell_type"] != "code":
            continue
        src = cell["source"] if isinstance(cell["source"], str) else "".join(cell["source"])
        crew_cells.append(src)

    ns = {"__name__": "__main__"}
    crew_result = None
    for i, src in enumerate(crew_cells):
        s = src.strip()
        # 跳过 shell/jupyter 魔法与 API key 设置
        if s.startswith("%") or s.startswith("!") or "OPENAI_API_KEY" in s and "=" in s and "get" not in s:
            continue
        try:
            exec(compile(s, f"{nb_path.name}:cell{i}", "exec"), ns)
        except Exception as e:
            # 只对含 crew 的 cell 严格，其余 cell 失败可容忍
            if "Crew" in s:
                print(f"  ⚠ crew cell 执行失败: {type(e).__name__}: {e}")
            continue
        if "with Crew()" in s:
            crew_result = True

    if not AGENTS:
        return None

    # 解析依赖边（FakeAgent 之间已连接）
    agents_json = []
    id_map = {}
    for idx, a in enumerate(AGENTS):
        id_map[id(a)] = idx
        agents_json.append({**a.cfg, "index": idx})
    edges = []
    for idx, a in enumerate(AGENTS):
        for d in a.dependencies:
            edges.append([id_map[id(d)], idx])

    # 拓扑排序验证（无环 + 全覆盖）
    indeg = [0] * len(AGENTS)
    for f, t in edges:
        indeg[t] += 1
    order, queue = [], [i for i, d in enumerate(indeg) if d == 0]
    while queue:
        n = queue.pop(0)
        order.append(n)
        for f, t in edges:
            if f == n:
                indeg[t] -= 1
                if indeg[t] == 0:
                    queue.append(t)
    dag_ok = len(order) == len(AGENTS)

    return {"notebook": nb_path.name, "dag_ok": dag_ok, "agents": agents_json, "edges": edges}


def main():
    stub_modules()
    claimed = {}  # task_id -> notebook 文件名（非副本优先）
    notebooks = sorted(REPO.glob("design_patterns/multiagent-[PJ]*.ipynb"))
    # 先定归属：文件名里的每个 P\d+ / J\d+ 都算一个任务；Copy1 让位给正主
    for nb_path in notebooks:
        ids = re.findall(r"[PJ]\d+", nb_path.stem)
        if not ids:
            continue
        is_copy = "copy" in nb_path.stem.lower()
        for tid in ids:
            cur = claimed.get(tid)
            if cur is None or (is_copy and "copy" not in cur.stem.lower()):
                claimed[tid] = nb_path

    for tid, nb_path in sorted(claimed.items()):
        cfg = extract(nb_path)
        if cfg is None:
            print(f"· {tid} ({nb_path.name}): 没抓到 crew，跳过")
            continue
        cfg["task_ids"] = [tid]
        cfg["source_notebook"] = nb_path.name
        out = OUT / f"{tid}.json"
        out.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"✓ {tid} ← {nb_path.name}: {len(cfg['agents'])} 角色, {len(cfg['edges'])} 边, DAG {'✓' if cfg['dag_ok'] else '✗ 有环!'}")


if __name__ == "__main__":
    main()
