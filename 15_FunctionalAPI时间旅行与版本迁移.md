# 15｜Functional API、时间旅行与版本迁移

## 1. 两套 API 的表达方式

| 方面 | Graph API | Functional API |
|---|---|---|
| 主要结构 | State、Node、Edge | entrypoint、task、普通控制流 |
| 分支循环 | 图边与路由函数 | Python if/for/while |
| 数据流 | 明确共享状态与 reducer | 函数输入输出与任务结果 |
| 适用场景 | 需要显式图结构和状态边界 | 已有函数流程，想增加运行时能力 |

它们不是“一个用于普通流程，另一个只用于 Agent”。二者都能组合模型与普通代码。

## 2. 最小 Functional API

```python
from langgraph.func import entrypoint, task

@task
def square(number: int):
    return number * number

@entrypoint()
def sum_squares(numbers: list[int]):
    futures = [square(n) for n in numbers]
    return sum(future.result() for future in futures)

print(sum_squares.invoke([2, 3]))
```

得到 13。task 调用返回可等待结果，不应把 Future 当成已经计算出的整数。这个例子也在 patterns.py 中。

当前最小例子未配置 checkpointer，不应宣称能跨进程恢复。需要持久化时按入口配置与任务重放约定实现。参考 [Functional API](https://docs.langchain.com/oss/python/langgraph/functional-api)。

## 3. task 边界为何重要

entrypoint 恢复时可能重放函数代码；已成功完成且已保存的 task 结果可被复用。非确定性工作和副作用应放入合适的 task 或其他有明确恢复语义的单元。

任务结果保存不能自动保证外部 API 恰好一次。外部成功而结果尚未保存的窗口仍需幂等处理。

## 4. 重放要求控制流稳定

如果恢复时在前面插入一个新的任务，或改变任务调用顺序，原来的结果对应关系可能不再符合预期。

时间、随机数、模型返回、外部读取等都可能改变路径。应放在受管理的任务边界内，并采用稳定输入与版本策略。

不要在原函数里散落多个不可重复的外部写入，再认为加上一个装饰器就完成可靠工作流。

## 5. 时间旅行不是撤销外部世界

回放：从一个历史检查点之后重新执行。

分叉：以历史检查点为基础修改状态，再探索另一条路径。

它们可以用于调试“如果当时选择另一份证据会怎样”，但不会撤回已经发出的邮件、已扣的钱或已写入外部数据库的行。

官方说明：[Time travel](https://docs.langchain.com/oss/python/langgraph/use-time-travel)。

## 6. 选择历史点并分叉

以最小问候图为例：

```python
history = list(graph.get_state_history(config))
before = next(s for s in history if s.next == ("greet",))
fork_config = graph.update_state(
    before.config,
    {"name": "新名字"},
    as_node=START,
)
result = graph.invoke(None, fork_config)
```

前提：graph 是带 checkpointer 且已运行的问候图，START 已导入。`as_node` 指示这次更新按哪个节点的写入来处理，会影响后继调度，不是任意备注字段。

原历史检查点仍保留；update_state 创建新的检查点分支，不是直接抹掉旧历史。更新依然遵循 reducer，向追加字段写完整历史仍可能重复。

## 7. 回放会产生真实开销

历史点之后的模型、工具与 interrupt 可能重新运行，输出也可能改变。仅阅读 `get_state_history` 与执行回放是不同操作。

调试环境使用只读工具、模拟外部写入或稳定幂等键，防止把试验变成重复业务操作。

## 8. 图版本迁移

旧检查点可能保存着：旧字段类型、旧节点名、下一步节点、消息格式、待恢复 interrupt。以下变化尤其危险：

- 删除或重命名仍被旧任务引用的节点。
- 将字段从 list 改成 dict。
- 改变 reducer，使旧数据无法合并。
- 调整同一节点中 interrupt 或 task 的调用顺序。
- 改变外部操作的幂等键计算方式。

## 9. 可实施的迁移策略

1. 为图和状态结构标明版本。
2. 保留旧版本服务直至旧任务完成，或提供显式迁移过程。
3. 在历史检查点副本上测试读取、恢复、拒绝和分叉。
4. 不让旧批准自动套用于新方案。
5. 定义失败时回滚到哪一版图及数据。

新增一个可选字段通常比删除旧字段容易兼容，但也要检查代码是否假设它始终存在。

## 10. 选择 API 的建议

如果你需要经常画出执行路径、观察共享 state、调整分支，先使用 Graph API。如果已有清晰的函数流程，更偏向正常 Python 控制结构，可以再评估 Functional API。

先掌握一种 API 的状态、恢复与幂等语义，再迁移；不要为了缩短代码而掩盖原本需要审核的业务分支。
