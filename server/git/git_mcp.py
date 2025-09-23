from fastmcp import FastMCP
import os
import json
from datetime import datetime
from git import Repo, GitCommandError
from dotenv import load_dotenv
from typing import List, Dict, Any

# Initialize FastMCP server
mcp = FastMCP("git-mcp")

# Configuration
load_dotenv()
GIT_BASE_DIR = os.getenv("GIT_BASE_DIR", "./repos")
os.makedirs(GIT_BASE_DIR, exist_ok=True)

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "git_mcp_log.json")
os.makedirs(LOG_DIR, exist_ok=True)

git_conversation = []

# Logging functions
def save_log():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(git_conversation, f, indent=2, ensure_ascii=False)

def log_message(role: str, content: str):
    git_conversation.append({
        "role": role, 
        "content": content, 
        "timestamp": datetime.now().isoformat()
    })
    save_log()

# Git helper function
def get_repo(repo_name: str):
    """Get or create a Git repository"""
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

@mcp.tool()
def create_repo(repo_name: str) -> str:
    """
    Create a new Git repository
    
    Args:
        repo_name: Name of the repository to create
    
    Returns:
        Success message with repository path
    """
    try:
        if not repo_name:
            return "Error: repo_name is required"
        
        repo = get_repo(repo_name)
        response = f"Repository '{repo_name}' created successfully at {repo.working_tree_dir}"
        log_message("assistant", response)
        
        return response
    except Exception as e:
        error_msg = f"Error creating repository '{repo_name}': {str(e)}"
        log_message("assistant", error_msg)
        return error_msg

@mcp.tool()
def add_file(repo_name: str, file_name: str, content: str = "") -> str:
    """
    Add a file to the Git repository
    
    Args:
        repo_name: Repository name
        file_name: File name to create
        content: File content (default: empty string)
    
    Returns:
        Success message
    """
    try:
        if not repo_name or not file_name:
            return "Error: repo_name and file_name are required"
        
        repo = get_repo(repo_name)
        file_path = os.path.join(repo.working_tree_dir, file_name)
        
        # Create directory structure if needed
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Write file content
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        # Add to git index
        repo.index.add([file_name])
        
        response = f"File '{file_name}' added to repository '{repo_name}' ({len(content)} characters)"
        log_message("assistant", response)
        
        return response
    except Exception as e:
        error_msg = f"Error adding file '{file_name}' to '{repo_name}': {str(e)}"
        log_message("assistant", error_msg)
        return error_msg

@mcp.tool()
def commit(repo_name: str, message: str = "Commit from MCP") -> str:
    """
    Make a commit in the repository
    
    Args:
        repo_name: Repository name
        message: Commit message (default: "Commit from MCP")
    
    Returns:
        Success message with commit SHA
    """
    try:
        if not repo_name:
            return "Error: repo_name is required"
        
        repo = get_repo(repo_name)
        
        # Check if there are changes to commit
        if not repo.index.diff("HEAD") and not repo.untracked_files:
            response = f"No changes to commit in '{repo_name}'"
            log_message("assistant", response)
            return response
        
        # Add all untracked files first
        if repo.untracked_files:
            repo.index.add(repo.untracked_files)
        
        # Make commit
        commit_obj = repo.index.commit(message)
        
        response = f"Commit made in '{repo_name}' with message: '{message}' (SHA: {commit_obj.hexsha[:8]})"
        log_message("assistant", response)
        
        return response
    except Exception as e:
        error_msg = f"Error committing to '{repo_name}': {str(e)}"
        log_message("assistant", error_msg)
        return error_msg

