import os
import asyncio
from datetime import datetime
from typing import Dict, List, Any
from mcp.server import Server, NotificationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# ======================
# Configuration
# ======================
BASE_DIR = os.path.join(os.path.dirname(__file__), "storage")
os.makedirs(BASE_DIR, exist_ok=True)

# ======================
# MCP Server
# ======================
app = Server("filesystem")

# ======================
# Helper Functions (adapted from original handlers)
# ======================
def sanitize_filename(filename: str) -> str:
    """Sanitiza el nombre del archivo para evitar problemas de ruta."""
    return os.path.basename(filename)

# ======================
# Tool Handlers
# ======================
@app.list_tools()
async def handle_list_tools() -> list[Tool]:
    """Lista todas las herramientas disponibles en el servidor."""
    return [
        Tool(
            name="write_file",
            description="Create or update a file in storage",
            inputSchema={
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Name of file to create/update"},
                    "content": {"type": "string", "description": "File content", "default": ""},
                },
                "required": ["filename"],
            },
        ),
        Tool(
            name="read_file",
            description="Read file content from storage",
            inputSchema={
                "type": "object",
                "properties": {"filename": {"type": "string", "description": "Name of file to read"}},
                "required": ["filename"],
            },
        ),
        Tool(
            name="list_files",
            description="List all files in storage",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="delete_file",
            description="Delete a file from storage",
            inputSchema={
                "type": "object",
                "properties": {"filename": {"type": "string", "description": "Name of file to delete"}},
                "required": ["filename"],
            },
        ),
        Tool(
            name="file_exists",
            description="Check if a file exists in storage",
            inputSchema={
                "type": "object",
                "properties": {"filename": {"type": "string", "description": "Name of file to check"}},
                "required": ["filename"],
            },
        ),
    ]

@app.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Maneja las llamadas a las herramientas y devuelve la respuesta."""

    if name == "write_file":
        filename = arguments.get("filename")
        content = arguments.get("content", "")
        if not filename:
            return [TextContent(type="text", text="Error: 'filename' is required.")]
        try:
            safe_filename = sanitize_filename(filename)
            filepath = os.path.join(BASE_DIR, safe_filename)
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            message = f"File '{safe_filename}' created/updated successfully ({len(content)} characters)."
            return [TextContent(type="text", text=message)]
        except Exception as e:
            return [TextContent(type="text", text=f"Error writing file '{filename}': {str(e)}")]

    elif name == "read_file":
        filename = arguments.get("filename")
        if not filename:
            return [TextContent(type="text", text="Error: 'filename' is required.")]
        try:
            safe_filename = sanitize_filename(filename)
            filepath = os.path.join(BASE_DIR, safe_filename)
            if not os.path.exists(filepath):
                return [TextContent(type="text", text=f"File '{safe_filename}' not found.")]
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            message = f"File '{safe_filename}' read successfully.\nContent:\n\n{content}"
            return [TextContent(type="text", text=message)]
        except UnicodeDecodeError:
            return [TextContent(type="text", text=f"Error: Cannot read file '{filename}' - appears to be binary.")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error reading file '{filename}': {str(e)}")]

    elif name == "list_files":
        try:
            if not os.path.exists(BASE_DIR):
                return [TextContent(type="text", text="Storage directory is empty.")]
            files = [
                {"name": f, "size": os.path.getsize(os.path.join(BASE_DIR, f))}
                for f in os.listdir(BASE_DIR)
                if os.path.isfile(os.path.join(BASE_DIR, f))
            ]
            files.sort(key=lambda x: x["name"])
            file_list = "\n".join([f"- {f['name']} ({f['size']} bytes)" for f in files])
            message = f"Found {len(files)} files:\n{file_list}" if files else "Storage directory is empty."
            return [TextContent(type="text", text=message)]
        except Exception as e:
            return [TextContent(type="text", text=f"Error listing files: {str(e)}")]

    elif name == "delete_file":
        filename = arguments.get("filename")
        if not filename:
            return [TextContent(type="text", text="Error: 'filename' is required.")]
        try:
            safe_filename = sanitize_filename(filename)
            filepath = os.path.join(BASE_DIR, safe_filename)
            if not os.path.exists(filepath):
                return [TextContent(type="text", text=f"File '{safe_filename}' not found.")]
            os.remove(filepath)
            return [TextContent(type="text", text=f"File '{safe_filename}' deleted successfully.")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error deleting file '{filename}': {str(e)}")]

    elif name == "file_exists":
        filename = arguments.get("filename")
        if not filename:
            return [TextContent(type="text", text="Error: 'filename' is required.")]
        try:
            safe_filename = sanitize_filename(filename)
            filepath = os.path.join(BASE_DIR, safe_filename)
            exists = os.path.exists(filepath) and os.path.isfile(filepath)
            message = f"File '{safe_filename}' exists: {exists}"
            if exists:
                size = os.path.getsize(filepath)
                modified = datetime.fromtimestamp(os.path.getmtime(filepath)).isoformat()
                message += f"\nSize: {size} bytes\nLast Modified: {modified}"
            return [TextContent(type="text", text=message)]
        except Exception as e:
            return [TextContent(type="text", text=f"Error checking file '{filename}': {str(e)}")]

    else:
        return [TextContent(type="text", text=f"Herramienta desconocida: {name}")]

# ======================
# Main execution loop
# ======================
async def main():
    """Función principal del servidor."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream, 
            write_stream, 
            NotificationOptions(stdio=True)
        )

if __name__ == "__main__":
    asyncio.run(main())