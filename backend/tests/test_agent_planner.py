"""
Tests for the bounded general-purpose agent loop (app/agents/planner.py).

Uses a scripted mock gateway (queued chat_completion responses) rather than
a real model -- these tests verify the loop's control flow (step bounding,
tool dispatch via the real LocalToolRegistry, parsing, stopping conditions),
not model quality. The live end-to-end test against a real local model is
run separately, outside the automated suite.
"""
import asyncio
import unittest

from app.gateway.base import ModelGateway
from app.services.tools import LocalToolRegistry
from app.agents.planner import run_agent_task, _extract_json_object, _parse_response


class ScriptedGateway(ModelGateway):
    """Returns each queued response in order, one per chat_completion() call."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.call_count = 0

    async def chat_completion(self, messages, options=None):
        self.call_count += 1
        if not self._responses:
            raise AssertionError("ScriptedGateway ran out of queued responses")
        return self._responses.pop(0)

    async def generate(self, prompt: str, system_prompt: str = None) -> str:
        raise NotImplementedError

    async def analyze(self, request):
        raise NotImplementedError

    async def stream_chat_completion(self, messages, options=None):
        raise NotImplementedError
        yield  # pragma: no cover

    async def unavailable_chat_completion(self, *args, **kwargs):
        raise RuntimeError("model unavailable")


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestResponseParsing(unittest.TestCase):
    def test_parses_action_and_json_input(self):
        text = (
            'Thought: I should write a file.\n'
            'Action: write_file\n'
            'Action Input: {"workspace_id": "ws-1", "path": "a.txt", "content": "hi"}'
        )
        step = _parse_response(text)
        self.assertEqual(step.action, "write_file")
        self.assertEqual(step.action_input["path"], "a.txt")
        self.assertFalse(step.is_final)

    def test_parses_final_answer(self):
        text = "Thought: Done.\nFinal Answer: The mean is 86.5."
        step = _parse_response(text)
        self.assertTrue(step.is_final)
        self.assertEqual(step.final_answer, "The mean is 86.5.")

    def test_extract_json_object_ignores_trailing_prose(self):
        obj = _extract_json_object('{"a": 1, "b": [1,2,3]} some trailing note')
        self.assertEqual(obj, {"a": 1, "b": [1, 2, 3]})

    def test_unparseable_response_has_no_action_or_final(self):
        step = _parse_response("I am thinking about this but said nothing structured.")
        self.assertIsNone(step.action)
        self.assertFalse(step.is_final)


class TestAgentLoop(unittest.TestCase):
    def test_stops_on_final_answer_after_one_tool_call(self):
        gateway = ScriptedGateway([
            'Thought: Let me compute variance.\n'
            'Action: compute_variance_across_readings\n'
            'Action Input: {"readings": [78, 82, 91, 95]}',
            'Thought: I have the stats now.\n'
            'Final Answer: Mean is 86.5, min 78, max 95.',
        ])
        registry = LocalToolRegistry()
        result = run(run_agent_task(
            gateway=gateway,
            tool_registry=registry,
            goal="Compute mean/min/max of [78, 82, 91, 95]",
            workspace_id="ws-planner-test-1",
        ))
        self.assertEqual(result.stopped_reason, "final_answer")
        self.assertEqual(len(result.steps), 2)
        self.assertEqual(result.steps[0].action, "compute_variance_across_readings")
        self.assertEqual(result.steps[0].observation_status, "success")
        self.assertIn("86.5", result.final_answer)
        self.assertEqual(gateway.call_count, 2)

    def test_respects_max_steps_hard_bound(self):
        # Gateway never gives a Final Answer -- loop must still stop.
        responses = [
            f'Thought: still working ({i}).\n'
            'Action: list_files\n'
            'Action Input: {"workspace_id": "ws-planner-test-2"}'
            for i in range(10)
        ]
        gateway = ScriptedGateway(responses)
        registry = LocalToolRegistry()
        result = run(run_agent_task(
            gateway=gateway,
            tool_registry=registry,
            goal="Never finish",
            workspace_id="ws-planner-test-2",
            max_steps=3,
        ))
        self.assertEqual(result.stopped_reason, "max_steps")
        self.assertEqual(len(result.steps), 3)
        self.assertEqual(gateway.call_count, 3)

    def test_default_max_steps_is_eight(self):
        from app.agents.planner import MAX_AGENT_STEPS
        self.assertEqual(MAX_AGENT_STEPS, 8)

    def test_stops_after_two_consecutive_unparseable_replies(self):
        gateway = ScriptedGateway([
            "I am rambling without structure.",
            "Still rambling, no Action or Final Answer here either.",
        ])
        registry = LocalToolRegistry()
        result = run(run_agent_task(
            gateway=gateway,
            tool_registry=registry,
            goal="Do something",
            workspace_id="ws-planner-test-3",
            max_steps=8,
        ))
        self.assertEqual(result.stopped_reason, "no_progress")
        self.assertEqual(gateway.call_count, 2)

    def test_tool_calls_only_go_through_registry_unregistered_tool_fails_cleanly(self):
        gateway = ScriptedGateway([
            'Thought: try something unregistered.\n'
            'Action: delete_everything\n'
            'Action Input: {}',
            'Thought: that failed, giving up.\n'
            'Final Answer: Could not complete the task.',
        ])
        registry = LocalToolRegistry()
        result = run(run_agent_task(
            gateway=gateway,
            tool_registry=registry,
            goal="Try a disallowed action",
            workspace_id="ws-planner-test-4",
        ))
        self.assertEqual(result.steps[0].observation_status, "failed")
        self.assertIn("not registered", str(result.steps[0].observation))
        self.assertEqual(result.stopped_reason, "final_answer")

    def test_workspace_id_is_auto_injected_when_model_omits_it(self):
        gateway = ScriptedGateway([
            'Thought: write a note but forget workspace_id.\n'
            'Action: write_file\n'
            'Action Input: {"path": "note.txt", "content": "hello"}',
            'Thought: done.\nFinal Answer: Wrote the note.',
        ])
        registry = LocalToolRegistry()
        result = run(run_agent_task(
            gateway=gateway,
            tool_registry=registry,
            goal="Write a note",
            workspace_id="ws-planner-test-5",
        ))
        self.assertEqual(result.steps[0].observation_status, "success")

    def test_gateway_failure_is_reported_not_raised(self):
        class FailingGateway(ScriptedGateway):
            async def chat_completion(self, messages, options=None):
                raise RuntimeError("local model process crashed")

        gateway = FailingGateway([])
        registry = LocalToolRegistry()
        result = run(run_agent_task(
            gateway=gateway,
            tool_registry=registry,
            goal="This will fail immediately",
            workspace_id="ws-planner-test-6",
        ))
        self.assertEqual(result.stopped_reason, "error")
        self.assertIn("unavailable", result.final_answer)


if __name__ == "__main__":
    unittest.main()
