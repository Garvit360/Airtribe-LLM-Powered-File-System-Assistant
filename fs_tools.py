"""
File system utilities for reading, writing, listing, and searching files.

This module provides four core functions that return consistent dict shapes:
- read_file: Extract text from PDF/TXT/DOCX files
- list_files: List directory contents with metadata and optional filtering  
- write_file: Write string content to files with automatic directory creation
- search_in_file: Find keyword matches in files with surrounding context
"""

from pypdf import PdfReader
from docx import Document
from pathlib import Path
import os
from datetime import datetime


def read_file(filepath: str) -> dict:
    """
    Read and extract text content from PDF, DOCX, or TXT files.
    
    Args:
        filepath: Path to the file to read
        
    Returns:
        dict: {"content": str | None, "filename": str, "size": int, "error": str | None}
              On success: content contains extracted text, error is None
              On failure: content is None, error contains error message
    """
    try:
        # Expand ~ to home directory and normalize path
        path = Path(os.path.expanduser(filepath))
        filepath = str(path)
        filename = path.name
        size = path.stat().st_size if path.exists() else 0
        
        # Dispatch by file extension
        extension = path.suffix.lower()
        content = None
        
        if extension == '.pdf':
            # Extract text from all PDF pages
            with open(filepath, 'rb') as file:
                reader = PdfReader(file)
                content = ""
                for page in reader.pages:
                    content += page.extract_text() + "\n"
                content = content.strip()
                
        elif extension == '.docx':
            # Extract text from DOCX paragraphs
            doc = Document(filepath)
            paragraphs = [paragraph.text for paragraph in doc.paragraphs]
            content = "\n".join(paragraphs)
            
        else:
            # Handle TXT files and other text formats
            with open(filepath, 'r', encoding='utf-8', errors='replace') as file:
                content = file.read()
        
        return {
            "content": content,
            "filename": filename,
            "size": size,
            "error": None
        }
        
    except Exception as e:
        return {
            "content": None,
            "filename": Path(filepath).name if filepath else "unknown",
            "size": 0,
            "error": str(e)
        }


def list_files(directory: str, extension: str = None) -> list:
    """
    List all files in a directory with metadata, optionally filtered by extension.
    
    Args:
        directory: Path to directory to scan
        extension: Optional file extension filter (e.g., '.pdf', '.txt')
        
    Returns:
        list: List of dicts with {"name": str, "size": int, "modified": str} per file
    """
    try:
        # Expand ~ and normalize directory path
        dir_path = Path(os.path.expanduser(directory))
        if not dir_path.exists() or not dir_path.is_dir():
            return []
        
        # Normalize extension filter if provided
        if extension and not extension.startswith('.'):
            extension = '.' + extension
        
        files_list = []
        
        # Scan directory for files only (skip directories)
        for item in dir_path.iterdir():
            if item.is_file():
                # Apply extension filter if specified
                if extension and item.suffix.lower() != extension.lower():
                    continue
                
                # Get file metadata
                stat_info = item.stat()
                modified_time = datetime.fromtimestamp(stat_info.st_mtime).isoformat()
                
                files_list.append({
                    "name": item.name,
                    "size": stat_info.st_size,
                    "modified": modified_time
                })
        
        # Return list of file metadata dicts
        return files_list
        
    except Exception:
        return []


def write_file(filepath: str, content: str) -> dict:
    """
    Write string content to a file, creating parent directories if needed.
    
    Args:
        filepath: Path where to write the file
        content: String content to write
        
    Returns:
        dict: {"success": bool, "path": str, "error": str | None}
    """
    try:
        # Expand ~ and create Path object; ensure parent directories exist
        path = Path(os.path.expanduser(filepath))
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write content as UTF-8 text
        path.write_text(content, encoding='utf-8')
        
        return {
            "success": True,
            "path": str(path),
            "error": None
        }
        
    except Exception as e:
        return {
            "success": False,
            "path": filepath,
            "error": str(e)
        }


def search_in_file(filepath: str, keyword: str) -> dict:
    """
    Find all lines containing a keyword (case-insensitive) with surrounding context.
    
    Args:
        filepath: Path to file to search in
        keyword: Keyword to search for (case-insensitive)
        
    Returns:
        dict: {"matches": [{"line": str, "line_number": int, "context_before": str, "context_after": str}], "keyword": str}
    """
    try:
        # Expand ~ and read file content as text
        filepath = os.path.expanduser(filepath)
        with open(filepath, 'r', encoding='utf-8', errors='replace') as file:
            lines = file.readlines()
        
        # Prepare case-insensitive search
        keyword_lower = keyword.lower()
        matches = []
        context_lines = 2  # Number of lines before/after to include as context
        
        # Search through each line
        for i, line in enumerate(lines):
            if keyword_lower in line.lower():
                # Calculate context boundaries
                start_context = max(0, i - context_lines)
                end_context = min(len(lines), i + context_lines + 1)
                
                # Extract context lines
                context_before = "".join(lines[start_context:i]).strip()
                context_after = "".join(lines[i+1:end_context]).strip()
                
                matches.append({
                    "line": line.rstrip('\n\r'),  # Remove trailing newlines but keep original text
                    "line_number": i + 1,  # 1-based line numbering
                    "context_before": context_before,
                    "context_after": context_after
                })
        
        return {
            "matches": matches,
            "keyword": keyword,
            "error": None
        }
        
    except Exception as e:
        return {
            "matches": [],
            "keyword": keyword,
            "error": str(e)
        }