@mcp.tool()
def list_files(repo_name: str) -> str:
    """
    List files in repository
    
    Args:
        repo_name: Repository name
    
    Returns:
        Formatted list of tracked and untracked files
    """
    try:
        if not repo_name:
            return "Error: repo_name is required"
        
        repo = get_repo(repo_name)
        
        # Get tracked files
        tracked_files = []
        try:
            for item in repo.tree().traverse():
                if item.type == 'blob':
                    tracked_files.append(item.path)
        except:
            # No commits yet, tree is empty
            tracked_files = []
        
        # Get untracked files
        untracked_files = repo.untracked_files
        
        result = f"Repository '{repo_name}' file listing:\n\n"
        
        if tracked_files:
            result += f"Tracked files ({len(tracked_files)}):\n"
            for file in sorted(tracked_files):
                result += f"  • {file}\n"
            result += "\n"
        
        if untracked_files:
            result += f"Untracked files ({len(untracked_files)}):\n"
            for file in sorted(untracked_files):
                result += f"  • {file}\n"
        
        if not tracked_files and not untracked_files:
            result += "Repository is empty"
        
        response = f"Listed files in repository '{repo_name}'"
        log_message("assistant", response)
        
        return result
    except Exception as e:
        error_msg = f"Error listing files in '{repo_name}': {str(e)}"
        log_message("assistant", error_msg)
        return error_msg

@mcp.tool()
def git_status(repo_name: str) -> str:
    """
    Show Git repository status
    
    Args:
        repo_name: Repository name
    
    Returns:
        Formatted Git status information
    """
    try:
        if not repo_name:
            return "Error: repo_name is required"
        
        repo = get_repo(repo_name)
        
        # Get status information
        modified = [item.a_path for item in repo.index.diff(None)]
        staged = [item.a_path for item in repo.index.diff("HEAD")]
        untracked = repo.untracked_files
        
        result = f"Git status for repository '{repo_name}':\n\n"
        
        if staged:
            result += f"Staged for commit ({len(staged)}):\n"
            for file in sorted(staged):
                result += f"  • {file}\n"
            result += "\n"
        
        if modified:
            result += f"Modified but not staged ({len(modified)}):\n"
            for file in sorted(modified):
                result += f"  • {file}\n"
            result += "\n"
        
        if untracked:
            result += f"Untracked files ({len(untracked)}):\n"
            for file in sorted(untracked):
                result += f"  • {file}\n"
            result += "\n"
        
        if not staged and not modified and not untracked:
            result += "Working directory is clean"
        
        # Add commit count info
        try:
            commit_count = len(list(repo.iter_commits()))
            result += f"\nTotal commits: {commit_count}"
        except:
            result += f"\nTotal commits: 0 (no commits yet)"
        
        response = f"Retrieved status for repository '{repo_name}'"
        log_message("assistant", response)
        
        return result
    except Exception as e:
        error_msg = f"Error getting status for '{repo_name}': {str(e)}"
        log_message("assistant", error_msg)
        return error_msg

@mcp.tool()
def list_repos() -> str:
    """
    List all available repositories
    
    Returns:
        Formatted list of repositories
    """
    try:
        if not os.path.exists(GIT_BASE_DIR):
            return f"No repositories found. Base directory: {GIT_BASE_DIR}"
        
        repos = []
        for item in os.listdir(GIT_BASE_DIR):
            repo_path = os.path.join(GIT_BASE_DIR, item)
            if os.path.isdir(repo_path) and os.path.exists(os.path.join(repo_path, '.git')):
                try:
                    repo = Repo(repo_path)
                    commit_count = len(list(repo.iter_commits()))
                    repos.append({
                        "name": item,
                        "path": repo_path,
                        "commits": commit_count
                    })
                except:
                    repos.append({
                        "name": item,
                        "path": repo_path,
                        "commits": 0
                    })
        
        if not repos:
            return f"No Git repositories found in {GIT_BASE_DIR}"
        
        result = f"Found {len(repos)} Git repositories:\n\n"
        for repo in sorted(repos, key=lambda x: x["name"]):
            result += f"• {repo['name']} ({repo['commits']} commits)\n  Path: {repo['path']}\n\n"
        
        response = f"Listed {len(repos)} repositories"
        log_message("assistant", response)
        
        return result
    except Exception as e:
        error_msg = f"Error listing repositories: {str(e)}"
        log_message("assistant", error_msg)
        return error_msg

# Run the server
if __name__ == "__main__":
    mcp.run()