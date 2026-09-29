"""0.2.0: cost, idempotency, checkpoint resume, Ollama, and RunResult."""

from pydantic import BaseModel

from safe_agent_harness import (
    Budget,
    BudgetExceeded,
    CostBudget,
    FakeModel,
    Harness,
    MemorySink,
    OllamaClient,
    Risk,
    RunResult,
    Tool,
    ToolRegistry,
    Tracer,
    allow_all,
)


class Ping(BaseModel):
    note: str = "ok"


def test_dollar_cap_raises():
    money = CostBudget(max_dollars=1)
    money.charge(0, dollars=1)
    try:
        money.charge(0, dollars=0.01, count_step=False)
    except BudgetExceeded as exc:
        assert "dollar limit" in str(exc)
    else:
        raise AssertionError("dollar cap did not trip")


def test_gpu_cap():
    gpu = Budget(max_gpu_minutes=1)
    try:
        gpu.charge(0, gpu_minutes=1.5, count_step=False)
    except BudgetExceeded as exc:
        assert "gpu-minute limit" in str(exc)
    else:
        raise AssertionError("gpu cap did not trip")


def test_model_cost_stops_the_run():
    tools = ToolRegistry()
    harness = Harness([FakeModel(["hello"], dollars=2)], tools, budget=lambda: Budget(max_dollars=1))
    assert "dollar limit" in harness.run("u", "s", "go")


def test_irreversible_key_required_and_duplicate_rejected():
    calls = []

    def spend(args):
        calls.append(args.order_id)
        return "sent"

    class Pay(BaseModel):
        order_id: str

    tool = Tool("pay", "pay", Pay, spend, Risk.IRREVERSIBLE)
    script = [
        ("pay", {"order_id": "A1"}),
        ("pay", {"order_id": "A1", "idempotency_key": "k1"}),
        ("pay", {"order_id": "A1", "idempotency_key": "k1"}),
        "done",
    ]
    harness = Harness([FakeModel(script)], ToolRegistry([tool]), approver=allow_all, retry_base=0)
    sink = MemorySink()
    harness.tracer = Tracer(sink)
    assert harness.run("u", "s", "pay") == "done"
    assert calls == ["A1"]
    reasons = [event["reason"] for event in sink.of("idempotency_rejected")]
    assert reasons == ["missing", "duplicate"]


def test_checkpoint_resume_finishes_a_running_step(tmp_path):
    path = tmp_path / "run.json"

    class Stop(FakeModel):
        def step(self, system, messages, tools):
            if self.i == 0:
                self.i += 1
                return {"text": "", "tokens": 1, "dollars": 0, "gpu_minutes": 0,
                        "tool_calls": [{"id": "c1", "name": "ping", "input": {"note": "a"}}]}
            raise RuntimeError("stop the run")

    ping = Tool("ping", "ping", Ping, lambda a: "pong")
    first = Harness([Stop([])], ToolRegistry([ping]), retry_base=0)
    assert "internal error" in first.run("u", "s", "overnight", checkpoint=path)
    assert path.is_file()

    second = Harness([FakeModel(["finished"])], ToolRegistry([ping]), retry_base=0)
    assert second.resume(path) == "finished"


def test_resume_of_a_finished_run_returns_the_answer(tmp_path):
    path = tmp_path / "done.json"
    first = Harness([FakeModel(["saved"])], ToolRegistry(), retry_base=0)
    assert first.run("u", "s", "task", checkpoint=path) == "saved"
    second = Harness([FakeModel(["other"])], ToolRegistry(), retry_base=0)
    assert second.resume(path) == "saved"


def test_resume_missing_file(tmp_path):
    harness = Harness([FakeModel(["x"])], ToolRegistry())
    try:
        harness.resume(tmp_path / "missing.json")
    except FileNotFoundError:
        return
    raise AssertionError("missing checkpoint was accepted")


def test_ollama_step_reports_cost_without_a_socket():
    class Client:
        def chat(self, model, messages, tools=None):
            return {
                "message": {"content": "local", "tool_calls": [
                    {"function": {"name": "ping", "arguments": {"note": "a"}}}
                ]},
                "prompt_eval_count": 2,
                "eval_count": 3,
                "total_duration": 30_000_000_000,
            }

    step = OllamaClient("llama", client=Client(), dollars_per_minute=2).step("sys", [], [])
    assert step["text"] == "local"
    assert step["tool_calls"][0]["name"] == "ping"
    assert step["tokens"] == 5
    assert step["gpu_minutes"] == 0.5
    assert step["dollars"] == 1.0


def test_run_stays_a_string_and_structured_is_a_result():
    harness = Harness([FakeModel(["plain"])], ToolRegistry())
    assert harness.run("u", "s", "task") == "plain"
    result = harness.run("u", "s2", "task", structured=True)
    assert isinstance(result, RunResult)
    assert result.answer == "plain" and result.status == "ok" and result.steps == 1
