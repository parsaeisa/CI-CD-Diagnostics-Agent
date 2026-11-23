import os
import re

from dotenv import load_dotenv
import requests
from github import Github, Auth
from fastmcp import FastMCP

load_dotenv()
mcp = FastMCP("github-ci-context-server")

GITHUB_API_URL = "https://api.github.com"

# Each raw log line starts with an ISO-8601 timestamp, e.g. "2024-05-01T12:00:00.1234567Z ".
_TIMESTAMP_RE = re.compile(r"^\ufeff?\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z ?")
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
# GitHub Actions marks failures with "##[error]"; the exit-code line closes a failed step.
_ERROR_MARKER_RE = re.compile(r"##\[error\]|Process completed with exit code [1-9]")

@mcp.tool()
def get_failed_run_logs(repo_name: str, run_id: int) -> str:
    """
    Retrieves the log output of the failed jobs of a specific Workflow Run,
    trimmed to the lines around the errors (stack traces, failing assertions,
    compiler errors). Also reports the commit SHA the run was executed on, which
    should be used as 'ref' when reading files with get_file_content.

    :param repo_name: Repository name like 'owner/repo'
    :param run_id: Numeric ID of the workflow run
    """
    gh = _get_github_client()
    repo = gh.get_repo(repo_name)
    run = repo.get_workflow_run(run_id)

    output = [
        f"Workflow run {run_id}: '{run.name}' (conclusion: {run.conclusion})",
        f"Branch: {run.head_branch}  Commit SHA: {run.head_sha}",
        "",
    ]
    found_failure = False

    for job in run.jobs():
        if job.conclusion != "failure":
            continue
        found_failure = True
        output.append(f"=== Job: {job.name} (id: {job.id}, conclusion: {job.conclusion}) ===")
        failed_steps = [step.name for step in job.steps if step.conclusion == "failure"]
        if failed_steps:
            output.append("Failed steps: " + ", ".join(f"'{name}'" for name in failed_steps))

        try:
            raw_log = _download_job_log(repo_name, job.id)
            output.append("--- Log excerpt ---")
            output.append(extract_relevant_log(raw_log))            
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            output.append(f"(Could not download log for this job: HTTP {status}. "
                          "Logs may have expired or the token may lack 'actions:read' permission.)")
        except requests.RequestException as exc:
            output.append(f"(Could not download log for this job: {exc})")
        output.append("")

    if not found_failure:
        return f"No failed jobs found in workflow run {run_id} (conclusion: {run.conclusion})."

    return "\n".join(output).rstrip()

@mcp.tool()
def get_file_content(repo_name: str, file_path: str, ref: str | None = None) -> str:
    """
    Retrieves the content of a source file or test definition from the repository (Context Grounding).

    :param repo_name: Repository name like 'owner/repo'
    :param file_path: File path in the repository (e.g., 'tests/test_api.py')
    :param ref: Commit SHA, branch or tag to read from. When diagnosing a failed run, pass the
                commit SHA reported by get_failed_run_logs so the file matches the code that failed.
                If omitted, the repository's default branch is used.
    """
    gh = _get_github_client()
    repo = gh.get_repo(repo_name)
    content_file = repo.get_contents(file_path, ref=ref or repo.default_branch)
    return content_file.decoded_content.decode("utf-8")

def _get_github_client():
    return Github(auth=Auth.Token(_get_token()))

def _get_token() -> str:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ValueError("Environment variable 'GITHUB_TOKEN' is not set.")
    return token

def _download_job_log(repo_name: str, job_id: int) -> str:
    """Download the full plain-text log of a single job.

    The API answers with a redirect to a short-lived signed URL; requests follows it
    and drops the Authorization header on the cross-host hop, which is what we want.
    """
    response = requests.get(
        f"{GITHUB_API_URL}/repos/{repo_name}/actions/jobs/{job_id}/logs",
        headers={
            "Authorization": f"Bearer {_get_token()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.content.decode("utf-8", errors="replace")

def extract_relevant_log(
    raw_log: str,
    context_before: int = 60,
    context_after: int = 10,
    tail_lines: int = 150,
    max_chars: int = 15000,
) -> str:
    """Reduce a job log to the parts that explain the failure.

    Keeps a window of lines around every error marker (the lines *before* an error
    usually hold the stack trace / failing assertion). If no marker is found, falls
    back to the end of the log. The result is capped at max_chars, keeping the end,
    since the final error is normally the most important one.
    """
    lines = _clean_log_lines(raw_log)
    if not lines:
        return "(log is empty)"

    error_indexes = [i for i, line in enumerate(lines) if _ERROR_MARKER_RE.search(line)]

    if error_indexes:
        # Merge overlapping windows into contiguous [start, end) ranges.
        ranges: list[list[int]] = []
        for i in error_indexes:
            start, end = max(0, i - context_before), min(len(lines), i + context_after + 1)
            if ranges and start <= ranges[-1][1]:
                ranges[-1][1] = max(ranges[-1][1], end)
            else:
                ranges.append([start, end])
        chunks = []
        for start, end in ranges:
            if start > 0:
                chunks.append(f"... [{start} lines omitted] ...")
            chunks.extend(lines[start:end])
        if ranges[-1][1] < len(lines):
            chunks.append(f"... [{len(lines) - ranges[-1][1]} lines omitted] ...")
    else:
        omitted = max(0, len(lines) - tail_lines)
        chunks = ([f"... [{omitted} lines omitted, no error marker found] ..."] if omitted else [])
        chunks.extend(lines[-tail_lines:])

    text = "\n".join(chunks)
    if len(text) > max_chars:
        text = "... [truncated] ...\n" + text[-max_chars:]
    return text

def _clean_log_lines(raw_log: str) -> list[str]:
    """Strip timestamps and ANSI color codes so the model sees only the content."""
    return [_ANSI_RE.sub("", _TIMESTAMP_RE.sub("", line)) for line in raw_log.splitlines()]

if __name__ == "__main__":
    mcp.run(transport="stdio")
