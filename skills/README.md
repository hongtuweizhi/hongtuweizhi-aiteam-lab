# skills —— 可独立安装的技能包

每个子目录是一个自包含技能（`SKILL.md` + 脚本），复制到 ZCode 的技能发现目录即可安装：

```
Windows:  C:\Users\<你>\.agents\skills\
Linux:    ~/.agents/skills/
```

例如安装 objective-scorer：

```bash
cp -r skills/objective-scorer ~/.agents/skills/
```

安装后在新会话里用自然语言触发（如"给这个任务做个客观判分器"），或在提示词里直接引用。

| 技能 | 一句话 | 自检 |
|---|---|---|
| **objective-scorer** | 给有标准答案的 agent 任务生成"不信任自报"的机器判分器 | `scripts/checker_template.py selftest` |
| **handoff-probe** | 往任意多 agent 管线注入 K 条机器可核验约束，输出逐跳存活曲线 | `scripts/probe_template.py selftest` |
| battle | 斗蛐蛐实验台操作手册（本实验室专用，依赖实验室目录） | — |

两个模板脚本都内置 `selftest`：改完模板先跑自检，确认打分/曲线逻辑本身正确，再接真实任务。
设计渊源与实测数据见仓库根 `REPORT.md`（objective-scorer 背后的自报造假三次实证；
handoff-probe 背后的"第一跳丢 60% 约束"实测曲线）。
