#!/usr/bin/env python3
import os
import json
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from git import Repo, GitCommandError
from pydantic import BaseModel
from dotenv import load_dotenv

# ==============================
# LOAD ENV VARIABLES & SETUP
# ==============================
load_dotenv()
GIT_BASE_DIR = os.getenv("GIT_BASE_DIR", "./repos")
os.makedirs(GIT_BASE_DIR, exist_ok=True)

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "git_mcp_log.json")
os.makedirs(LOG_DIR, exist_ok=True)

# Conversation log
git_conversation = []

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
        json.dump(git_conversation, f, indent=2, ensure_ascii=False)

def log_message(role, content):
    git_conversation.append({"role": role, "content": content, "timestamp": datetime.now().isoformat()})
    save_log()

# ==============================
# GIT HELPERS
# ==============================
def get_repo(repo_name):
    path = os.path.join(GIT_BASE_DIR, repo_name)
    if os.path.exists(path):
        return Repo(path)
    else:
        os.makedirs(path, exist_ok=True)
        return Repo.init(path)

# ==============================
# MCP TOOLS ENDPOINT
# ==============================
@app.get("/tools")
async def list_tools():
    return {
        "tools": [
            {
                "name": "create_repo",
                "endpoint": "/git/create_repo",
                "description": "Crea un repositorio local",
                "inputSchema": {"type": "object", "properties": {"repo_name": {"type": "string"}}, "required": ["repo_name"]}
            },
            {
                "name": "add_file",
                "endpoint": "/git/add_file",
                "description": "Agrega un archivo a un repositorio",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "repo_name": {"type": "string"},
                        "file_name": {"type": "string"},
                        "content": {"type": "string"}
                    },
                    "required": ["repo_name", "file_name"]
                }
            },
            {
                "name": "commit",
                "endpoint": "/git/commit",
                "description": "Realiza un commit en un repositorio",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "repo_name": {"type": "string"},
                        "message": {"type": "string"}
                    },
                    "required": ["repo_name"]
                }
            },
            {
                "name": "list_files",
                "endpoint": "/git/list_files",
                "description": "Lista archivos en un repositorio",
                "inputSchema": {"type": "object", "properties": {"repo_name": {"type": "string"}}, "required": ["repo_name"]}
            }
        ]
    }

# ==============================
# MCP ENDPOINTS
# ==============================
class RepoModel(BaseModel):
    repo_name: str

class FileModel(BaseModel):
    repo_name: str
    file_name: str
    content: str = ""

class CommitModel(BaseModel):
    repo_name: str
    message: str = "Commit from MCP"

@app.post("/git/create_repo")
async def create_repo(data: RepoModel):
    repo_name = data.repo_name
    get_repo(repo_name)
    response = f"Repository '{repo_name}' created."
    log_message("assistant", response)
    return {"success": True, "response": response}

@app.post("/git/add_file")
async def add_file(data: FileModel):
    repo = get_repo(data.repo_name)
    file_path = os.path.join(repo.working_tree_dir, data.file_name)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(data.content)
    repo.index.add([file_path])
    response = f"File '{data.file_name}' added to '{data.repo_name}'."
    log_message("assistant", response)
    return {"success": True, "response": response}

@app.post("/git/commit")
async def commit(data: CommitModel):
    repo = get_repo(data.repo_name)
    try:
        repo.index.commit(data.message)
        response = f"Commit made in '{data.repo_name}' with message '{data.message}'."
    except GitCommandError as e:
        response = f"Git error: {str(e)}"
    log_message("assistant", response)
    return {"success": True, "response": response}

@app.post("/git/list_files")
async def list_files(data: RepoModel):
    repo = get_repo(data.repo_name)
    files = os.listdir(repo.working_tree_dir)
    response = f"Files in '{data.repo_name}': {files}"
    log_message("assistant", response)
    return {"success": True, "response": response}

# ==============================
# MAIN
# ==============================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
