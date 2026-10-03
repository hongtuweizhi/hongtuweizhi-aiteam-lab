# 盲评裁判 v2：多 provider 支持（opencode-go 被限流后切 DeepSeek 官方）。
# 用法：JUDGE_PROVIDER=deepseek python judge.py
# 断点续跑：已完成卷自动跳过（按 provider 分文件存）。
import json
import os
import re
import time
from pathlib import Path

from openai import OpenAI

BLIND = Path(r"D:\aiteam-lab\blind")
SUBS = sorted((BLIND / "submissions").glob("*.txt"))

PROVIDERS = {
    "glm": {
        "base_url": "https://opencode.ai/zen/go/v1",
        "key_file": r"D:\aiteam-lab\agent\auth.json",
        "key_json_path": ("opencode-go", "key"),
        "model": "glm-5.3",
        "session": "aiteam-blind-judge",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "key_file": r"D:\aiteam-lab\agent\deepseek_key.txt",
        "key_json_path": None,
        "model": "deepseek-chat",
        "session": None,  # 官方 API 无需会话头
    },
}

JUDGE_PROMPT = """你是规划方案的盲评裁判。下面给你一份任务材料和一份匿名产出（可能包含叙述与 JSON）。
只评价**计划内容本身**的质量，不评价行文风格、长度或格式。产出里的自述（说完成了什么）不算数，
你要对照任务材料**自己核算**：时间窗是否被遵守、总时长是否超限、覆盖是否完整、时间表是否自洽。
产出可能来自不同的系统，不要猜测或评价来源。

评分维度（1-10 整数）：
- goal_coverage 目标覆盖：对照【目标】逐项核对，计划内容里是否有真实对应的安排（不是嘴上说达成）
- constraint_adherence 约束遵守：对照【约束】的数值（时间窗/总时长/距离），在时间表里核实
- feasibility_coherence 可行自洽：时间表先后/等待/ travelling 是否合理、无时间穿越
- completeness 完整性：【资源】里要求覆盖的对象是否都出现在计划中
- overall 总体质量

只输出一个 JSON 对象，不要其他文字：
{"goal_coverage": N, "constraint_adherence": N, "feasibility_coherence": N, "completeness": N, "overall": N, "strengths": "一句话", "weaknesses": "一句话"}

═══════════ 任务材料与匿名产出如下 ═══════════

"""


def load_key(provider: dict) -> str:
    raw = open(provider["key_file"], encoding="utf-8").read()
    if provider["key_json_path"]:
        return json.loads(raw)[provider["key_json_path"][0]][provider["key_json_path"][1]]
    return raw.strip()


def main():
    pname = os.environ.get("JUDGE_PROVIDER", "glm")
    p = PROVIDERS[pname]
    headers = {"x-opencode-session": p["session"], "x-opencode-client": "aiteam-lab"} if p["session"] else {}
    client = OpenAI(base_url=p["base_url"], api_key=load_key(p), default_headers=headers)

    out_path = BLIND / f"judge_scores_{pname}.json"
    done = {}
    if out_path.exists():
        done = {d["anon"]: d for d in json.loads(out_path.read_text(encoding="utf-8"))["judgements"]}

    judgements = list(done.values())
    for path in SUBS:
        if path.stem in done:
            continue
        t0 = time.time()
        try:
            content = path.read_text(encoding="utf-8")
            resp = client.chat.completions.create(
                model=p["model"],
                messages=[{"role": "user", "content": JUDGE_PROMPT + content}],
                temperature=0,
            )
            raw = resp.choices[0].message.content or ""
            m = re.search(r"\{[\s\S]*\}", raw)
            try:
                scores = json.loads(m.group()) if m else {"_parse_error": raw[:300]}
            except json.JSONDecodeError:
                scores = {"_parse_error": raw[:300]}
            u = resp.usage
            judgements.append({
                "anon": path.stem,
                "scores": scores,
                "raw": raw,
                "usage": {"prompt": u.prompt_tokens, "completion": u.completion_tokens,
                          "total": u.total_tokens} if u else {},
                "elapsed_s": round(time.time() - t0, 1),
            })
            s = scores if "_parse_error" not in scores else {}
            print(f"✓ {path.stem}: overall={s.get('overall')} goal={s.get('goal_coverage')} "
                  f"constraint={s.get('constraint_adherence')} feas={s.get('feasibility_coherence')} "
                  f"comp={s.get('completeness')} ({judgements[-1]['elapsed_s']}s)")
        except Exception as e:
            print(f"✗ {path.stem}: {type(e).__name__}: {str(e)[:150]}")
        out_path.write_text(json.dumps({"model": p["model"], "provider": pname,
                                        "judgements": judgements}, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    print(f"完成 {len(judgements)}/{len(SUBS)}")


if __name__ == "__main__":
    main()
