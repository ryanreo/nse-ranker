"""Ask Claude Haiku a question through the `claude` CLI and get checked JSON back.

Runs `claude -p --model haiku` with no tools, no saved session and no project settings, so Haiku
only reads what we pass in. On a Claude subscription this counts toward normal usage limits.
"""
import json
import shutil
import subprocess

TIMEOUT = 300   # seconds


class HaikuError(RuntimeError):
    pass


def ask(instructions, data, schema, timeout=TIMEOUT):
    """Send `data` (any JSON-able value) with `instructions`; return Haiku's answer as a dict.

    `schema` is a JSON Schema the answer must follow; the CLI enforces it.
    """
    claude = shutil.which("claude")
    if not claude:
        raise HaikuError("The `claude` command isn't on PATH, so Haiku can't run.")
    command = [
        claude, "-p", "--model", "haiku", "--tools", "", "--no-session-persistence",
        "--setting-sources", "", "--output-format", "json", "--json-schema", json.dumps(schema),
        instructions,
    ]
    try:
        done = subprocess.run(command, input=json.dumps(data, ensure_ascii=False), capture_output=True,
                              text=True, encoding="utf-8", timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise HaikuError(f"Haiku took longer than {timeout} s") from error
    try:
        reply = json.loads(done.stdout)
    except json.JSONDecodeError as error:
        raise HaikuError(f"Unexpected reply from claude: {(done.stdout or done.stderr)[:300]}") from error
    if reply.get("is_error") or "structured_output" not in reply:
        raise HaikuError(f"Haiku failed: {str(reply.get('result'))[:300]}")
    return reply["structured_output"]
