# 09｜并行分支、Send 与结果汇总

## 1. 静态并行：分支数量提前知道

例如同时执行关键词检索与向量检索：

```text
          ┌→ keyword ─┐
START ────┤           ├→ merge → END
          └→ dense ───┘
```

注册方法：

```python
builder.add_edge(START, "keyword")
builder.add_edge(START, "dense")
builder.add_edge(["keyword", "dense"], "merge")
```

列表形式表达 merge 等待两个指定前驱都完成的汇合要求。不要把两条独立边机械理解成任意复杂路径下都等价的屏障。

尤其当两条分支长度不同，必须明确等待哪些终端节点；不能让短分支提前触发汇总，随后长分支又触发一次。

## 2. 并行节点如何写状态

方案 A：不同字段。

```python
keyword_hits: list[dict]
dense_hits: list[dict]
```

方案 B：同一字段＋合适 reducer。

```python
hits: Annotated[list[dict], merge_hits]
```

如果需要分别检查两种检索分数，方案 A 往往更清晰。合并时再做 RRF，不要把不同分值尺度直接加起来。

## 3. 动态并行：运行时才知道有多少项

用户上传 N 篇文章，N 随请求变化。用 Send 给同一个 worker 节点派发不同输入：

```python
from langgraph.types import Send

def scatter(state):
    return [Send("worker", {"document_id": doc["id"], "text": doc["text"]})
            for doc in state["documents"]]
```

Send 的输入可以与父图完整 state 不同，worker 只接收完成任务所需字段。它返回的更新仍需与目标状态及 reducer 设计兼容。

机制与限制参考 [Send 与 Command](https://docs.langchain.com/oss/python/langgraph/graph-api-send-command)。

## 4. 配套平方求和实验

[patterns.py](示例项目/patterns.py) 运行：

```text
jobs = [{id:a,value:2}, {id:b,value:3}]
→ Send(worker,a) 与 Send(worker,b)
→ reports = [{id:a,value:4}, {id:b,value:9}]
→ total = 13
```

reports 使用列表追加 reducer。总数在 gather 节点计算，避免多个 worker 同时覆盖 total。

```bash
python patterns.py
```

## 5. 空集合需要明确路径

scatter 返回空列表意味着没有派发任务，不应假设 gather 仍会按你的预期运行。

示例中 jobs 为空时直接路由到 gather，返回 total=0。这是业务规则，不是框架帮你猜出来的行为。

## 6. 顺序与去重

不要依赖并行任务完成顺序决定最终展示顺序。保留稳定 job_id，在汇总后按业务顺序排序。

如果任务可能重复提交，列表追加会重复记录。应考虑按 job_id 去重、业务去重表或幂等操作。仅换一个 reducer 不能处理所有外部副作用重复问题。

## 7. 并行的代价

假设两项网络任务各用 1 秒与 2 秒，理想并行大约需要较慢任务的时间加协调开销，而非 3 秒。但模型服务限流、线程池、数据库锁会改变结果。

大量 Send 会增加在途任务、结果、检查点和内存。按数据量分批、控制并发，不能一次把百万项目全部派发到进程里。

可从 config 的 `max_concurrency` 等运行配置与后端实际约束入手压测；它不替代服务端速率限制或分布式队列。

## 8. 部分失败

一个 worker 失败时，需要明确整个批次如何处理：全体失败、记录失败项后继续，还是等待人工补充？

不要让 worker 捕获所有异常后返回空列表，因为“没有结果”和“处理失败”会被混为一谈。可以返回带 `status/error_code` 的结构化业务结果，暂时性系统错误则按重试策略处理。

成功任务的 pending writes 恢复与后端持久化有关，不能把它扩大成“所有外部操作恰好一次”。参见第 12 章。

## 9. 验收清单

空集合、单项、多项、重复 ID、乱序完成、某一项失败、汇总次数、并行写冲突、并发上限。至少为这些情形说明期望行为。
