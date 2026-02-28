from openai import OpenAI
from dotenv import load_dotenv
import os
import json
from pathlib import Path
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
def get_response(prompt: str, history: list | None = None) -> str:
    messages = (history or []) + [{"role": "user", "content": prompt}]
    while True:
        response = client.chat.completions.create(
            model="gpt-5.1",
            messages=messages,
            tools=tools,
        )
        msg = response.choices[0].message
        if msg.content is not None and msg.content.strip():
            return msg.content
        if not msg.tool_calls:
            raise RuntimeError("Model returned no content and no tool_calls")
        messages.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [
                {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ],
        })
        for tc in msg.tool_calls:
            name = tc.function.name
            args = json.loads(tc.function.arguments)
            result = run_tool(name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

def run_chat_ui() -> None:
    """Interactive terminal chat (ChatGPT-style)."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.markdown import Markdown

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
        user_input = console.input("[bold cyan]You[/]: ").strip()
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            console.print("[dim]Bye.[/]")
            break

        with console.status("[bold green]Thinking…[/]"):
            response = get_response(user_input, history=history)

        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": response})

        console.print(Panel(Markdown(response), title="Assistant", border_style="green"))
        console.print()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--chat":
        run_chat_ui()
    else:
        prompt = "List files in sample_files, then read sample_files/notes.txt and summarize it in one sentence."
        print(get_response(prompt))
