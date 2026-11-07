# 17｜API、术语与官方资料

## 1. API 速查

| API | 常用位置 | 职责 |
|---|---|---|
| `StateGraph` | `langgraph.graph` | 创建状态图 |
| `START / END` | `langgraph.graph` | 入口与结束标识 |
| `MessagesState` | `langgraph.graph` | 常用消息状态定义 |
| `add_messages` | `langgraph.graph.message` | 合并消息，处理消息身份 |
| `add_node` | 图 builder | 注册工作节点 |
| `add_edge` | 图 builder | 注册确定性后继 |
| `add_conditional_edges` | 图 builder | 注册条件路由 |
| `compile` | 图 builder | 创建可执行图 |
| `invoke / ainvoke` | 编译图 | 同步/异步执行 |
| `stream / astream` | 编译图 | stream_mode 事件输出 |
| `stream_events` | 编译图 | 版本化事件流接口 |
| `get_state` | 编译图 | 读取当前或指定检查点 |
| `get_state_history` | 编译图 | 遍历历史快照 |
| `update_state` | 编译图 | 通过 reducer 写状态并产生新保存点 |
| `Command` | `langgraph.types` | 更新、路由、恢复等控制信号 |
| `Send` | `langgraph.types` | 动态派发节点输入 |
| `interrupt` | `langgraph.types` | 等待外部恢复值 |
| `RetryPolicy` | `langgraph.types` | 节点暂时性错误重试 |
| `Runtime` | `langgraph.runtime` | 访问 context、Store 等运行信息 |
| `InMemorySaver` | `langgraph.checkpoint.memory` | 进程内检查点 |
| `SqliteSaver` | `langgraph.checkpoint.sqlite` | SQLite 检查点，需要独立依赖 |
| `InMemoryStore` | `langgraph.store.memory` | 进程内跨 thread 键值存储 |
| `ToolNode` | `langgraph.prebuilt` | 执行结构化工具调用 |
| `tools_condition` | `langgraph.prebuilt` | 根据工具请求决定下一步 |
| `entrypoint / task` | `langgraph.func` | Functional API 工作流和任务 |

API 表基于本教程固定版本。迁移时查官方参考和实际安装签名，不把旧博客导入位置当作永远不变。

## 2. 术语速查

| 术语 | 一句话理解 | 易错点 |
|---|---|---|
| state | 节点共享的运行数据 | 不等于 Python 调用栈 |
| reducer | 合并旧字段值与更新的函数 | 追加不等于去重 |
| super-step | 一轮可共同执行与归并的任务阶段 | 不等于单个节点 |
| thread | 一份状态历史的身份 | 不是 OS 线程或权限凭证 |
| run | 一次执行过程 | 一个 thread 可有多个 run |
| checkpoint | 可恢复的保存点 | 不回滚外部系统 |
| interrupt | 需要外部输入的暂停 | 不是普通异常失败 |
| resume | 为暂停或未完成工作继续执行 | 不同恢复形式不能混用 |
| replay | 重新执行历史点之后的工作 | 会产生新开销和副作用 |
| fork | 基于旧保存点产生另一条历史 | 不抹掉旧检查点 |
| Store | 跨会话应用数据存储接口 | 不是自动语义记忆或 ACL |
| idempotency | 重复同一操作不重复产生业务效果 | 不能只靠本地布尔变量 |
| subgraph | 被父图作为模块使用的图 | 不一定是 Agent |

## 3. 容易混淆的参数位置

```python
config = {
    "configurable": {"thread_id": "lesson-001"},
    "recursion_limit": 30,
}
result = graph.invoke(input_data, config, context=app_context)
```

thread_id 在 configurable 内；recursion_limit 在 config 顶层；context 使用对应调用参数。具体扩展配置需要核对当前签名。

## 4. 官方资料索引

核对日期：2026-11-06。推荐先按教程理解问题，再查对应资料。

| 资料 | 重点 |
|---|---|
| [Overview](https://docs.langchain.com/oss/python/langgraph/overview) | 框架定位与生态关系 |
| [Quickstart](https://docs.langchain.com/oss/python/langgraph/quickstart) | 最小 Agent 闭环 |
| [Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api) | 状态、节点与执行模型 |
| [State](https://docs.langchain.com/oss/python/langgraph/graph-api-state) | 字段、reducer、消息与 Schema |
| [Control flow](https://docs.langchain.com/oss/python/langgraph/graph-api-control-flow) | 顺序、分支和循环 |
| [Send and Command](https://docs.langchain.com/oss/python/langgraph/graph-api-send-command) | 动态任务与控制信号 |
| [Configure nodes](https://docs.langchain.com/oss/python/langgraph/graph-api-nodes) | 重试、缓存及运行配置 |
| [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence) | 持久化总体概念 |
| [Checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers) | thread、快照、恢复语义 |
| [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) | 人工中断与重进注意事项 |
| [Streaming](https://docs.langchain.com/oss/python/langgraph/streaming) | stream_mode 模式 |
| [Event streaming](https://docs.langchain.com/oss/python/langgraph/event-streaming) | v3 投影式事件流 |
| [Subgraphs](https://docs.langchain.com/oss/python/langgraph/use-subgraphs) | 子图接口与持久化范围 |
| [Memory](https://docs.langchain.com/oss/python/langgraph/add-memory) | 消息管理与记忆 |
| [Stores](https://docs.langchain.com/oss/python/langgraph/stores) | namespace、存储与检索 |
| [Fault tolerance](https://docs.langchain.com/oss/python/langgraph/fault-tolerance) | 失败、重试、恢复边界 |
| [Functional API](https://docs.langchain.com/oss/python/langgraph/functional-api) | 入口、任务与重放 |
| [Time travel](https://docs.langchain.com/oss/python/langgraph/use-time-travel) | 回放与历史分叉 |
| [Test](https://docs.langchain.com/oss/python/langgraph/test) | 图测试方法 |
| [Application structure](https://docs.langchain.com/oss/python/langgraph/application-structure) | 应用打包与部署入口 |

## 5. 版本阅读规则

看一段网上代码时，先记录发布时间、Python 版本、LangGraph 版本和模型集成版本。旧 API 是否仍受支持，与是否推荐新项目使用是两件事。

不要无条件升级全部依赖后只检查 import 成功。还应运行暂停恢复、消息协议、并行汇总和历史迁移测试。

## 6. 实验记录模板

```text
实验目的与假设：
图版本 / Python / 依赖锁：
输入与初始状态：
节点、边、reducer：
checkpointer / Store 后端：
thread 与恢复方式：
预期节点路径：
实际事件与状态：
失败或中断点：
是否产生外部副作用：
测试与性能结果：
已知限制：
```
