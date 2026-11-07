"""真实 ToolNode + 确定性模拟 model；不访问模型服务。"""
import argparse
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition


@tool
def double_number(value: int) -> int:
    """返回整数 value 的两倍。"""
    return value * 2


def simulated_model(state: MessagesState):
    last = state["messages"][-1]
    if isinstance(last, ToolMessage):
        return {"messages": [AIMessage(content=f"计算结果：{last.content}")]}
    if not isinstance(last, HumanMessage):
        raise ValueError("模拟模型只接受整数用户输入或工具结果")
    value = int(last.content)
    if abs(value) > 1_000_000:
        raise ValueError("教学输入范围为 -1000000 至 1000000")
    return {"messages": [AIMessage(content="", tool_calls=[{
        "name": "double_number", "args": {"value": value},
        "id": "double_call_1", "type": "tool_call",
    }])]}


def build_tool_agent():
    builder = StateGraph(MessagesState)
    builder.add_node("model", simulated_model)
    builder.add_node("tools", ToolNode([double_number]))
    builder.add_edge(START, "model")
    builder.add_conditional_edges("model", tools_condition, {"tools": "tools", END: END})
    builder.add_edge("tools", "model")
    return builder.compile()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("number", type=int, nargs="?", default=6)
    args = parser.parse_args()
    result = build_tool_agent().invoke(
        {"messages": [HumanMessage(content=str(args.number))]},
        {"recursion_limit": 10},
    )
    for message in result["messages"]:
        print(type(message).__name__, message.content, getattr(message, "tool_calls", ""))
