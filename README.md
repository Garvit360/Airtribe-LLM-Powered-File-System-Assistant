# LLM-Powered File System

## Project brief

A small system that combines **file-system tools** (read, list, write, search) with an **LLM assistant** that can call those tools from natural-language prompts. Use it to list directories, read PDF/TXT/DOCX files, search for keywords, and write files via conversational queries (e.g. “List files in sample_files and summarize notes.txt”).

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  User prompt                                                     │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  llm_file_assistant.py                                           │
│  • OpenAI client (gpt-5.1)                                   │
│  • Tool definitions (read_file, list_files, write_file,           │
│    search_in_file) in OpenAI function-calling format             │
│  • Loop: chat completion → if tool_calls → run_tool() →          │
│    append results → repeat until model returns text              │
│  • Paths resolved relative to project root (PROJECT_ROOT)        │
└────────────────────────────┬────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  fs_tools.py                                                     │
│  • read_file(filepath)   → dict (content, filename, size, error)  │
│  • list_files(dir, ext?) → list of {name, size, modified}       │
│  • write_file(filepath, content) → dict (success, path, error)   │
│  • search_in_file(filepath, keyword) → dict (matches, keyword)   │
│  Supported: PDF (pypdf), DOCX (python-docx), TXT                 │
└─────────────────────────────────────────────────────────────────┘
```

- **fs_tools**: Pure file I/O. Paths may use `~`; it is expanded. No LLM dependency.
- **llm_file_assistant**: Loads `.env` for `OPENAI_API_KEY`, defines tools, runs the chat loop, and executes tools via `fs_tools`. File paths in prompts are resolved against the directory containing `llm_file_assistant.py`.

---

## How to run

1. **Create a virtualenv and install dependencies**

   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Set your OpenAI API key**

   Create a `.env` file in the project root:

   ```
   OPENAI_API_KEY=sk-...
   ```

3. **Run the assistant**

   From the project root:

   ```bash
   python llm_file_assistant.py
   ```

   The default prompt lists `sample_files` and summarizes `sample_files/notes.txt`. Edit the `prompt` in `if __name__ == "__main__"` to try other queries (e.g. read a PDF, search for a keyword, write a file).

4. **Use the file tools alone (optional)**

   ```bash
   python fs_tools.py
   ```

   This runs the demo in `fs_tools.py` (e.g. `list_files` on `sample_files`). Useful to verify file I/O without the LLM.
