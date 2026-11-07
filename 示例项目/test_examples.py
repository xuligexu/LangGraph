"""使用真实 LangGraph 运行时验证控制流；不调用真实聊天模型。"""
import asyncio
import json
from operator import add
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Annotated, TypedDict
import unittest

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.errors import GraphRecursionError, InvalidUpdateError
from langgraph.graph import END, START, StateGraph
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command, interrupt

from approval import build_review_graph
from basics import build_counter, build_greeting
from patterns import UserContext, build_batch_graph, build_parent_graph, build_preference_graph, sum_squares
from rag_workflow import build_rag_graph
from tool_agent import build_tool_agent


class GraphTests(unittest.TestCase):
    def test_greeting_and_async(self):
        graph = build_greeting()
        self.assertEqual(graph.invoke({"name": " 小王 "})["greeting"], "你好，小王！")
        result = asyncio.run(graph.ainvoke({"name": "小李"}))
        self.assertEqual(result["greeting"], "你好，小李！")

    def test_counter_boundary_and_reducer(self):
        graph = build_counter()
        result = graph.invoke({"count": 0, "target": 3, "events": []})
        self.assertEqual(result["count"], 3)
        self.assertEqual(result["events"], ["count=1", "count=2", "count=3"])
        self.assertEqual(graph.invoke({"count": 0, "target": 0, "events": []})["events"], [])

    def test_recursion_guard(self):
        with self.assertRaises(GraphRecursionError):
            build_counter().invoke({"count": 0, "target": 100, "events": []}, {"recursion_limit": 2})

    def test_tool_protocol(self):
        messages = build_tool_agent().invoke({"messages": [HumanMessage(content="6")]})["messages"]
        self.assertEqual(len(messages), 4)
        self.assertIsInstance(messages[1], AIMessage)
        self.assertIsInstance(messages[2], ToolMessage)
        self.assertEqual(messages[1].tool_calls[0]["id"], messages[2].tool_call_id)
        self.assertIn("12", messages[-1].content)

    def test_stream_updates_and_v3(self):
        graph = build_greeting()
        updates = list(graph.stream({"name": "小王"}, stream_mode="updates"))
        self.assertEqual(updates[0]["greet"]["greeting"], "你好，小王！")
        run = graph.stream_events({"name": "小李"}, version="v3")
        snapshots = list(run.values)
        self.assertTrue(snapshots)
        self.assertEqual(run.output["greeting"], "你好，小李！")

    def test_send_empty_and_multiple_jobs(self):
        graph = build_batch_graph()
        result = graph.invoke({"jobs": [{"id": "a", "value": 2}, {"id": "b", "value": 3}], "reports": []})
        self.assertEqual(result["total"], 13)
        self.assertEqual({r["id"] for r in result["reports"]}, {"a", "b"})
        self.assertEqual(graph.invoke({"jobs": [], "reports": []})["total"], 0)

    def test_subgraph_and_functional(self):
        self.assertEqual(build_parent_graph().invoke({"value": 5})["description"], "子图结果：10")
        self.assertEqual(sum_squares.invoke([2, 3, 4]), 29)

    def test_store_namespace(self):
        store = InMemoryStore()
        store.put(("users", "u1", "preferences"), "language", {"value": "中文"})
        graph = build_preference_graph(store)
        self.assertEqual(graph.invoke({}, context=UserContext("u1"))["message"], "语言偏好：中文")
        self.assertEqual(graph.invoke({}, context=UserContext("u2"))["message"], "语言偏好：未设置")

    def test_parallel_conflict(self):
        class State(TypedDict):
            value: int
        builder = StateGraph(State)
        builder.add_node("a", lambda s: {"value": 1})
        builder.add_node("b", lambda s: {"value": 2})
        builder.add_edge(START, "a")
        builder.add_edge(START, "b")
        builder.add_edge("a", END)
        builder.add_edge("b", END)
        with self.assertRaises(InvalidUpdateError):
            builder.compile().invoke({"value": 0})

    def test_thread_isolation_and_new_input_merge(self):
        graph = build_counter(InMemorySaver())
        c1 = {"configurable": {"thread_id": "one"}}
        c2 = {"configurable": {"thread_id": "two"}}
        graph.invoke({"count": 0, "target": 1, "events": []}, c1)
        result = graph.invoke({"target": 2}, c1)
        self.assertEqual(result["events"], ["count=1", "count=2"])
        self.assertEqual(graph.get_state(c2).values, {})

    def test_approval_both_branches_and_sqlite_reopen(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "review.sqlite")
            for decision in ["approve", "reject"]:
                config = {"configurable": {"thread_id": decision}}
                with SqliteSaver.from_conn_string(path) as saver:
                    graph = build_review_graph(saver)
                    paused = graph.invoke({"topic": "测试公告"}, config)
                    self.assertIn("__interrupt__", paused)
                    digest = graph.get_state(config).values["draft_hash"]
                with SqliteSaver.from_conn_string(path) as saver:
                    graph = build_review_graph(saver)
                    result = graph.invoke(Command(resume={"action": decision, "draft_hash": digest}), config)
                    self.assertEqual(result["status"], "approved" if decision == "approve" else "rejected")
                    self.assertEqual(graph.get_state(config).next, ())

    def test_approval_separate_processes(self):
        script = Path(__file__).with_name("approval.py")
        with tempfile.TemporaryDirectory() as folder:
            db = str(Path(folder) / "process.sqlite")
            command = [sys.executable, "-B", "-X", "utf8", str(script)]
            start = subprocess.run(command + ["start", "--thread", "p1", "--topic", "Process test", "--db", db],
                                   capture_output=True, text=True, encoding="utf-8", check=True)
            self.assertTrue(json.loads(start.stdout)["interrupts"])
            resume = subprocess.run(command + ["resume", "--thread", "p1", "--decision", "approve", "--db", db],
                                    capture_output=True, text=True, encoding="utf-8", check=True)
            self.assertEqual(json.loads(resume.stdout)["values"]["status"], "approved")
            repeated = subprocess.run(command + ["resume", "--thread", "p1", "--decision", "approve", "--db", db],
                                      capture_output=True, text=True, encoding="utf-8")
            self.assertNotEqual(repeated.returncode, 0)

    def test_interrupt_reexecutes_node_prefix(self):
        class State(TypedDict):
            approved: bool
        executions = []
        def review(state):
            executions.append("entered")
            value = interrupt({"question": "continue?"})
            return {"approved": value}
        builder = StateGraph(State)
        builder.add_node("review", review)
        builder.add_edge(START, "review")
        builder.add_edge("review", END)
        graph = builder.compile(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "reenter"}}
        graph.invoke({"approved": False}, config)
        graph.invoke(Command(resume=True), config)
        self.assertEqual(len(executions), 2)

    def test_error_resume_does_not_repeat_previous_node(self):
        class State(TypedDict):
            value: int
        called = []
        def first(state):
            called.append("first")
            return {"value": 1}
        def second(state):
            called.append("second")
            if called.count("second") == 1:
                raise ConnectionError("temporary")
            return {"value": 2}
        builder = StateGraph(State)
        builder.add_node("first", first)
        builder.add_node("second", second)
        builder.add_edge(START, "first")
        builder.add_edge("first", "second")
        builder.add_edge("second", END)
        graph = builder.compile(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "failure"}}
        with self.assertRaises(ConnectionError):
            graph.invoke({"value": 0}, config)
        self.assertEqual(graph.invoke(None, config)["value"], 2)
        self.assertEqual(called, ["first", "second", "second"])

    def test_rag_direct_rewrite_refusal_and_budget(self):
        graph = build_rag_graph()
        direct = graph.invoke({"question": "退款多久到账"})
        self.assertEqual((direct["status"], direct["attempts"]), ("answered", 1))
        rewritten = graph.invoke({"question": "买完想退掉"})
        self.assertEqual((rewritten["status"], rewritten["attempts"]), ("answered", 2))
        for question in ["年度专业版多少钱", "火星天气"]:
            result = graph.invoke({"question": question})
            self.assertEqual((result["status"], result["attempts"]), ("refused", 2))
        limited = graph.invoke({"question": "买完想退掉", "max_attempts": 1})
        self.assertEqual(limited["status"], "refused")

    def test_rag_retry_is_distinct_from_retrieval_attempts(self):
        calls = []
        def unreliable(query):
            calls.append(query)
            if len(calls) == 1:
                raise ConnectionError("temporary")
            return [{"id": "test", "text": "退款规则"}]
        result = build_rag_graph(retriever=unreliable).invoke({"question": "退款"})
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["attempts"], 1)

    def test_rag_validation_and_request_reset(self):
        graph = build_rag_graph(generator=lambda q, d: "错误引用[99]", checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "rag"}}
        first = graph.invoke({"question": "退款"}, config)
        self.assertTrue(first["warnings"])
        second = graph.invoke({"question": "火星天气"}, config)
        self.assertEqual(second["status"], "refused")
        self.assertEqual(second["sources"], [])
        self.assertEqual(second["warnings"], [])

    def test_time_travel_fork(self):
        graph = build_greeting(InMemorySaver())
        config = {"configurable": {"thread_id": "history"}}
        graph.invoke({"name": "旧名字"}, config)
        before = next(s for s in graph.get_state_history(config) if s.next == ("greet",))
        fork = graph.update_state(before.config, {"name": "新名字"}, as_node=START)
        self.assertEqual(graph.invoke(None, fork)["greeting"], "你好，新名字！")
        self.assertEqual(graph.get_state(before.config).values["name"], "旧名字")


if __name__ == "__main__":
    unittest.main()
