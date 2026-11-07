"""无模型的最小图与有界循环。"""
from operator import add
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph


class GreetingState(TypedDict):
    name: str
    greeting: str


def greet(state: GreetingState):
    if not state["name"].strip():
        raise ValueError("name 不能为空")
    return {"greeting": f"你好，{state['name'].strip()}！"}


def build_greeting(checkpointer=None):
    builder = StateGraph(GreetingState)
    builder.add_node("greet", greet)
    builder.add_edge(START, "greet")
    builder.add_edge("greet", END)
    return builder.compile(checkpointer=checkpointer)


class CounterState(TypedDict):
    count: int
    target: int
    events: Annotated[list[str], add]


def build_counter(checkpointer=None):
    def increment(state):
        value = state["count"] + 1
        return {"count": value, "events": [f"count={value}"]}

    def route(state):
        if state["target"] < 0 or state["count"] < 0:
            raise ValueError("count 与 target 必须非负")
        return "increment" if state["count"] < state["target"] else END

    builder = StateGraph(CounterState)
    builder.add_node("increment", increment)
    builder.add_conditional_edges(START, route, ["increment", END])
    builder.add_conditional_edges("increment", route, ["increment", END])
    return builder.compile(checkpointer=checkpointer)


if __name__ == "__main__":
    print(build_greeting().invoke({"name": "学习者"}))
    graph = build_counter()
    for update in graph.stream({"count": 0, "target": 3, "events": []},
                               {"recursion_limit": 20}, stream_mode="updates"):
        print(update)
    print(graph.get_graph().draw_mermaid())
