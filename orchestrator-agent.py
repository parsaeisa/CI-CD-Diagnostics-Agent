import asyncio
import json
import os
import sys

from anthropic import Anthropic
from mcp import ClientSession, StdioServerParameters
from dotenv import load_dotenv
from mcp.client.stdio import stdio_client
from pydantic import BaseModel, Field

load_dotenv()

MAX_AGENT_ITERATIONS = 5

class DiagnosticResult(BaseModel):
    root_cause: str = Field(description="Analysis and root cause of the error")
    proposed_fix: str = Field(description="Exact corrective code or solution")
    unit_test: str = Field(description="New unit test code to validate the fix")

async def run_ci_diagnostic_agent(repo_name: str, run_id: int):
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["ci-cd-diagnostic-agent/github_mcp_server.py"],
        env={**os.environ, "GITHUB_TOKEN": os.environ.get("GITHUB_TOKEN", "")}
    )

    anthropic_client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    # Connect to the MCP server via the STDIO channel
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            
            # There are some TOOLS available in the MCP server, we need to convert them to the format expected by Claude
            mcp_tools_response = await session.list_tools()
            claude_tools = []
            for tool in mcp_tools_response.tools:
                claude_tools.append({
                    "name": tool.name,
                    "description": tool.description or "",
                    "input_schema": tool.input_schema
                })

            final_report_tool = {
                "name": "submit_final_diagnostic",
                "description": "Submit the finalized root cause analysis, deterministic fix, and unit test.",
                "input_schema": DiagnosticResult.model_json_schema()
            }
            claude_tools.append(final_report_tool)

            # Starting prompt for the agent
            messages = [
                {
                    "role": "user",
                    "content": (
                        f"CI run {run_id} failed in repository '{repo_name}'. "
                        "First, fetch the failure logs. Then, read any relevant source/test files "
                        "needed to understand the context, passing the run's commit SHA (shown in "
                        "the logs output) as 'ref' so you read the exact code that failed. "
                        "Finally, provide the diagnosis and fixes "
                        "by calling the 'submit_final_diagnostic' tool."
                    )
                }
            ]

            # Agent loop, capped so a confused model can't spin forever (each turn costs tokens)
            print("[Agent] Starting diagnostic process...")
            for iteration in range(1, MAX_AGENT_ITERATIONS + 1):
                print(f"[Agent] Iteration {iteration}/{MAX_AGENT_ITERATIONS}")
                response = anthropic_client.messages.create(
                    model=os.environ.get("ANTHROPIC_MODEL"),
                    max_tokens=4096,
                    tools=claude_tools,
                    messages=messages
                )

                messages.append({"role": "assistant", "content": response.content})

                # Check if the model called any tools
                tool_calls = [b for b in response.content if b.type == "tool_use"]
            
                # If no tools were called, the loop ends
                if not tool_calls:
                    print("[Agent] Text response received without calling any new tools.")
                    return None

                tool_results_content = []

                for tool_call in tool_calls:
                    tool_name = tool_call.name
                    tool_args = tool_call.input
                    tool_id = tool_call.id

                    # Detection of final diagnostic submission
                    if tool_name == "submit_final_diagnostic":
                        print("[Agent] Final diagnostic report is ready.")
                        final_result = DiagnosticResult(**tool_args)
                        return final_result

                    print(f"[Agent] Calling tool '{tool_name}' with arguments: {tool_args}")
                    result = await session.call_tool(tool_name, arguments=tool_args)
                
                    # Extract the text response from the tool
                    text_output = "\n".join([c.text for c in result.content if hasattr(c, "text")])

                    tool_results_content.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": text_output
                    })

                # This array goes to the next cycle in the Agent loop, so the model can see the results of the tools it called
                messages.append({
                    "role": "user",
                    "content": tool_results_content
                })

            print(f"[Agent] Stopped after {MAX_AGENT_ITERATIONS} iterations without a final diagnostic.")
            return None


if __name__ == "__main__":
    # Example execution
    target_repo = "parsaeisa/ci-cd-diagnostic-agent-sandbox"
    failed_run = 44584440522

    diag = asyncio.run(run_ci_diagnostic_agent(target_repo, failed_run))
    # if diag:
    #     print("\n=== Root cause of the error ===")
    #     print(diag.root_cause)
    #     print("\n=== Proposed fix (Corrective code or solution) ===")
    #     print(diag.proposed_fix)
    #     print("\n=== Unit test (New unit test code to validate the fix) ===")
    #     print(diag.unit_test)

    if diag:
        print(json.dumps(diag.model_dump(), indent=2, ensure_ascii=False))