"""
Bounded multi-step agent loop -- the MRPL/SIH26117 problem statement's core
"agentic AI workbench" requirement: plan multi-step tasks, call local
tools, observe results, and produce a final deliverable, rather than a
single question-in/answer-out turn.

This is ADDITIVE, not a replacement for the existing four-agent
investigation pipeline (IntakeAgent -> RAGAgent -> AnalysisAgent ->
ReportAgent, see agents.py / api/agents.py's /agents/investigate) -- that
pipeline stays exactly as-is for its purpose (retrieve-then-answer a
document question with a deterministic confidence score). This module adds
a genuinely different capability: a general-purpose bounded agent loop for
tasks that need multiple tool calls in sequence (write code, run it,
inspect the result, adjust).

Deliberately a CONTROLLED loop, not an open-ended autonomous agent:
  - MAX_AGENT_STEPS hard-bounds how many tool calls a single task can make.
  - Every tool call goes through the existing LocalToolRegistry, which only
    ever executes registered tools -- the model cannot invoke anything
    outside that allowlist.
  - Uses ReAct-style structured text prompting (Thought/Action/Action
    Input/Observation, or Thought/Final Answer) rather than requiring
    provider-specific native function-calling, so it works with whichever
    model app.config.settings.MODEL_NAME currently points at without
    depending on that model having been fine-tuned for tool use.
  - Every step (thought, action, arguments, observation) is recorded and
    returned in full -- this IS the audit trail for an agent task, not a
    black box.
"""
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.gateway.base import ModelGateway
from app.services.tools import LocalToolRegistry

logger = logging.getLogger("sovereignx")

MAX_AGENT_STEPS = 8

_ACTION_RE = re.compile(r"Action:\s*(\S+)", re.IGNORECASE)
_ACTION_INPUT_RE = re.compile(r"Action Input:\s*(\{.*)", re.IGNORECASE | re.DOTALL)
_FINAL_ANSWER_RE = re.compile(r"Final Answer:\s*(.*)", re.IGNORECASE | re.DOTALL)
_THOUGHT_RE = re.compile(r"Thought:\s*(.*?)(?=\n(?:Action|Final Answer):|\Z)", re.IGNORECASE | re.DOTALL)


@dataclass
class AgentStep:
    step_number: int
    raw_response: str
    thought: str = ""
    action: Optional[str] = None
    action_input: Optional[Dict[str, Any]] = None
    observation: Optional[Any] = None
    observation_status: Optional[str] = None  # "success" | "failed"
    is_final: bool = False


@dataclass
class AgentRunResult:
    goal: str
    workspace_id: str
    steps: List[AgentStep] = field(default_factory=list)
    final_answer: Optional[str] = None
    stopped_reason: str = "final_answer"  # "final_answer" | "max_steps" | "no_progress" | "error"
    total_ms: float = 0.0


def _build_system_prompt(tool_registry: LocalToolRegistry, workspace_id: str, max_steps: int) -> str:
    tool_lines = []
    for t in tool_registry.list_tools():
        params = ", ".join(
            f'"{name}": <{p.type}{"" if p.required else ", optional"}>'
            for name, p in t.parameters.items()
        )
        tool_lines.append(f"- {t.name}({params}): {t.description}")
    tool_block = "\n".join(tool_lines)

    return f"""You are SovereignX's task-execution agent, running entirely on local infrastructure with no external/cloud access. You solve the user's goal step by step using ONLY the tools listed below -- never invent a tool, never fabricate a tool result.

Available tools:
{tool_block}

Your task workspace_id is "{workspace_id}" -- pass this exact value for any tool that takes a workspace_id parameter; do not invent a different one.

You have at most {max_steps} steps total. Respond with EXACTLY ONE of the following two formats each turn (nothing else):

Thought: <brief reasoning about what to do next>
Action: <exact tool name>
Action Input: <a single valid JSON object of arguments>

OR, once you have everything needed to fully answer the goal:

Thought: <brief reasoning>
Final Answer: <your complete answer/deliverable summary for the user>

Rules:
- Action Input must be valid JSON (use double quotes, no trailing commas).
- Wait for the "Observation:" of one action before deciding the next one -- never chain multiple actions in one reply.
- If a tool fails, read the error and adapt (fix arguments, try a different approach, or explain the limitation in a Final Answer) -- do not repeat the exact same failing call.
- If you cannot fully complete the goal within the remaining steps, give the best Final Answer you can, explicitly stating what could not be completed and why.
"""


