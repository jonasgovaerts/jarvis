"""Chat tool-flow tests with a scripted FunctionModel — no real LLM."""

from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from gateway.chat.service import ChatDeps, build_chat_agent


class StubOps:
    def __init__(self):
        self.calls = []

    async def create_feature_request_workitem(self, namespace, **kwargs):
        self.calls.append(kwargs)
        return "fr-stub1234"


def scripted_model(repo_arg: str) -> FunctionModel:
    def fn(messages, info: AgentInfo) -> ModelResponse:
        last_parts = messages[-1].parts
        if any(isinstance(p, ToolReturnPart) for p in last_parts):
            tool_result = next(p for p in last_parts if isinstance(p, ToolReturnPart)).content
            if str(tool_result).startswith("ERROR"):
                return ModelResponse(parts=[TextPart("Which repository did you mean?")])
            return ModelResponse(parts=[TextPart("Queued! Tracking it on the board.")])
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="create_feature_request",
                    args={
                        "repository": repo_arg,
                        "title": "Dark mode",
                        "description": "Add a dark theme toggle",
                    },
                )
            ]
        )

    return FunctionModel(fn)


async def test_valid_repo_creates_workitem():
    stub = StubOps()
    deps = ChatDeps(repos=["my-blog"], session_id="s1", namespace="jarvis", _ops=stub)
    agent = build_chat_agent()
    result = await agent.run(
        "user: add dark mode to my blog", deps=deps, model=scripted_model("my-blog")
    )
    assert deps.created_workflow == "fr-stub1234"
    assert stub.calls[0]["repository"] == "my-blog"
    assert "Queued" in result.output


async def test_unknown_repo_forces_clarification():
    stub = StubOps()
    deps = ChatDeps(repos=["my-blog"], session_id="s1", namespace="jarvis", _ops=stub)
    agent = build_chat_agent()
    result = await agent.run("user: add dark mode", deps=deps, model=scripted_model("not-a-repo"))
    assert deps.created_workflow == ""
    assert stub.calls == []
    assert "Which repository" in result.output
