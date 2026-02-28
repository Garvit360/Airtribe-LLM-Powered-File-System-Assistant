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
        p = PROJECT_ROOT / path_str
    return str(Path(os.path.expanduser(str(p))).resolve())

tools = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file and return the content. Supports PDF, DOCX, and TXT.",
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
            "description": "List all files in a directory with size and modified time.",
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
            "description": "Write content to a file. Creates parent directories if needed.",
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
            "description": "Search for a keyword in a text file; returns matching lines with context.",
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
    raise ValueError(f"Unknown tool: {name}")

@traceable
def get_response(prompt: str) -> str:
    messages = [{"role": "user", "content": prompt}]
    while True:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
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

if __name__ == "__main__":
    prompt = "List files in sample_files, then read sample_files/notes.txt and summarize it in one sentence."
    print(get_response(prompt))
