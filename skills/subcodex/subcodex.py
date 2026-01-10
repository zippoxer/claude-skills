#!/usr/bin/env python3
"""
subcodex - Named Codex sessions for Claude Code integration

Provides accurate running status tracking with file locking.
"""

import argparse
import fcntl
import json
import os
import random
import signal
import string
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


SUBCODEX_DIR = Path.home() / ".subcodex"
SESSIONS_FILE = SUBCODEX_DIR / "sessions.json"
CONVERSATIONS_DIR = SUBCODEX_DIR / "conversations"
CONFIG_FILE = SUBCODEX_DIR / "config.json"
CODEX_SESSIONS_DIR = Path.home() / ".codex" / "sessions"

DEFAULT_CONFIG = {
    "web-search": True,
    "mode": "dangerous",
    "model": "gpt-5.2",
    "reasoning": "high",
    "review-reasoning": "xhigh",
    "exclusive_cwd": False,
}

# Current session being tracked (for signal handler cleanup)
_current_session: str | None = None


def ensure_dir():
    """Create directories and default files if needed."""
    SUBCODEX_DIR.mkdir(parents=True, exist_ok=True)
    CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
    if not SESSIONS_FILE.exists():
        SESSIONS_FILE.write_text("{}")
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=2))


@contextmanager
def locked_sessions(write: bool = False):
    """Context manager for safely reading/writing sessions.json with file locking."""
    ensure_dir()
    mode = "r+" if SESSIONS_FILE.exists() else "w+"
    with open(SESSIONS_FILE, mode) as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.seek(0)
            content = f.read()
            sessions = json.loads(content) if content.strip() else {}
            yield sessions
            if write:
                f.seek(0)
                f.truncate()
                json.dump(sessions, f, indent=2)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def get_config(key: str, default=None):
    """Get a config value."""
    if CONFIG_FILE.exists():
        try:
            config = json.loads(CONFIG_FILE.read_text())
            return config.get(key, default)
        except json.JSONDecodeError:
            pass
    return default if default is not None else DEFAULT_CONFIG.get(key)


def generate_suffix() -> str:
    """Generate random 4-character suffix."""
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=4))


def get_session_uuid(name: str) -> str | None:
    """Get codex_uuid for a session."""
    with locked_sessions() as sessions:
        session = sessions.get(name, {})
        return session.get("codex_uuid")


def session_exists(name: str) -> bool:
    """Check if session exists."""
    return get_session_uuid(name) is not None


def generate_unique_name(base: str) -> str:
    """Generate unique session name with random suffix."""
    for _ in range(100):
        name = f"{base}-{generate_suffix()}"
        if not session_exists(name):
            return name
    raise RuntimeError("Could not generate unique name after 100 attempts")


