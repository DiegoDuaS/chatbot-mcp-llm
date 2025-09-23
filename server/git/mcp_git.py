import os
import json
import sys
from datetime import datetime
from git import Repo, GitCommandError
from dotenv import load_dotenv

# ======================
# Configuration
# ======================
load_dotenv()
GIT_BASE_DIR = os.getenv("GIT_BASE_DIR", "./repos")
os.makedirs(GIT_BASE_DIR, exist_ok=True)

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "git_mcp_stdio_log.json")
os.makedirs(LOG_DIR, exist_ok=True)

git_conversation = []

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
    
    try:
        repo.config_writer().set_value("user", "name", "MCP Bot").release()
        repo.config_writer().set_value("user", "email", "mcp@example.com").release()
    except:
        pass
    
    return repo

# ======================
# MCP Command Handlers
# ======================
def handle_create_repo(params):
    try:
        repo_name = params.get("repo_name")
        if not repo_name:
            return {"error": {"code": -1, "message": "repo_name is required"}}
        
        repo = get_repo(repo_name)
        response = f"Repository '{repo_name}' created successfully at {repo.working_tree_dir}"
        log_message("assistant", response)
        
        return {"result": {"success": True, "message": response}}
    except Exception as e:
        error_msg = f"Error creating repository '{repo_name}': {str(e)}"
        log_message("assistant", error_msg)
        return {"error": {"code": -1, "message": error_msg}}

def handle_add_file(params):
    try:
        repo_name = params.get("repo_name")
        file_name = params.get("file_name")
        content = params.get("content", "")
        
        if not repo_name or not file_name:
            return {"error": {"code": -1, "message": "repo_name and file_name are required"}}
        
        repo = get_repo(repo_name)
        file_path = os.path.join(repo.working_tree_dir, file_name)
        
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        repo.index.add([file_name])
        response = f"File '{file_name}' added to repository '{repo_name}'"
        log_message("assistant", response)
        
        return {"result": {"success": True, "message": response}}
    except Exception as e:
        error_msg = f"Error adding file '{file_name}' to '{repo_name}': {str(e)}"
        log_message("assistant", error_msg)
        return {"error": {"code": -1, "message": error_msg}}

def handle_commit(params):
    try:
        repo_name = params.get("repo_name")
        message = params.get("message", "Commit from MCP")
        
        if not repo_name:
            return {"error": {"code": -1, "message": "repo_name is required"}}
        
        repo = get_repo(repo_name)
        
        if not repo.index.diff("HEAD") and not repo.untracked_files:
            response = f"No changes to commit in '{repo_name}'"
            log_message("assistant", response)
            return {"result": {"success": True, "message": response}}
        
        commit_obj = repo.index.commit(message)
        response = f"Commit made in '{repo_name}' with message: '{message}' (SHA: {commit_obj.hexsha[:8]})"
        log_message("assistant", response)
        
        return {"result": {"success": True, "message": response}}
    except Exception as e:
        error_msg = f"Error committing to '{repo_name}': {str(e)}"
        log_message("assistant", error_msg)
        return {"error": {"code": -1, "message": error_msg}}

def handle_list_files(params):
    try:
        repo_name = params.get("repo_name")
        
        if not repo_name:
            return {"error": {"code": -1, "message": "repo_name is required"}}
        
        repo = get_repo(repo_name)
        files = []
        
        for item in repo.tree().traverse():
            if item.type == 'blob':
                files.append(item.path)
        
        untracked = repo.untracked_files
        
        response = f"Repository '{repo_name}':\nTracked files: {files}\nUntracked files: {untracked}"
        log_message("assistant", response)
        
        return {"result": {
            "success": True, 
            "message": response, 
            "tracked_files": files, 
            "untracked_files": untracked
        }}
    except Exception as e:
        error_msg = f"Error listing files in '{repo_name}': {str(e)}"
        log_message("assistant", error_msg)
        return {"error": {"code": -1, "message": error_msg}}

def handle_git_status(params):
    try:
        repo_name = params.get("repo_name")
        
        if not repo_name:
            return {"error": {"code": -1, "message": "repo_name is required"}}
        
        repo = get_repo(repo_name)
        status = {
            "modified": [item.a_path for item in repo.index.diff(None)],
            "staged": [item.a_path for item in repo.index.diff("HEAD")],
            "untracked": repo.untracked_files
        }
        
        response = f"Git status for '{repo_name}':\nModified: {status['modified']}\nStaged: {status['staged']}\nUntracked: {status['untracked']}"
        log_message("assistant", response)
        
        return {"result": {"success": True, "message": response, "status": status}}
    except Exception as e:
        error_msg = f"Error getting status for '{repo_name}': {str(e)}"
        log_message("assistant", error_msg)
        return {"error": {"code": -1, "message": error_msg}}

def handle_list_tools(params):
    tools = [
        {
            "type": "function",
            "function": {
                "name": "create_repo",
                "description": "Create a new Git repository",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo_name": {
                            "type": "string",
                            "description": "Name of the repository to create"
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
                "description": "Add a file to the Git repository",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo_name": {
                            "type": "string",
                            "description": "Repository name"
                        },
                        "file_name": {
                            "type": "string",
                            "description": "File name to create"
                        },
                        "content": {
                            "type": "string",
                            "description": "File content",
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
                "description": "Make a commit in the repository",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo_name": {
                            "type": "string",
                            "description": "Repository name"
                        },
                        "message": {
                            "type": "string",
                            "description": "Commit message",
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
                "description": "List files in repository",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo_name": {
                            "type": "string",
                            "description": "Repository name"
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
                "description": "Show Git repository status",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo_name": {
                            "type": "string",
                            "description": "Repository name"
                        }
                    },
                    "required": ["repo_name"]
                }
            }
        }
    ]
    
    return {"result": {"status": "ok", "tools": tools}}

# ======================
# Main MCP loop
# ======================
def main():
    # Method handlers
    handlers = {
        "create_repo": handle_create_repo,
        "add_file": handle_add_file,
        "commit": handle_commit,
        "list_files": handle_list_files,
        "git_status": handle_git_status,
        "list_tools": handle_list_tools
    }
    
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            
            try:
                request = json.loads(line)
                
                if "method" not in request:
                    response = {
                        "jsonrpc": "2.0",
                        "id": request.get("id"),
                        "error": {"code": -32600, "message": "Invalid Request"}
                    }
                else:
                    method = request["method"]
                    params = request.get("params", {})
                    
                    if method in handlers:
                        result = handlers[method](params)
                        response = {
                            "jsonrpc": "2.0",
                            "id": request.get("id"),
                            **result
                        }
                    else:
                        response = {
                            "jsonrpc": "2.0",
                            "id": request.get("id"),
                            "error": {"code": -32601, "message": f"Method not found: {method}"}
                        }
                
                print(json.dumps(response))
                sys.stdout.flush()
                
            except json.JSONDecodeError as e:
                response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {str(e)}"}
                }
                print(json.dumps(response))
                sys.stdout.flush()
            except Exception as e:
                response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id") if 'request' in locals() else None,
                    "error": {"code": -32000, "message": f"Server error: {str(e)}"}
                }
                print(json.dumps(response))
                sys.stdout.flush()
    
    except KeyboardInterrupt:
        pass
    except Exception as e:
        sys.stderr.write(f"Fatal error: {str(e)}\n")
        sys.stderr.flush()

if __name__ == "__main__":
    main()