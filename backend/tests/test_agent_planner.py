"""
Tests for the bounded agentic loop (app/agents/planner.py). Uses a scripted
mock gateway (deterministic, no real LLM call) so step-limit/parsing/
tool-wiring logic is tested fast and reliably -- a real end-to-end run
against the live qwen3.5:4b model was verified separately (see the project
audit report), not duplicated here as a slow/flaky unit test.
"""
import shutil
import tempfile
import unittest
from pathlib import Path

from app.config import settings
from app.gateway.base import ModelGateway
from app.services.tools import LocalToolRegistry
from app.agents.planner import run_agent_task, _parse_response, _extract_json_object, MAX_AGENT_STEPS


class ScriptedGateway(ModelGateway):
    """Returns each entry in `script` in order, one per chat_completion call."""
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    async def analyze(self, request):
        raise NotImplementedError

    async def generate(self, prompt, system_prompt=None):
        raise NotImplementedError

    async def chat_completion(self, messages, options=None):
        self.calls.append(messages)
        if not self.script:
            return "Thought: out of script.\nFinal Answer: (scripted gateway exhausted)"
        return self.script.pop(0)

    async def stream_chat_completion(self, messages, options=None):
        raise NotImplementedError


def _run(coro):
    import asyncio
    # asyncio.run() (fresh loop per call, cleanly closed) rather than
    # asyncio.get_event_loop() -- the latter is flaky when this suite runs
    # alongside pytest-asyncio-managed tests elsewhere.
    return asyncio.run(coro)


class TestResponseParsing(unittest.TestCase):
    def test_parses_action_and_json_input(self):
        text = (
            'Thought: I should list files first.\n'
            'Action: list_files\n'
            'Action Input: {"workspace_id": "ws-1"}'
        )
        step = _parse_response(text)
        self.assertEqual(step.action, "list_files")
        self.assertEqual(step.action_input, {"workspace_id": "ws-1"})
        self.assertFalse(step.is_final)

    def test_parses_final_answer(self):
        text = "Thought: I'm done.\nFinal Answer: The answer is 42."
        step = _parse_response(text)
        self.assertTrue(step.is_final)
        self.assertEqual(step.final_answer, "The answer is 42.")

    def test_final_answer_takes_precedence_when_both_present(self):
        text = "Thought: done.\nFinal Answer: here it is.\nAction: read_file"
        step = _parse_response(text)
        self.assertTrue(step.is_final)

    def test_extract_json_object_ignores_trailing_prose(self):
        text = '{"a": 1, "b": "two"}\nSome trailing commentary the model added.'
        obj = _extract_json_object(text)
        self.assertEqual(obj, {"a": 1, "b": "two"})

    def test_unparseable_response_has_no_action_or_final(self):
        step = _parse_response("I'm just going to ramble without the right format.")
        self.assertIsNone(step.action)
        self.assertFalse(step.is_final)


class TestAgentLoop(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="sovereignx_test_storage_")
        self._original_storage_path = settings.DOCUMENT_STORAGE_PATH
        settings.DOCUMENT_STORAGE_PATH = str(Path(self._tmp) / "documents")
        self.tool_registry = LocalToolRegistry()

    def tearDown(self):
        settings.DOCUMENT_STORAGE_PATH = self._original_storage_path
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_simple_two_step_task_completes(self):
        gateway = ScriptedGateway([
            'Thought: I will write a file.\n'
            'Action: write_file\n'
            'Action Input: {"workspace_id": "ws-1", "path": "out.txt", "content": "hello"}',
            'Thought: Done.\nFinal Answer: I wrote out.txt with "hello".',
        ])
        result = _run(run_agent_task(gateway, self.tool_registry, "write a greeting file", "ws-1"))
        self.assertEqual(result.stopped_reason, "final_answer")
        self.assertIn("hello", result.final_answer)
        self.assertEqual(len(result.steps), 2)
        self.assertEqual(result.steps[0].action, "write_file")
        self.assertEqual(result.steps[0].observation_status, "success")

    def test_tool_failure_is_observed_not_raised(self):
        gateway = ScriptedGateway([
            'Thought: read a file that does not exist.\n'
            'Action: read_file\n'
            'Action Input: {"workspace_id": "ws-1", "path": "missing.txt"}',
            'Thought: it failed, I will report that.\nFinal Answer: The file was missing.',
        ])
        result = _run(run_agent_task(gateway, self.tool_registry, "read missing.txt", "ws-1"))
        self.assertEqual(result.steps[0].observation_status, "failed")
        self.assertEqual(result.stopped_reason, "final_answer")

    def test_step_limit_is_enforced(self):
        # Script that NEVER gives a Final Answer -- always issues another action.
        infinite_action = (
            'Thought: keep listing files.\nAction: list_files\nAction Input: {"workspace_id": "ws-1"}'
        )
        gateway = ScriptedGateway([infinite_action] * 20)
        result = _run(run_agent_task(gateway, self.tool_registry, "loop forever", "ws-1", max_steps=3))
        self.assertEqual(result.stopped_reason, "max_steps")
        self.assertEqual(len(result.steps), 3)
        self.assertIsNotNone(result.final_answer)

    def test_workspace_id_auto_injected_when_model_omits_it(self):
        gateway = ScriptedGateway([
            # Model forgets workspace_id entirely.
            'Thought: list files.\nAction: list_files\nAction Input: {}',
            'Thought: done.\nFinal Answer: listed.',
        ])
        result = _run(run_agent_task(gateway, self.tool_registry, "list files", "ws-auto"))
        self.assertEqual(result.steps[0].observation_status, "success")
        self.assertEqual(result.steps[0].observation["workspace_id"], "ws-auto")

    def test_repeated_unparseable_output_stops_with_no_progress(self):
        gateway = ScriptedGateway(["gibberish with no action or final answer"] * 5)
        result = _run(run_agent_task(gateway, self.tool_registry, "do something", "ws-1"))
        self.assertEqual(result.stopped_reason, "no_progress")
        self.assertLessEqual(len(result.steps), 3)

    def test_unregistered_tool_call_surfaces_as_failed_observation(self):
        gateway = ScriptedGateway([
            'Thought: try a made-up tool.\nAction: delete_all_data\nAction Input: {}',
            'Thought: that failed as expected.\nFinal Answer: could not use that tool.',
        ])
        result = _run(run_agent_task(gateway, self.tool_registry, "misbehave", "ws-1"))
        self.assertEqual(result.steps[0].observation_status, "failed")
        self.assertIn("not registered", str(result.steps[0].observation))

    def test_default_max_steps_matches_module_constant(self):
        self.assertEqual(MAX_AGENT_STEPS, 8)


if __name__ == "__main__":
    unittest.main()
