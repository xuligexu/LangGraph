# 04｜条件分支、循环与 Command

## 1. 普通边

```python
builder.add_edge("normalize", "retrieve")
```

normalize 完成后，retrieve 被安排执行。若同一节点有多条普通出边，会激活多个后继，不是“依次任选一条”。

## 2. 条件边

```python
def route(state):
    if state["documents"]:
        return "found"
    return "missing"

builder.add_conditional_edges(
    "retrieve", route,
    {"found": "answer", "missing": "refuse"},
)
```

路由函数返回分支标签，path map 将标签映射为节点名。也可以直接返回节点名，但显式映射通常更容易检查业务含义。

路由函数应主要读取状态并决定方向，不应顺手执行模型调用或产生外部副作用。需要工作的内容放到独立节点，便于追踪和重试。

## 3. 循环必须有可证明的出口

```text
retrieve → 有证据 → answer → END
    │
    └→ 无证据且未到上限 → rewrite → retrieve
    └→ 无证据且到上限 → refuse → END
```

将 attempts 的语义写清楚：“已执行的检索次数”，初始 0，每次 retrieve 加 1。最大检索次数 2 意味着初次一次、改写后再试一次。

如果同时有 `max_rewrites` 与 `max_attempts`，必须明确它们的关系，避免一个模块认为上限含初次，另一个认为不含。

## 4. 完整控制流的状态推演

假设首次检索为空、第二次命中：

| 步骤 | attempts | documents | 下一步 |
|---|---:|---|---|
| initialize | 0 | [] | retrieve |
| retrieve | 1 | [] | rewrite |
| rewrite | 1 | [] | retrieve |
| retrieve | 2 | [证据] | answer |
| answer | 2 | [证据] | END |

如果第二次仍为空，转 refuse。终止条件应优先由业务计数保证。

## 5. recursion_limit 是最后一道保护

```python
result = graph.invoke(input_data, {"recursion_limit": 30})
```

该值限制图执行步数，不是 Python 函数调用栈深度，也不是单纯的“模型最多调用 30 次”。并行节点可处在同一步。

达到限制通常意味着循环未退出，或正常任务预算确实不足。先检查路由和计数，不能看到 `GraphRecursionError` 就一直提高限制。

参考：[控制流](https://docs.langchain.com/oss/python/langgraph/graph-api-control-flow)。

## 6. Command：更新状态并指定去向

```python
from typing import Literal
from langgraph.types import Command

def decide(state) -> Command[Literal["answer", "refuse"]]:
    if state["documents"]:
        return Command(update={"status": "ready"}, goto="answer")
    return Command(update={"status": "missing"}, goto="refuse")
```

它把数据更新与路由放在一次节点返回中。类型标注帮助表达可能目标和图可视化，但不替代运行时输入验证。

如果决定只依赖已有状态，条件边很清晰；若节点既完成工作又决定去向，Command 更直接。

## 7. Command 不会取消普通出边

假设 decide 返回 `Command(goto="answer")`，你又写了：

```python
builder.add_edge("decide", "refuse")
```

refuse 仍可能运行。不要把普通边当作被 Command 覆盖的默认分支。为一个决定出口选择清晰的一种方式，避免重复路由。

关于 Send 与 Command 的不同用途，见 [官方指南](https://docs.langchain.com/oss/python/langgraph/graph-api-send-command)。

## 8. 两类 Command 不要混淆

| 用法 | 位置 | 目的 |
|---|---|---|
| `Command(update=..., goto=...)` | 节点返回值 | 改状态并控制后继 |
| `Command(resume=...)` | invoke/stream 的输入 | 回答一个待处理 interrupt |

恢复中断时不能只传一个普通字典以为它是审批答案。普通字典通常被当作新输入，并按入口路径开始工作。

## 9. 本章检查

画出你的流程，检查每个节点：是否可能有多个出口；多个出口是否真的要并行；每个环是否修改了终止条件；所有缺资料路径是否能结束；异常是否会被误当作“无证据”。