def save_session(
    name: str,
    codex_uuid: str,
    *,
    running: bool = False,
    pid: int | None = None,
    tool_calls: int = 0,
    started_at: str | None = None,
):
    """Save or update session info."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cwd = os.getcwd()

    with locked_sessions(write=True) as sessions:
        existing = sessions.get(name, {})
        sessions[name] = {
            "codex_uuid": codex_uuid,
            "last_used": now,
            "created": existing.get("created", now),
            "cwd": existing.get("cwd", cwd),
            "running": running,
            "pid": pid,
            "tool_calls": tool_calls,
            "started_at": started_at,
        }


def set_session_running(name: str, pid: int, tool_calls: int = 0):
    """Mark session as running (creates session if doesn't exist)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cwd = os.getcwd()
    with locked_sessions(write=True) as sessions:
        if name not in sessions:
            sessions[name] = {
                "codex_uuid": None,
                "created": now,
                "cwd": cwd,
            }
        sessions[name]["running"] = True
        sessions[name]["pid"] = pid
        sessions[name]["started_at"] = now
        sessions[name]["tool_calls"] = tool_calls
        sessions[name]["last_used"] = now


def set_session_stopped(name: str, tool_calls: int | None = None):
    """Mark session as stopped."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with locked_sessions(write=True) as sessions:
        if name in sessions:
            sessions[name]["running"] = False
            sessions[name]["pid"] = None
            sessions[name]["last_used"] = now
            if tool_calls is not None:
                sessions[name]["tool_calls"] = tool_calls


def increment_tool_calls(name: str):
    """Increment tool call count for a session."""
    with locked_sessions(write=True) as sessions:
        if name in sessions:
            sessions[name]["tool_calls"] = sessions[name].get("tool_calls", 0) + 1


def get_running_session_in_cwd(cwd: str) -> str | None:
    """Get name of running session in given cwd, if any."""
    with locked_sessions() as sessions:
        for name, session in sessions.items():
            if session.get("running") and session.get("cwd") == cwd:
                # Verify PID is actually running
                pid = session.get("pid")
                if pid and is_process_running(pid):
                    return name
    return None


def is_process_running(pid: int) -> bool:
    """Check if a process is running."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def cleanup_stale_sessions():
    """Mark sessions as stopped if their PID is no longer running."""
    with locked_sessions(write=True) as sessions:
        for name, session in sessions.items():
            if session.get("running"):
                pid = session.get("pid")
                if not pid or not is_process_running(pid):
                    session["running"] = False
                    session["pid"] = None


def format_duration(seconds: int) -> str:
    """Format duration in human-readable form."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    else:
        return f"{seconds // 3600}h {seconds % 3600 // 60}m"


def find_codex_session_file(uuid: str) -> Path | None:
    """Find Codex session file by UUID."""
    if not CODEX_SESSIONS_DIR.exists():
        return None
    for f in CODEX_SESSIONS_DIR.rglob(f"*{uuid}.jsonl"):
        return f
    return None


def count_tool_calls_from_session(uuid: str) -> int:
    """Count tool calls from a Codex session file."""
    session_file = find_codex_session_file(uuid)
    if not session_file or not session_file.exists():
        return 0

    count = 0
    with open(session_file) as f:
        for line in f:
            try:
                event = json.loads(line)
                payload_type = event.get("payload", {}).get("type", "")
                if payload_type in ("function_call", "custom_tool_call"):
                    count += 1
            except json.JSONDecodeError:
                continue
    return count


def write_conversation_header(name: str):
    """Write conversation file header."""
    conv_file = CONVERSATIONS_DIR / f"{name}.txt"
    cwd = os.getcwd()
    conv_file.write_text(f"""# {name}

cwd: {cwd}
Resume: subcodex resume {name} "..."

""")


def append_message(name: str, role: str, content: str):
    """Append message to conversation file."""
    conv_file = CONVERSATIONS_DIR / f"{name}.txt"
    if not conv_file.exists():
        write_conversation_header(name)

    with open(conv_file, "a") as f:
        if role == "user":
            f.write(f"<user>\n{content}\n</user>\n\n")
        else:
            f.write(f"<codex>\n{content}\n</codex>\n\n")


def extract_conversation(session_file: Path, conv_file: Path, name: str):
    """Extract conversation from Codex session file."""
    cwd = "unknown"
    messages = []

    with open(session_file) as f:
        for line in f:
            try:
                event = json.loads(line)
                if event.get("type") == "session_meta":
                    cwd = event.get("payload", {}).get("cwd", "unknown")
                elif event.get("type") == "event_msg":
                    payload = event.get("payload", {})
                    if payload.get("type") == "user_message":
                        messages.append(("user", payload.get("message", "")))
                    elif payload.get("type") == "agent_message":
                        messages.append(("codex", payload.get("message", "")))
            except json.JSONDecodeError:
                continue

    with open(conv_file, "w") as f:
        f.write(f"# {name}\n\ncwd: {cwd}\nResume: subcodex resume {name} \"...\"\n\n")
        for role, msg in messages:
            if role == "user":
                f.write(f"<user>\n{msg}\n</user>\n\n")
            else:
                f.write(f"<codex>\n{msg}\n</codex>\n\n")


def build_codex_cmd(mode: str, model: str | None, reasoning: str | None) -> list[str]:
    """Build codex exec command with options."""
    cmd = ["codex", "exec", "--skip-git-repo-check"]

    # Mode flag
    if mode == "read-only":
        cmd.extend(["--sandbox", "read-only"])
    elif mode in ("dangerous", "dangerously-bypass-approvals-and-sandbox"):
        cmd.append("--dangerously-bypass-approvals-and-sandbox")
    else:
        cmd.append("--full-auto")

    # Web search
    if get_config("web-search", True):
        cmd.extend(["--enable", "web_search_request"])

    # Model
    if model:
        cmd.extend(["-m", model])

    # Reasoning
    if reasoning:
        cmd.extend(["-c", f"model_reasoning_effort={reasoning}"])

    return cmd


def run_codex_with_tracking(
    name: str, cmd: list[str], prompt: str, is_resume: bool = False, resume_uuid: str | None = None
) -> tuple[str, str | None, int]:
    """
    Run codex command with tool call tracking.
    Returns (reply, session_uuid, tool_calls).
    """
    global _current_session
    _current_session = name

    # Create temp file for output
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        # Build full command
        full_cmd = cmd + ["-o", tmp_path]
        if is_resume and resume_uuid:
            full_cmd.extend(["resume", resume_uuid, prompt])
        else:
            full_cmd.append(prompt)

        print(f"--- {name} ---")
        print()
        print("[Waiting for Codex...]")
        print()

        # Start process
        process = subprocess.Popen(
            full_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        # Track as running
        set_session_running(name, process.pid)

        # Read output for session ID
        session_uuid = None
        output_lines = []
        tool_calls = 0

        for line in process.stdout:
            output_lines.append(line)
            # Look for session ID
            if "session id:" in line:
                parts = line.split("session id:")
                if len(parts) > 1:
                    session_uuid = parts[1].strip().split()[0]
            # Count tool calls if JSON output (for review)
            if line.strip().startswith("{"):
                try:
                    event = json.loads(line)
                    payload_type = event.get("payload", {}).get("type", "")
                    if payload_type in ("function_call", "custom_tool_call"):
                        tool_calls += 1
                        increment_tool_calls(name)
                except json.JSONDecodeError:
                    pass

        process.wait()
        output = "".join(output_lines)

        # Check for errors
        if process.returncode != 0 or "ERROR" in output:
            # Try to extract JSON error
            for line in output_lines:
                if "ERROR:" in line and "{" in line:
                    try:
                        json_str = line[line.index("{") :]
                        err = json.loads(json_str)
                        err_msg = err.get("error", {}).get("message")
                        if err_msg:
                            print(f"Error: {err_msg}", file=sys.stderr)
                            sys.exit(1)
                    except (json.JSONDecodeError, ValueError):
                        pass
            print(f"Codex failed (exit {process.returncode}):", file=sys.stderr)
            print(output, file=sys.stderr)
            sys.exit(1)

        # Read reply from output file
        reply = ""
        if os.path.exists(tmp_path):
            reply = Path(tmp_path).read_text()

        # Count tool calls from session file (accurate count)
        final_tool_calls = 0
        if session_uuid:
            final_tool_calls = count_tool_calls_from_session(session_uuid)

        return reply, session_uuid, final_tool_calls

    finally:
        # Clean up temp file
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        # Mark session as stopped
        set_session_stopped(name)
        _current_session = None


def run_codex_review_with_tracking(
    name: str, cmd: list[str]
) -> tuple[str, str | None, int]:
    """
    Run codex review command with tool call tracking.
    Returns (reply, session_uuid, tool_calls).
    """
    global _current_session
    _current_session = name

    try:
        print(f"--- {name} ---")
        print()
        print("[Waiting for Codex review...]")
        print()

        # Start process
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        # Track as running
        set_session_running(name, process.pid)

        # Read JSON output
        session_uuid = None
        events = []
        tool_calls = 0

        for line in process.stdout:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
                events.append(event)

                # Extract session ID
                if event.get("type") == "thread.started":
                    session_uuid = event.get("thread_id")

                # Count tool calls
                payload_type = event.get("payload", {}).get("type", "")
                if payload_type in ("function_call", "custom_tool_call"):
                    tool_calls += 1
                    increment_tool_calls(name)

            except json.JSONDecodeError:
                pass

        process.wait()

        # Check for errors
        for event in events:
            if event.get("type") == "turn.failed":
                err_msg = event.get("error", {}).get("message", "Unknown error")
                print(f"Error: {err_msg}", file=sys.stderr)
                sys.exit(1)

        if process.returncode != 0:
            print(f"Codex review failed (exit {process.returncode})", file=sys.stderr)
            sys.exit(process.returncode)

        # Extract reply from events
        reply = ""
        for event in events:
            if (
                event.get("type") == "item.completed"
                and event.get("item", {}).get("type") == "agent_message"
            ):
                reply = event.get("item", {}).get("text", "")
                break

        if not reply:
            print("Error: No response received from Codex", file=sys.stderr)
            sys.exit(1)

        return reply, session_uuid, tool_calls

    finally:
        # Mark session as stopped
        set_session_stopped(name)
        _current_session = None


def signal_handler(signum, frame):
    """Handle signals by cleaning up current session."""
    global _current_session
    if _current_session:
        set_session_stopped(_current_session)
    sys.exit(1)


# ============================================================================
# Commands
# ============================================================================


def cmd_list(args):
    """List sessions."""
    ensure_dir()
    cleanup_stale_sessions()

    with locked_sessions() as sessions:
        if not sessions:
            print("No sessions.")
            return

    limit = None if args.all else 25

    print("Sessions:")
    print()

    # Sort by last_used descending
    with locked_sessions() as sessions:
        sorted_sessions = sorted(
            sessions.items(), key=lambda x: x[1].get("last_used", ""), reverse=True
        )

        total = len(sorted_sessions)
        hidden = 0
        if limit and total > limit:
            hidden = total - limit
            sorted_sessions = sorted_sessions[:limit]

        now = datetime.now(timezone.utc)
        for name, session in sorted_sessions:
            status = "running" if session.get("running") else "stopped"
            tool_calls = session.get("tool_calls", 0)
            cwd = session.get("cwd", "unknown")
            last_used = session.get("last_used", "unknown")

            # Calculate duration if running
            duration_str = ""
            if session.get("running") and session.get("started_at"):
                try:
                    started = datetime.fromisoformat(session["started_at"].replace("Z", "+00:00"))
                    duration = int((now - started).total_seconds())
                    duration_str = f" ({format_duration(duration)})"
                except ValueError:
                    pass

            print(f"  {name}")
            print(f"    status: {status}{duration_str}")
            print(f"    tool_calls: {tool_calls}")
            print(f"    cwd: {cwd}")
            print(f"    last_used: {last_used}")
            print()

        if hidden > 0:
            print(f"  ... and {hidden} more (use --all to show all)")
            print()


def cmd_new(args):
    """Create new session."""
    ensure_dir()

    # Check exclusive_cwd
    if get_config("exclusive_cwd", False):
        cwd = os.getcwd()
        running_session = get_running_session_in_cwd(cwd)
        if running_session:
            print(f'Error: Session "{running_session}" is already running in {cwd}', file=sys.stderr)
            print("Just stop here and wait - you'll be notified when it completes.", file=sys.stderr)
            sys.exit(1)

    # Generate unique name
    session_name = generate_unique_name(args.name)

    # Get prompt
    prompt = args.prompt
    if not prompt and not sys.stdin.isatty():
        prompt = sys.stdin.read()
    if not prompt:
        print("Error: prompt required", file=sys.stderr)
        sys.exit(1)

    # Save user message before calling codex
    append_message(session_name, "user", prompt)

    # Build command
    mode = args.mode or get_config("mode", "full-auto")
    model = args.model or get_config("model")
    reasoning = args.reasoning or get_config("reasoning")
    cmd = build_codex_cmd(mode, model, reasoning)

    # Run codex
    reply, session_uuid, tool_calls = run_codex_with_tracking(session_name, cmd, prompt)

    if session_uuid:
        append_message(session_name, "codex", reply)
        save_session(session_name, session_uuid, tool_calls=tool_calls)

    print(reply)
    print()
    print("---")
    print(f"Session: {session_name}")
    print(f'Resume: subcodex resume {session_name} "..."')


def cmd_resume(args):
    """Resume existing session."""
    ensure_dir()

    # Check session exists
    existing_uuid = get_session_uuid(args.name)
    if not existing_uuid:
        print(f"Error: session '{args.name}' not found", file=sys.stderr)
        print("Use 'subcodex list' to see available sessions", file=sys.stderr)
        sys.exit(1)

    # Check exclusive_cwd
    if get_config("exclusive_cwd", False):
        cwd = os.getcwd()
        running_session = get_running_session_in_cwd(cwd)
        if running_session:
            print(f'Error: Session "{running_session}" is already running in {cwd}', file=sys.stderr)
            print("Just stop here and wait - you'll be notified when it completes.", file=sys.stderr)
            sys.exit(1)

    # Get prompt
    prompt = args.prompt
    if not prompt and not sys.stdin.isatty():
        prompt = sys.stdin.read()
    if not prompt:
        print("Error: prompt required", file=sys.stderr)
        sys.exit(1)

    # Save user message before calling codex
    append_message(args.name, "user", prompt)

    # Build command
    mode = args.mode or get_config("mode", "full-auto")
    model = args.model or get_config("model")
    reasoning = args.reasoning or get_config("reasoning")
    cmd = build_codex_cmd(mode, model, reasoning)

    # Run codex
    reply, _, tool_calls = run_codex_with_tracking(
        args.name, cmd, prompt, is_resume=True, resume_uuid=existing_uuid
    )

    append_message(args.name, "codex", reply)
    save_session(args.name, existing_uuid, tool_calls=tool_calls)

    print(reply)
    print()
    print("---")
    print(f"Session: {args.name}")
    print(f'Resume: subcodex resume {args.name} "..."')


def cmd_review(args):
    """Run code review."""
    ensure_dir()

    # Check exclusive_cwd
    if get_config("exclusive_cwd", False):
        cwd = os.getcwd()
        running_session = get_running_session_in_cwd(cwd)
        if running_session:
            print(f'Error: Session "{running_session}" is already running in {cwd}', file=sys.stderr)
            print("Just stop here and wait - you'll be notified when it completes.", file=sys.stderr)
            sys.exit(1)

    # Validate target
    target_count = sum(
        [bool(args.uncommitted), bool(args.base), bool(args.commit)]
    )
    if target_count > 1:
        print("Error: Cannot combine --uncommitted, --base, and --commit", file=sys.stderr)
        sys.exit(1)

    # Get custom prompt
    custom_prompt = args.prompt
    if not custom_prompt and not sys.stdin.isatty():
        custom_prompt = sys.stdin.read()

    # Must have target or custom prompt
    if not target_count and not custom_prompt:
        print(
            "Error: review requires a target (--uncommitted, --base, --commit) and/or a custom prompt",
            file=sys.stderr,
        )
        sys.exit(1)

    # Generate unique name
    actual_name = generate_unique_name(args.name)

    # Build prompt description
    if args.uncommitted:
        prompt_desc = "[Review uncommitted changes]"
    elif args.base:
        prompt_desc = f"[Review changes against {args.base}]"
    elif args.commit:
        prompt_desc = f"[Review commit {args.commit}]"
    else:
        prompt_desc = "[Custom review]"
    if custom_prompt:
        prompt_desc = f"{prompt_desc}: {custom_prompt}"
    if args.title:
        prompt_desc = f"{prompt_desc} (title: {args.title})"

    # Save user message before calling codex
    append_message(actual_name, "user", prompt_desc)

    # Build command
    cmd = ["codex", "exec", "--skip-git-repo-check", "--json"]

    if args.model:
        cmd.extend(["-c", f"model={args.model}"])

    reasoning = args.reasoning or get_config("review-reasoning", "xhigh")
    cmd.extend(["-c", f"model_reasoning_effort={reasoning}"])

    cmd.append("review")

    if args.title:
        cmd.extend(["--title", args.title])

    if args.uncommitted:
        cmd.append("--uncommitted")
    elif args.base:
        cmd.extend(["--base", args.base])
    elif args.commit:
        cmd.extend(["--commit", args.commit])

    if custom_prompt:
        cmd.append(custom_prompt)

    # Run codex review
    reply, session_uuid, tool_calls = run_codex_review_with_tracking(actual_name, cmd)

    if session_uuid:
        append_message(actual_name, "codex", reply)
        save_session(actual_name, session_uuid, tool_calls=tool_calls)

    print(reply)
    print()
    print("---")
    print(f"Session: {actual_name}")
    print(f'Resume: subcodex resume {actual_name} "..."')


def cmd_import(args):
    """Import existing Codex session."""
    ensure_dir()

    if session_exists(args.name):
        print(f"Error: session '{args.name}' already exists", file=sys.stderr)
        sys.exit(1)

    session_file = find_codex_session_file(args.uuid)
    conv_file = CONVERSATIONS_DIR / f"{args.name}.txt"

    if session_file and session_file.exists():
        print(f"Found Codex session file: {session_file}")
        print("Extracting conversation...")
        extract_conversation(session_file, conv_file, args.name)
        print("Conversation extracted.")
    else:
        print(f"Warning: Codex session file not found for UUID {args.uuid}")
        print("Creating empty conversation file...")
        write_conversation_header(args.name)

    save_session(args.name, args.uuid)

    print()
    print(f"Imported: {args.name}")
    print(f'Resume: subcodex resume {args.name} "..."')


# ============================================================================
# Main
# ============================================================================


def main():
    # Install signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    parser = argparse.ArgumentParser(
        description="subcodex - Named Codex sessions for Claude Code integration"
    )
    subparsers = parser.add_subparsers(dest="command")

    # new
    new_parser = subparsers.add_parser("new", help="Create new session")
    new_parser.add_argument("name", help="Session name base")
    new_parser.add_argument("prompt", nargs="?", help="Initial prompt")
    new_parser.add_argument("--model", help="Override model")
    new_parser.add_argument("--reasoning", help="Override reasoning level")
    new_parser.add_argument("--read-only", action="store_const", const="read-only", dest="mode")
    new_parser.add_argument("--dangerous", action="store_const", const="dangerous", dest="mode")

    # resume
    resume_parser = subparsers.add_parser("resume", help="Resume existing session")
    resume_parser.add_argument("name", help="Session name")
    resume_parser.add_argument("prompt", nargs="?", help="Follow-up prompt")
    resume_parser.add_argument("--model", help="Override model")
    resume_parser.add_argument("--reasoning", help="Override reasoning level")
    resume_parser.add_argument("--read-only", action="store_const", const="read-only", dest="mode")
    resume_parser.add_argument("--dangerous", action="store_const", const="dangerous", dest="mode")

    # review
    review_parser = subparsers.add_parser("review", help="Code review session")
    review_parser.add_argument("name", help="Session name base")
    review_parser.add_argument("prompt", nargs="?", help="Custom review prompt")
    review_parser.add_argument("--uncommitted", action="store_true", help="Review uncommitted changes")
    review_parser.add_argument("--base", help="Review against base branch")
    review_parser.add_argument("--commit", help="Review specific commit")
    review_parser.add_argument("--title", help="Optional title")
    review_parser.add_argument("--model", help="Override model")
    review_parser.add_argument("--reasoning", help="Override reasoning level")

    # list
    list_parser = subparsers.add_parser("list", help="List sessions")
    list_parser.add_argument("--all", "-a", action="store_true", help="Show all sessions (default: last 25)")

    # import
    import_parser = subparsers.add_parser("import", help="Import existing Codex session")
    import_parser.add_argument("--name", required=True, help="Session name")
    import_parser.add_argument("--uuid", required=True, help="Codex session UUID")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "list":
        cmd_list(args)
    elif args.command == "new":
        cmd_new(args)
    elif args.command == "resume":
        cmd_resume(args)
    elif args.command == "review":
        cmd_review(args)
    elif args.command == "import":
        cmd_import(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
