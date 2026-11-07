"""Send、子图、Runtime/Store、Functional API 的无模型示例。"""
from dataclasses import dataclass
from operator import add
from typing import Annotated, TypedDict

from langgraph.func import entrypoint, task
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.store.memory import InMemoryStore
from langgraph.types import Send


class BatchState(TypedDict):
    jobs: list[dict]
    reports: Annotated[list[dict], add]
    total: int


class JobState(TypedDict):
    job_id: str
    number: int


def build_batch_graph():
    def scatter(state):
        ids = [job["id"] for job in state["jobs"]]
        if len(set(ids)) != len(ids):
            raise ValueError("job id 必须唯一")
        if not state["jobs"]:
            return "gather"
        return [Send("worker", {"job_id": job["id"], "number": job["value"]})
                for job in state["jobs"]]

    def worker(state: JobState):
        return {"reports": [{"id": state["job_id"], "value": state["number"] ** 2}]}

    def gather(state):
        return {"total": sum(item["value"] for item in state["reports"])}

    builder = StateGraph(BatchState)
    builder.add_node("worker", worker)
    builder.add_node("gather", gather)
    builder.add_conditional_edges(START, scatter, ["worker", "gather"])
    builder.add_edge("worker", "gather")
    builder.add_edge("gather", END)
    return builder.compile()


class ChildState(TypedDict):
    value: int


class ParentState(TypedDict):
    value: int
    description: str


def build_parent_graph():
    child = StateGraph(ChildState)
    child.add_node("double", lambda state: {"value": state["value"] * 2})
    child.add_edge(START, "double")
    child.add_edge("double", END)
    parent = StateGraph(ParentState)
    parent.add_node("calculation", child.compile())
    parent.add_node("describe", lambda state: {"description": f"子图结果：{state['value']}"})
    parent.add_edge(START, "calculation")
    parent.add_edge("calculation", "describe")
    parent.add_edge("describe", END)
    return parent.compile()


@dataclass
class UserContext:
    user_id: str


class PreferenceState(TypedDict):
    message: str


def build_preference_graph(store):
    def personalize(state, runtime: Runtime[UserContext]):
        namespace = ("users", runtime.context.user_id, "preferences")
        item = runtime.store.get(namespace, "language")
        language = item.value["value"] if item else "未设置"
        return {"message": f"语言偏好：{language}"}

    builder = StateGraph(PreferenceState, context_schema=UserContext)
    builder.add_node("personalize", personalize)
    builder.add_edge(START, "personalize")
    builder.add_edge("personalize", END)
    return builder.compile(store=store)


@task
def square(number: int):
    return number * number


@entrypoint()
def sum_squares(numbers: list[int]):
    futures = [square(number) for number in numbers]
    return sum(future.result() for future in futures)


if __name__ == "__main__":
    batch = build_batch_graph().invoke({
        "jobs": [{"id": "a", "value": 2}, {"id": "b", "value": 3}], "reports": [],
    })
    print("Send 汇总：", batch)
    print("子图：", build_parent_graph().invoke({"value": 4}))
    store = InMemoryStore()
    store.put(("users", "u1", "preferences"), "language", {"value": "中文"})
    print("Store：", build_preference_graph(store).invoke({}, context=UserContext("u1")))
    print("Functional API：", sum_squares.invoke([2, 3]))
