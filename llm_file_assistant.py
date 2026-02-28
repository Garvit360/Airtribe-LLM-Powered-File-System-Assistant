from openai import OpenAI
from dotenv import load_dotenv
import os
import json
from pathlib import Path
from typing import Callable
from langsmith import traceable

import fs_tools

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Path to project root; sample paths are resolved relative to this
PROJECT_ROOT = Path(__file__).resolve().parent

def resolve_path(path_str: str) -> str:
    """Resolve path relative to project root; expand ~."""
    p = Path(path_str)
    if not p.is_absolute() and "~" not in path_str:
        # Normalize relative paths that start with the project name
        # Strip leading PROJECT_ROOT.name segment to avoid double-nesting
        if path_str == PROJECT_ROOT.name or path_str.startswith(PROJECT_ROOT.name + "/"):
            suffix = path_str[len(PROJECT_ROOT.name):].lstrip("/")
            path_str = suffix if suffix else "."
        p = PROJECT_ROOT / path_str
    return str(Path(os.path.expanduser(str(p))).resolve())

tools = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file and return the content. Supports PDF, DOCX, and TXT. Use get_path_by_name first to find where a file lives.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Path to the file to read (e.g. sample_files/notes.txt)"},
                },
                "required": ["filepath"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List all files in a directory with size and modified time. Use get_path_by_name first to find where a directory lives.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "Path to the directory to list"},
                },
                "required": ["directory"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file. Creates parent directories if needed. Use get_path_by_name first to find where a file lives.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Path where to write the file"},
                    "content": {"type": "string", "description": "Content to write"},
                },
                "required": ["filepath", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_in_file",
            "description": "Search for a keyword in a text file; returns matching lines with context. Use get_path_by_name first to find where a file lives.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Path to the file to search"},
                    "keyword": {"type": "string", "description": "Keyword to search for (case-insensitive)"},
                },
                "required": ["filepath", "keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_path_by_name",
            "description": "Return the full path of a file or directory under the project by its exact, case-sensitive name. Use this to find where a file or folder lives before calling list_files or read_file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Exact case-sensitive name to search for"},
                },
                "required": ["name"],
            },
        },
    },
]

def run_tool(name: str, arguments: dict) -> str:
    """Execute a single tool by name and return result as JSON string."""
    if name == "read_file":
        path = resolve_path(arguments["filepath"])
        return json.dumps(fs_tools.read_file(path))
    if name == "list_files":
        path = resolve_path(arguments["directory"])
        return json.dumps(fs_tools.list_files(path))
    if name == "write_file":
        path = resolve_path(arguments["filepath"])
        return json.dumps(fs_tools.write_file(path, arguments["content"]))
    if name == "search_in_file":
        path = resolve_path(arguments["filepath"])
        return json.dumps(fs_tools.search_in_file(path, arguments["keyword"]))
    if name == "get_path_by_name":
        root_path = str(PROJECT_ROOT)
        return json.dumps(fs_tools.get_path_by_name(root_path, arguments["name"]))
    raise ValueError(f"Unknown tool: {name}")

@traceable
def get_response(
    prompt: str,
    history: list | None = None,
    on_tool_calls: Callable[[list], None] | None = None,
    stream_callback: Callable[[str], None] | None = None,
) -> str:
    messages = (history or []) + [{"role": "user", "content": prompt}]
    while True:
        stream = client.chat.completions.create(
            model="gpt-5.1",
            messages=messages,
            tools=tools,
            stream=True,
        )
        content_parts = []
        tool_calls_accum = {}
        finish_reason = None

        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            finish_reason = chunk.choices[0].finish_reason
            if delta.content:
                content_parts.append(delta.content)
                if stream_callback:
                    stream_callback(delta.content)
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_accum:
                        tool_calls_accum[idx] = {"id": "", "name": "", "arguments": ""}
                    if tc.id:
                        tool_calls_accum[idx]["id"] = tc.id
                    if tc.function and tc.function.name:
                        tool_calls_accum[idx]["name"] = tc.function.name
                    if tc.function and tc.function.arguments:
                        tool_calls_accum[idx]["arguments"] += tc.function.arguments

        full_content = "".join(content_parts).strip() if content_parts else ""
        if full_content and finish_reason == "stop":
            return full_content
        if not tool_calls_accum or finish_reason != "tool_calls":
            if full_content:
                return full_content
            raise RuntimeError("Model returned no content and no tool_calls")

        tool_calls_list = [
            {
                "id": tool_calls_accum[i]["id"],
                "type": "function",
                "function": {"name": tool_calls_accum[i]["name"], "arguments": tool_calls_accum[i]["arguments"]},
            }
            for i in sorted(tool_calls_accum.keys())
        ]
        tool_names = [t["function"]["name"] for t in tool_calls_list]
        if on_tool_calls:
            on_tool_calls(tool_names)
        messages.append({
            "role": "assistant",
            "content": full_content or None,
            "tool_calls": [
                {"id": t["id"], "type": "function", "function": {"name": t["function"]["name"], "arguments": t["function"]["arguments"]}}
                for t in tool_calls_list
            ],
        })
        for t in tool_calls_list:
            name = t["function"]["name"]
            args = json.loads(t["function"]["arguments"])
            result = run_tool(name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": t["id"],
                "content": result,
            })

def run_chat_ui() -> None:
    """Interactive terminal chat (ChatGPT-style)."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.markdown import Markdown
    from rich.live import Live

    console = Console()
    history: list[dict] = []

    console.print(Panel(
        "[bold]LLM File Assistant[/]\n\n"
        "Ask to list, read, search, or write files (e.g. sample_files/).\n"
        "Type [bold]exit[/] or [bold]quit[/] to end.",
        title="Chat",
        border_style="blue",
    ))
    console.print()

    while True:
        console.print("[bold cyan]You[/]: ", end="")
        user_input = input().strip()
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            console.print("[dim]Bye.[/]")
            break

        streamed_content: list[str] = []

        def on_tool_calls(tool_names: list) -> None:
            live.update(Panel("[dim]Calling: " + ", ".join(tool_names) + "[/]", title="Assistant", border_style="green"))

        def stream_callback(chunk: str) -> None:
            streamed_content.append(chunk)
            live.update(Panel(Markdown("".join(streamed_content)), title="Assistant", border_style="green"))

        with Live(Panel("[bold green]Thinking…[/]", title="Assistant", border_style="green"), console=console, refresh_per_second=8) as live:
            response = get_response(
                user_input,
                history=history,
                on_tool_calls=on_tool_calls,
                stream_callback=stream_callback,
            )

        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": response})

        console.print()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--chat":
        run_chat_ui()
    else:
        prompt = "List files in sample_files, then read sample_files/notes.txt and summarize it in one sentence."
        print(get_response(prompt))
