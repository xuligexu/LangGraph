# 03｜状态设计与 Reducer

## 1. 状态不是全局杂物箱

状态应该保存节点之间确实需要交换、检查或恢复的数据。数据库连接、HTTP 客户端、API 密钥一般不应放进可持久化状态。

RAG 状态可以是：

```python
from typing import TypedDict

class RagState(TypedDict, total=False):
    question: str
    query: str
    documents: list[dict]
    attempts: int
    answer: str
    status: str
```

`total=False` 表示静态类型层面允许字段缺省，不代表读取不存在的键会自动得到 None。用 `state.get(...)` 或入口初始化处理缺省。

## 2. 默认更新：覆盖

初始状态：

```python
{"query": "原问题", "attempts": 0}
```

节点返回：

```python
{"query": "改写问题"}
```

合并后 query 更新，attempts 保留。对没有 reducer 的键，单步单次写入默认覆盖原值。

若两个并行节点在同一步都写 query，不能假设“最后完成的赢”。普通单值 channel 通常会报并发更新冲突，需要重新设计字段或 reducer。

## 3. Reducer：旧值与增量如何合并

```python
from operator import add
from typing import Annotated, TypedDict

class State(TypedDict):
    events: Annotated[list[str], add]
```

若已有 `events=["开始"]`，节点返回 `{"events":["检索完成"]}`，结果为 `['开始','检索完成']`。

`Annotated[T, reducer]` 把类型与合并函数关联。这里 `add` 对列表做拼接，不是自动去重。

实现要点见 [定义与更新状态](https://docs.langchain.com/oss/python/langgraph/graph-api-state)。

## 4. 常见重复陷阱

错误：

```python
return {"events": state["events"] + ["新事件"]}
```

因为 reducer 还会把旧值再拼一次：若旧值 `[A]`，更新 `[A,B]`，最终 `[A,A,B]`。

正确返回增量 `{"events":["新事件"]}`。但若需要覆盖整个字段，不能用“返回完整列表”假装覆盖；应按所用版本支持的覆盖机制或重新设计 channel。

## 5. 数值 reducer 的语义

```python
count: Annotated[int, add]
```

此时节点返回 `{"count":1}` 表示加一，而不是设为一。若返回 `state['count']+1`，会把旧值再加一遍。

如果 count 表示当前循环次数且只有一个节点维护，通常直接用普通 int，返回 `旧值+1` 更容易理解。并行贡献总数才考虑加法 reducer。

## 6. 自定义合并策略

并行检索可能产生同一文档的多个候选，可按 ID 合并并保留最高分：

```python
def merge_hits(left, right):
    best = {}
    for item in left + right:
        old = best.get(item["id"])
        if old is None or item["score"] > old["score"]:
            best[item["id"]] = item
    return sorted(best.values(), key=lambda x: (-x["score"], x["id"]))
```

这里假设同一 ID 的正文与来源一致。如果同分时内容不同，需要明确版本与冲突策略，不能依赖遍历顺序偷偷选择。

Reducer 应尽量纯净、可重复、可序列化；不在里面请求网络、获取随机数或写数据库。可并行归并时尤其要检查结合性，以及顺序是否影响结果。

## 7. 顺序与幂等不是一回事

- 列表拼接满足结合性，但顺序会影响列表内容的排列。
- 拼接同一更新两次会重复，因此不幂等。
- 按稳定 ID 去重可以减少重复，但还需要解决字段冲突。

不要让“第一个到达的并行结果”暗中决定业务结论。汇总节点可显式按 ID、分数和时间排序。

## 8. 输入、内部、输出 Schema

可以给图定义不同的输入输出范围，例如输入只有 question，内部还有 documents、attempts，输出只有 answer 与 sources。

这有助于 API 清晰，但不是保密边界。内部字段仍可能出现在 stream、checkpoint、日志或调试接口中。敏感信息应从存储、权限和事件过滤层面控制。

## 9. 一个字段设计表

| 字段 | 写入者 | 合并方式 | 生命周期 |
|---|---|---|---|
| question | 请求入口 | 覆盖 | 当前问题 |
| query | 初始化/改写 | 覆盖 | 当前检索轮 |
| documents | 检索节点 | 覆盖 | 当前检索轮 |
| attempts | 检索节点 | 覆盖为旧值+1 | 当前问题 |
| audit_events | 各节点 | 追加 | 按业务控制保留 |
| answer | 生成或拒答节点 | 覆盖 | 当前问题 |

将新问题输入同一 thread 时，未覆盖字段可能残留。应有入口节点重置请求级字段，而不是依赖“每次 invoke 都是空状态”。
