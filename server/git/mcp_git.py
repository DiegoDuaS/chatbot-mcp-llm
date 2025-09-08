#!/usr/bin/env python3
import os
import json
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from git import Repo, GitCommandError
from dotenv import load_dotenv

load_dotenv()
GIT_BASE_DIR = os.getenv("GIT_BASE_DIR", "./git_repos")
os.makedirs(GIT_BASE_DIR, exist_ok=True)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# Logs
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "git_chat_log.json")
os.makedirs(LOG_DIR, exist_ok=True)
git_conversation = []

def save_log():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(git_conversation, f, indent=2, ensure_ascii=False)


def get_repo(repo_name):
    path = os.path.join(GIT_BASE_DIR, repo_name)
    if os.path.exists(path):
        return Repo(path)
    else:
        os.makedirs(path, exist_ok=True)
        return Repo.init(path)


@app.post("/git")
async def git_chat(request: Request):
    data = await request.json()
    user_message = data.get("message", "")

    # Guardar mensaje del usuario
    git_conversation.append({"role": "user", "content": user_message, "timestamp": datetime.now().isoformat()})

    # Comandos simples detectados por el servidor
    response = ""
    try:
        if "create repo" in user_message.lower():
            repo_name = user_message.split()[-1]
            get_repo(repo_name)
            response = f"Repository '{repo_name}' created."
        elif "add file" in user_message.lower():
            parts = user_message.split()
            repo_name = parts[2]
            file_name = parts[3]
            content = " ".join(parts[4:]) if len(parts) > 4 else ""
            repo = get_repo(repo_name)
            file_path = os.path.join(repo.working_tree_dir, file_name)
            with open(file_path, "w") as f:
                f.write(content)
            repo.index.add([file_path])
            response = f"File '{file_name}' added to '{repo_name}'."
        elif "commit" in user_message.lower():
            parts = user_message.split()
            repo_name = parts[1]
            message = " ".join(parts[2:]) if len(parts) > 2 else "Commit from MCP"
            repo = get_repo(repo_name)
            repo.index.commit(message)
            response = f"Commit made in '{repo_name}' with message '{message}'."
        elif "list files" in user_message.lower():
            repo_name = user_message.split()[-1]
            repo = get_repo(repo_name)
            files = os.listdir(repo.working_tree_dir)
            response = f"Files in '{repo_name}': {files}"
        else:
            response = "I can handle commands: create repo <name>, add file <repo> <file> <content>, commit <repo> <message>, list files <repo>."
    except GitCommandError as e:
        response = f"Git error: {str(e)}"

    git_conversation.append({"role": "assistant", "content": response, "timestamp": datetime.now().isoformat()})
    save_log()
    return {"response": response}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
