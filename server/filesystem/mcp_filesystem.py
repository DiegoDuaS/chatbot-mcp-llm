#!/usr/bin/env python3
import os
import json
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# ==============================
# CONFIG
# ==============================
BASE_DIR = os.path.join(os.path.dirname(__file__), "storage")
os.makedirs(BASE_DIR, exist_ok=True)

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "filesystem_mcp_log.json")
os.makedirs(LOG_DIR, exist_ok=True)

fs_conversation = []

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# ==============================
# LOGGING
# ==============================
def save_log():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(fs_conversation, f, indent=2, ensure_ascii=False)

def log_message(role, content):
    fs_conversation.append({"role": role, "content": content, "timestamp": datetime.now().isoformat()})
    save_log()

# ==============================
# MCP TOOLS
# ==============================
@app.get("/tools")
async def list_tools():
    return {
        "tools": [
            {
                "name": "write_file",
                "endpoint": "/filesystem/write",
                "description": "Crea o actualiza un archivo en el almacenamiento",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string"},
                        "content": {"type": "string"}
                    },
                    "required": ["filename"]
                }
            },
            {
                "name": "read_file",
                "endpoint": "/filesystem/read",
                "description": "Lee un archivo del almacenamiento",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string"}
                    },
                    "required": ["filename"]
                }
            },
            {
                "name": "list_files",
                "endpoint": "/filesystem/list",
                "description": "Lista todos los archivos del almacenamiento",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        ]
    }

# ==============================
# MCP ENDPOINTS
# ==============================
class FileModel(BaseModel):
    filename: str
    content: str = ""

class FileReadModel(BaseModel):
    filename: str

@app.post("/filesystem/write")
async def write_file(data: FileModel):
    filepath = os.path.join(BASE_DIR, data.filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(data.content)
    response = f"Archivo '{data.filename}' creado/actualizado."
    log_message("assistant", response)
    return {"success": True, "response": response}

@app.post("/filesystem/read")
async def read_file(data: FileReadModel):
    filepath = os.path.join(BASE_DIR, data.filename)
    if not os.path.exists(filepath):
        response = f"Archivo '{data.filename}' no encontrado."
        log_message("assistant", response)
        return {"success": False, "response": response}
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    response = f"Archivo '{data.filename}' leído correctamente."
    log_message("assistant", response)
    return {"success": True, "filename": data.filename, "content": content, "response": response}

@app.post("/filesystem/list")
async def list_files():
    files = os.listdir(BASE_DIR)
    response = f"{len(files)} archivos encontrados."
    log_message("assistant", response)
    return {"success": True, "files": files, "response": response}

# ==============================
# MAIN
# ==============================
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8100)