def _parse_response(text: str) -> AgentStep:
    step = AgentStep(step_number=-1, raw_response=text)

    final_match = _FINAL_ANSWER_RE.search(text)
    action_match = _ACTION_RE.search(text)

    thought_match = _THOUGHT_RE.search(text)
    if thought_match:
        step.thought = thought_match.group(1).strip()

    # Final Answer takes precedence if both somehow appear (model confusion) --
    # prefer stopping cleanly over executing an unintended action.
    if final_match and (not action_match or final_match.start() < action_match.start()):
        step.is_final = True
        step.final_answer = final_match.group(1).strip()
        return step

    if action_match:
        step.action = action_match.group(1).strip().strip('"').strip("'")
        input_match = _ACTION_INPUT_RE.search(text)
        if input_match:
            raw_json = input_match.group(1).strip()
            # The model may trail extra prose after the JSON object -- take
            # the shortest valid JSON prefix by trying to parse progressively
            # shorter/longer brace-balanced substrings rather than assuming
            # the whole remainder of the response is clean JSON.
            step.action_input = _extract_json_object(raw_json)
        else:
            step.action_input = {}
        return step

    # Neither Final Answer nor Action was parseable -- treat the whole reply
    # as a (non-final) thought and let the caller decide how to recover.
    step.thought = step.thought or text.strip()
    return step


def _extract_json_object(text: str) -> Dict[str, Any]:
    """Best-effort: find the first balanced-brace JSON object in `text`."""
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                candidate = text[start:i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    continue
    raise ValueError(f"Could not parse a JSON object from Action Input: {text[:200]!r}")


async def run_agent_task(
    gateway: ModelGateway,
    tool_registry: LocalToolRegistry,
    goal: str,
    workspace_id: str,
    max_steps: int = MAX_AGENT_STEPS,
) -> AgentRunResult:
    """
    Runs the bounded Thought/Action/Observation loop until the model gives a
    Final Answer, the step limit is reached, or an unrecoverable error
    occurs. Never raises for a model that fails to make progress -- that
    becomes stopped_reason="max_steps" with whatever partial trace exists,
    which the caller surfaces to the user rather than crashing the request.
    """
    t0 = time.perf_counter()
    system_prompt = _build_system_prompt(tool_registry, workspace_id, max_steps)
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Goal: {goal}"},
    ]

    result = AgentRunResult(goal=goal, workspace_id=workspace_id)
    consecutive_parse_failures = 0

    for step_num in range(1, max_steps + 1):
        try:
            raw = await gateway.chat_completion(messages)
        except Exception as e:
            logger.error(f"agent_task step={step_num} gateway call failed: {e}")
            result.stopped_reason = "error"
            result.final_answer = f"The task could not continue: the local model became unavailable ({e})."
            break

        step = _parse_response(raw)
        step.step_number = step_num
        messages.append({"role": "assistant", "content": raw})

        if step.is_final:
            step.observation = None
            result.steps.append(step)
            result.final_answer = step.final_answer
            result.stopped_reason = "final_answer"
            logger.info(f"agent_task goal={goal!r} finished at step={step_num} reason=final_answer")
            break

        if not step.action:
            # Model didn't produce a parseable Action or Final Answer --
            # nudge it once, but don't loop forever on unparseable output.
            consecutive_parse_failures += 1
            if consecutive_parse_failures >= 2:
                result.steps.append(step)
                result.stopped_reason = "no_progress"
                result.final_answer = (
                    "The agent could not produce a valid next step (no Action or Final Answer "
                    "was recognized twice in a row) and stopped rather than continue blindly."
                )
                break
            messages.append({
                "role": "user",
                "content": "Your reply didn't match the required format. Respond with either "
                            "'Thought: ... / Action: ... / Action Input: {...}' or "
                            "'Thought: ... / Final Answer: ...'.",
            })
            result.steps.append(step)
            continue

        consecutive_parse_failures = 0

        # Auto-inject workspace_id if the tool needs it and the model omitted
        # it -- the model was told the exact value to use, but small local
        # models sometimes drop parameters; this is a safety net, not a way
        # to let the model pick an arbitrary workspace.
        tool_def = tool_registry.get_tool(step.action)
        args = dict(step.action_input or {})
        if tool_def and "workspace_id" in tool_def["definition"].parameters and "workspace_id" not in args:
            args["workspace_id"] = workspace_id

        try:
            exec_result = tool_registry.execute(step.action, args, context_id=workspace_id)
            step.observation = exec_result.outputs if exec_result.status == "success" else {"error": exec_result.error}
            step.observation_status = exec_result.status
        except Exception as e:
            logger.error(f"agent_task step={step_num} tool={step.action} raised unexpectedly: {e}")
            step.observation = {"error": str(e)}
            step.observation_status = "failed"

        result.steps.append(step)
        observation_text = json.dumps(step.observation, default=str)[:4000]
        messages.append({
            "role": "user",
            "content": f"Observation: {observation_text}",
        })

    else:
        result.stopped_reason = "max_steps"
        result.final_answer = (
            f"The task did not finish within the {max_steps}-step limit. "
            "Here is what was accomplished so far; consider narrowing the request or continuing in a follow-up."
        )
        logger.warning(f"agent_task goal={goal!r} stopped_reason=max_steps after {max_steps} steps")

    result.total_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    return result
