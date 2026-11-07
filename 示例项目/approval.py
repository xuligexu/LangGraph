"""跨进程审批演示：只保存决定，不执行真实发布。"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Literal, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class ReviewState(TypedDict, total=False):
    topic: str
    draft: str
    draft_hash: str
    approved: bool
    status: str
    result: str


def prepare(state):
    topic = state["topic"].strip()
    if not topic or len(topic) > 200:
        raise ValueError("主题长度应为 1 至 200 字符")
    draft = f"关于“{topic}”的教学演示草稿。此程序不会真实发布内容。"
    return {"draft": draft, "draft_hash": hashlib.sha256(draft.encode()).hexdigest(),
            "status": "awaiting_review", "approved": False, "result": ""}


def review(state) -> Command[Literal["accepted", "rejected"]]:
    decision = interrupt({"kind": "draft_review", "draft": state["draft"],
                          "draft_hash": state["draft_hash"],
                          "choices": ["approve", "reject"]})
    if not isinstance(decision, dict) or decision.get("action") not in {"approve", "reject"}:
        raise ValueError("审批值必须是包含 action=approve/reject 的对象")
    if decision.get("draft_hash") != state["draft_hash"]:
        raise ValueError("审批草稿哈希不匹配")
    approved = decision["action"] == "approve"
    return Command(update={"approved": approved}, goto="accepted" if approved else "rejected")


def accepted(state):
    if not state.get("approved"):
        raise ValueError("未批准的状态不能进入 accepted")
    return {"status": "approved", "result": "已记录批准；演示结束，未进行真实发布。"}


def rejected(state):
    return {"status": "rejected", "result": "已记录拒绝；未进行发布。"}


def build_review_graph(checkpointer):
    builder = StateGraph(ReviewState)
    for name, function in [("prepare", prepare), ("review", review),
                           ("accepted", accepted), ("rejected", rejected)]:
        builder.add_node(name, function)
    builder.add_edge(START, "prepare")
    builder.add_edge("prepare", "review")
    builder.add_edge("accepted", END)
    builder.add_edge("rejected", END)
    return builder.compile(checkpointer=checkpointer)


def snapshot_view(snapshot):
    return {"values": snapshot.values, "next": list(snapshot.next),
            "interrupts": [item.value for task in snapshot.tasks for item in task.interrupts]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "show", "resume"])
    parser.add_argument("--thread", required=True)
    parser.add_argument("--db", type=Path, default=Path("checkpoints.sqlite"))
    parser.add_argument("--topic", default="")
    parser.add_argument("--decision", choices=["approve", "reject"])
    args = parser.parse_args()
    args.db.parent.mkdir(parents=True, exist_ok=True)
    config = {"configurable": {"thread_id": args.thread}}
    with SqliteSaver.from_conn_string(str(args.db)) as saver:
        graph = build_review_graph(saver)
        snapshot = graph.get_state(config)
        if args.action == "start":
            if snapshot.values:
                raise ValueError("thread 已存在；请用 show/resume 或换一个新 thread")
            graph.invoke({"topic": args.topic}, config)
        elif args.action == "resume":
            if not args.decision:
                raise ValueError("resume 需要 --decision")
            if not any(task.interrupts for task in snapshot.tasks):
                raise ValueError("当前 thread 没有等待审批的 interrupt")
            graph.invoke(Command(resume={"action": args.decision,
                                         "draft_hash": snapshot.values["draft_hash"]}), config)
        elif not snapshot.values:
            raise ValueError("thread 不存在")
        print(json.dumps(snapshot_view(graph.get_state(config)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        sys.exit(1)
