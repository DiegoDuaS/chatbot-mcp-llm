#!/usr/bin/env python3
import os
import json
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from git import Repo, GitCommandError
from dotenv import load_dotenv
from jsonrpcserver import method, async_dispatch as dispatch, Success, Error

# ======================
# Cargar variables de entorno
# ======================
load_dotenv()
GIT_BASE_DIR = os.getenv("GIT_BASE_DIR", "./repos")
os.makedirs(GIT_BASE_DIR, exist_ok=True)

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "git_mcp_log.json")
os.makedirs(LOG_DIR, exist_ok=True)

# Conversation log
git_conversation = []

# ======================
# FastAPI
# ======================
app = FastAPI(title="Git MCP JSON-RPC Server")

# ======================
# Logging
# ======================
def save_log():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(git_conversation, f, indent=2, ensure_ascii=False)

def log_message(role, content):
    git_conversation.append({"role": role, "content": content, "timestamp": datetime.now().isoformat()})
    save_log()

# ======================
# Git Helpers
# ======================
def get_repo(repo_name: str):
    path = os.path.join(GIT_BASE_DIR, repo_name)
    if os.path.exists(path) and os.path.exists(os.path.join(path, '.git')):
        return Repo(path)
    
    os.makedirs(path, exist_ok=True)
    repo = Repo.init(path)
    
    # Configurar Git si no está configurado
    try:
        repo.config_writer().set_value("user", "name", "MCP Bot").release()
        repo.config_writer().set_value("user", "email", "mcp@example.com").release()
    except:
        pass
    
    return repo

# ======================
# JSON-RPC Methods
# ======================
@method
async def create_repo(repo_name: str):
    try:
        repo = get_repo(repo_name)
        response = f"✅ Repository '{repo_name}' created successfully at {repo.working_tree_dir}"
        log_message("assistant", response)
        return Success({"success": True, "message": response})
    except Exception as e:
        error_msg = f"❌ Error creating repository '{repo_name}': {str(e)}"
        log_message("assistant", error_msg)
        return Error(code=-1, message=error_msg)

@method
async def add_file(repo_name: str, file_name: str, content: str = ""):
    try:
        repo = get_repo(repo_name)
        file_path = os.path.join(repo.working_tree_dir, file_name)
        
        # Crear directorios si es necesario
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        repo.index.add([file_name])  # Usar nombre relativo
        response = f"✅ File '{file_name}' added to repository '{repo_name}'"
        log_message("assistant", response)
        return Success({"success": True, "message": response})
    except Exception as e:
        error_msg = f"❌ Error adding file '{file_name}' to '{repo_name}': {str(e)}"
        log_message("assistant", error_msg)
        return Error(code=-1, message=error_msg)

@method
async def commit(repo_name: str, message: str = "Commit from MCP"):
    try:
        repo = get_repo(repo_name)
        
        # Verificar que hay cambios para commitear
        if not repo.index.diff("HEAD") and not repo.untracked_files:
            response = f"⚠️ No changes to commit in '{repo_name}'"
            log_message("assistant", response)
            return Success({"success": True, "message": response})
        
        commit_obj = repo.index.commit(message)
        response = f"✅ Commit made in '{repo_name}' with message: '{message}' (SHA: {commit_obj.hexsha[:8]})"
        log_message("assistant", response)
        return Success({"success": True, "message": response})
    except GitCommandError as e:
        error_msg = f"❌ Git error in '{repo_name}': {str(e)}"
        log_message("assistant", error_msg)
        return Error(code=-1, message=error_msg)
    except Exception as e:
        error_msg = f"❌ Error committing to '{repo_name}': {str(e)}"
        log_message("assistant", error_msg)
        return Error(code=-1, message=error_msg)

@method
async def list_files(repo_name: str):
    try:
        repo = get_repo(repo_name)
        files = []
        
        # Listar archivos trackeados por Git
        for item in repo.tree().traverse():
            if item.type == 'blob':  # Solo archivos, no directorios
                files.append(item.path)
        
        # También incluir archivos no trackeados
        untracked = repo.untracked_files
        
        response = f"📁 Repository '{repo_name}':\n"
        response += f"Tracked files: {files}\n"
        response += f"Untracked files: {untracked}"
        
        log_message("assistant", response)
        return Success({"success": True, "message": response, "tracked_files": files, "untracked_files": untracked})
    except Exception as e:
        error_msg = f"❌ Error listing files in '{repo_name}': {str(e)}"
        log_message("assistant", error_msg)
        return Error(code=-1, message=error_msg)

@method
async def git_status(repo_name: str):
    try:
        repo = get_repo(repo_name)
        status = {
            "modified": [item.a_path for item in repo.index.diff(None)],
            "staged": [item.a_path for item in repo.index.diff("HEAD")],
            "untracked": repo.untracked_files
        }
        
        response = f"📊 Git status for '{repo_name}':\n"
        response += f"Modified: {status['modified']}\n"
        response += f"Staged: {status['staged']}\n"
        response += f"Untracked: {status['untracked']}"
        
        log_message("assistant", response)
        return Success({"success": True, "message": response, "status": status})
    except Exception as e:
        error_msg = f"❌ Error getting status for '{repo_name}': {str(e)}"
        log_message("assistant", error_msg)
        return Error(code=-1, message=error_msg)

@method
async def list_tools():
    tools = [
        {
            "type": "function",
            "function": {
                "name": "create_repo",
                "description": "Crea un nuevo repositorio Git local",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo_name": {
                            "type": "string",
                            "description": "Nombre del repositorio a crear"
                        }
                    },
                    "required": ["repo_name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "add_file",
                "description": "Agrega un archivo a un repositorio Git",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo_name": {
                            "type": "string",
                            "description": "Nombre del repositorio"
                        },
                        "file_name": {
                            "type": "string",
                            "description": "Nombre del archivo a crear"
                        },
                        "content": {
                            "type": "string",
                            "description": "Contenido del archivo",
                            "default": ""
                        }
                    },
                    "required": ["repo_name", "file_name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "commit",
                "description": "Realiza un commit en el repositorio",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo_name": {
                            "type": "string",
                            "description": "Nombre del repositorio"
                        },
                        "message": {
                            "type": "string",
                            "description": "Mensaje del commit",
                            "default": "Commit from MCP"
                        }
                    },
                    "required": ["repo_name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "Lista archivos en un repositorio",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo_name": {
                            "type": "string",
                            "description": "Nombre del repositorio"
                        }
                    },
                    "required": ["repo_name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "git_status",
                "description": "Muestra el estado del repositorio Git",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo_name": {
                            "type": "string",
                            "description": "Nombre del repositorio"
                        }
                    },
                    "required": ["repo_name"]
                }
            }
        }
    ]
    return Success({"status": "ok", "tools": tools})

# ======================
# JSON-RPC Endpoint
# ======================
@app.post("/")
async def handle(request: Request):
    data = await request.body()
    response = await dispatch(data.decode("utf-8"))
    return JSONResponse(content=json.loads(str(response)))

# ======================
# Health Check
# ======================
@app.get("/health")
async def health():
    return {"status": "ok", "message": "Git MCP Server is running"}

# ======================
# Main
# ======================
if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Git MCP Server on http://localhost:8002")
    uvicorn.run(app, host="0.0.0.0", port=8002)