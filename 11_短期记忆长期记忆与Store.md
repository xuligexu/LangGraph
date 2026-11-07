# 11｜短期记忆、长期记忆与 Store

## 1. 两种记忆要分开

| 需求 | 主要机制 | 例子 |
|---|---|---|
| 同一会话继续讨论 | state＋checkpointer | 上一轮用户问了哪个套餐 |
| 不同会话共享偏好 | Store 或业务数据库 | 用户希望默认中文回答 |
| 查询权威知识 | 知识库与检索系统 | 当前有效退款规则 |

长期记忆不等于把所有聊天永久存入向量库。RAG 知识库、用户偏好和运行检查点有不同权限、更新与删除要求。

官方区分：[Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)、[Memory](https://docs.langchain.com/oss/python/langgraph/add-memory)。

## 2. InMemoryStore 最小操作

```python
from langgraph.store.memory import InMemoryStore

store = InMemoryStore()
namespace = ("users", "u1", "preferences")
store.put(namespace, "language", {"value": "中文"})
item = store.get(namespace, "language")
print(item.value)
store.delete(namespace, "language")
```

namespace 用于组织数据，key 定位其中一项。不要把 namespace 当成框架自动执行的安全权限：应用仍需保证调用者只能访问被允许的范围。

InMemoryStore 适合学习与测试，进程退出会丢失数据。磁盘或数据库持久化需要选相应后端。见 [Stores](https://docs.langchain.com/oss/python/langgraph/stores)。

## 3. 将 Store 注入节点

```python
graph = builder.compile(store=store)
```

节点可通过 `runtime.store` 访问，并从运行 context 获取当前用户标识。配套 patterns.py 演示：u1 有中文偏好，u2 没有，读取结果不同。

可信的 user_id 应由认证层生成；模型输出的“我属于用户 u1”不能直接决定 namespace。

## 4. search 不一定是语义检索

Store 的 search 可以列举或过滤某个命名空间下的数据。只有配置了支持的索引与 Embedding 等能力，才涉及语义搜索。

不要看到 `store.search(...)` 就推断已经完成向量化。教程偏好示例使用精确 key 读取，没有语义检索。

## 5. 消息历史如何控制长度

历史无限增长会增加成本，触碰上下文限制，并让旧错误持续影响后续回答。

可采用：保留最近若干轮、保留系统规则与关键业务事实、将较旧历史总结为摘要、把长期偏好写到独立存储。

删除消息时要维护工具协议完整性：一条 AI 工具调用与对应 ToolMessage 应匹配。不能只按数组长度粗暴删掉中间一半。

## 6. 摘要也是有损信息

原话：“我这次演示用中文，但生产界面用英文。”

错误摘要：“用户永远偏好中文。”

长期记忆应保留事实来源、适用范围、更新时间和置信依据。对临时状态与稳定偏好区分处理，必要时让用户确认。

## 7. 写记忆需要规则

可以建立一个受控流程：识别候选事实→判断是否适合长期保存→核对是否与已有记录冲突→保存结构化条目→记录来源和时间。

不能默认把模型推测的个人属性当事实存储。资料中的恶意指令也不应自动进入“用户永久规则”。

## 8. 缓存与记忆不是同一个概念

缓存为了减少重复计算，通常可以重新计算；记忆是应用希望保留的业务数据。两者可能都使用键值存储，但生命周期和验收标准不同。

缓存键需要包含模型、提示、数据版本与权限范围。记忆更新则需要来源、覆盖和删除策略。

## 9. 删除与权限撤销

删除用户信息时要考虑 Store、检查点、摘要、缓存、追踪日志和备份。只删除当前 messages 不等于删除历史检查点。

同一用户不同项目也可能需要分隔：例如 `(tenant_id, user_id, project_id, memory_type)`。具体粒度按业务规则决定。

## 10. 本章验收

切换 thread 后仍能按用户读取长期偏好；不同用户不会串数据；重启后清楚哪些内存数据会消失；删除记录确实不可读；摘要没有把条件性偏好变成永久事实。
