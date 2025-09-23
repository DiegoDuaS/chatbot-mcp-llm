from fastmcp import FastMCP
import os
import json
from datetime import datetime
from dotenv import load_dotenv
from typing import List, Dict, Any

# Initialize FastMCP server
mcp = FastMCP("filesystem-mcp")

# Configuration
load_dotenv()
FILESYSTEM_BASE_DIR = os.getenv("FILESYSTEM_BASE_DIR", os.path.join(os.path.dirname(__file__), "storage"))
os.makedirs(FILESYSTEM_BASE_DIR, exist_ok=True)

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "filesystem_mcp_log.json")
os.makedirs(LOG_DIR, exist_ok=True)

filesystem_conversation = []

# Logging functions
def save_log():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(filesystem_conversation, f, indent=2, ensure_ascii=False)

def log_message(role: str, content: str):
    filesystem_conversation.append({
        "role": role, 
        "content": content, 
        "timestamp": datetime.now().isoformat()
    })
    save_log()

# Helper Functions
def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal attacks"""
    return os.path.basename(filename)

def get_file_path(filename: str) -> str:
    """Get safe file path within base directory"""
    safe_filename = sanitize_filename(filename)
    return os.path.join(FILESYSTEM_BASE_DIR, safe_filename)

@mcp.tool()
def write_file(filename: str, content: str = "") -> str:
    """
    Create or update a file in storage
    
    Args:
        filename: Name of file to create/update
        content: File content (default: empty string)
    
    Returns:
        Success message with file details
    """
    try:
        if not filename:
            return "Error: filename is required"
        
        log_message("user", f"Writing file: {filename}")
        
        filepath = get_file_path(filename)
        safe_filename = sanitize_filename(filename)
        
        # Create directory if it doesn't exist
        file_dir = os.path.dirname(filepath)
        if file_dir and file_dir != FILESYSTEM_BASE_DIR:
            os.makedirs(file_dir, exist_ok=True)
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        
        response = f"File '{safe_filename}' created/updated successfully ({len(content)} characters)"
        log_message("assistant", response)
        
        return response
    except Exception as e:
        error_msg = f"Error writing file '{filename}': {str(e)}"
        log_message("assistant", error_msg)
        return error_msg

@mcp.tool()
def read_file(filename: str) -> str:
    """
    Read file content from storage
    
    Args:
        filename: Name of file to read
    
    Returns:
        File content or error message
    """
    try:
        if not filename:
            return "Error: filename is required"
        
        log_message("user", f"Reading file: {filename}")
        
        filepath = get_file_path(filename)
        safe_filename = sanitize_filename(filename)
        
        if not os.path.exists(filepath):
            return f"File '{safe_filename}' not found"
        
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        
        result = f"File '{safe_filename}' read successfully.\n\n--- Content ---\n{content}\n--- End Content ---"
        
        response = f"Read file '{safe_filename}' ({len(content)} characters)"
        log_message("assistant", response)
        
        return result
    except UnicodeDecodeError:
        error_msg = f"Cannot read file '{filename}' - appears to be binary"
        log_message("assistant", error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"Error reading file '{filename}': {str(e)}"
        log_message("assistant", error_msg)
        return error_msg

@mcp.tool()
def list_files() -> str:
    """
    List all files in storage
    
    Returns:
        Formatted list of files and directories
    """
    try:
        log_message("user", "Listing files")
        
        if not os.path.exists(FILESYSTEM_BASE_DIR):
            return "Storage directory is empty"
        
        files = []
        directories = []
        
        for item in os.listdir(FILESYSTEM_BASE_DIR):
            item_path = os.path.join(FILESYSTEM_BASE_DIR, item)
            if os.path.isfile(item_path):
                size = os.path.getsize(item_path)
                modified = datetime.fromtimestamp(os.path.getmtime(item_path)).strftime("%Y-%m-%d %H:%M")
                files.append({"name": item, "size": size, "modified": modified})
            elif os.path.isdir(item_path):
                directories.append(item)
        
        files.sort(key=lambda x: x["name"])
        directories.sort()
        
        result = f"Storage Contents:\n\n"
        
        if directories:
            result += f"Directories ({len(directories)}):\n"
            for dir_name in directories:
                result += f"  • {dir_name}/\n"
            result += "\n"
        
        if files:
            result += f"Files ({len(files)}):\n"
            for file in files:
                result += f"  • {file['name']} ({file['size']} bytes) - {file['modified']}\n"
        
        if not files and not directories:
            result = "Storage directory is empty"
        
        response = f"Listed {len(files)} files and {len(directories)} directories"
        log_message("assistant", response)
        
        return result
    except Exception as e:
        error_msg = f"Error listing files: {str(e)}"
        log_message("assistant", error_msg)
        return error_msg

@mcp.tool()
def delete_file(filename: str) -> str:
    """
    Delete a file from storage
    
    Args:
        filename: Name of file to delete
    
    Returns:
        Success message or error
    """
    try:
        if not filename:
            return "Error: filename is required"
        
        log_message("user", f"Deleting file: {filename}")
        
        filepath = get_file_path(filename)
        safe_filename = sanitize_filename(filename)
        
        if not os.path.exists(filepath):
            return f"File '{safe_filename}' not found"
        
        os.remove(filepath)
        
        response = f"File '{safe_filename}' deleted successfully"
        log_message("assistant", response)
        
        return response
    except Exception as e:
        error_msg = f"Error deleting file '{filename}': {str(e)}"
        log_message("assistant", error_msg)
        return error_msg

@mcp.tool()
def file_exists(filename: str) -> str:
    """
    Check if a file exists in storage
    
    Args:
        filename: Name of file to check
    
    Returns:
        File existence status and details
    """
    try:
        if not filename:
            return "Error: filename is required"
        
        log_message("user", f"Checking file existence: {filename}")
        
        filepath = get_file_path(filename)
        safe_filename = sanitize_filename(filename)
        exists = os.path.exists(filepath) and os.path.isfile(filepath)
        
        if exists:
            size = os.path.getsize(filepath)
            modified = datetime.fromtimestamp(os.path.getmtime(filepath)).strftime("%Y-%m-%d %H:%M:%S")
            created = datetime.fromtimestamp(os.path.getctime(filepath)).strftime("%Y-%m-%d %H:%M:%S")
            
            result = f"File '{safe_filename}' exists\n"
            result += f"Size: {size} bytes\n"
            result += f"Modified: {modified}\n"
            result += f"Created: {created}"
        else:
            result = f"File '{safe_filename}' does not exist"
        
        response = f"Checked existence of '{safe_filename}': {exists}"
        log_message("assistant", response)
        
        return result
    except Exception as e:
        error_msg = f"Error checking file '{filename}': {str(e)}"
        log_message("assistant", error_msg)
        return error_msg

@mcp.tool()
def create_directory(dirname: str) -> str:
    """
    Create a directory in storage
    
    Args:
        dirname: Name of directory to create
    
    Returns:
        Success message or error
    """
    try:
        if not dirname:
            return "Error: dirname is required"
        
        log_message("user", f"Creating directory: {dirname}")
        
        safe_dirname = sanitize_filename(dirname)
        dirpath = os.path.join(FILESYSTEM_BASE_DIR, safe_dirname)
        
        os.makedirs(dirpath, exist_ok=True)
        
        response = f"Directory '{safe_dirname}' created successfully"
        log_message("assistant", response)
        
        return response
    except Exception as e:
        error_msg = f"Error creating directory '{dirname}': {str(e)}"
        log_message("assistant", error_msg)
        return error_msg

@mcp.tool()
def get_file_info(filename: str) -> str:
    """
    Get detailed information about a file
    
    Args:
        filename: Name of file to inspect
    
    Returns:
        Detailed file information
    """
    try:
        if not filename:
            return "Error: filename is required"
        
        log_message("user", f"Getting file info: {filename}")
        
        filepath = get_file_path(filename)
        safe_filename = sanitize_filename(filename)
        
        if not os.path.exists(filepath):
            return f"File '{safe_filename}' not found"
        
        stat_info = os.stat(filepath)
        
        # Basic info
        info = f"File Information: {safe_filename}\n\n"
        info += f"Size: {stat_info.st_size} bytes\n"
        info += f"Created: {datetime.fromtimestamp(stat_info.st_ctime).strftime('%Y-%m-%d %H:%M:%S')}\n"
        info += f"Modified: {datetime.fromtimestamp(stat_info.st_mtime).strftime('%Y-%m-%d %H:%M:%S')}\n"
        info += f"Accessed: {datetime.fromtimestamp(stat_info.st_atime).strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        # File type detection
        _, ext = os.path.splitext(safe_filename)
        if ext:
            info += f"Extension: {ext}\n"
        
        # Try to determine if it's text or binary
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                first_chars = f.read(100)
                f.seek(0)  # Reset file pointer
                lines = len(f.readlines())
            
            info += f"Type: Text file\n"
            info += f"Lines: {lines}\n"
            if first_chars:
                info += f"Preview: {repr(first_chars[:50])}{'...' if len(first_chars) > 50 else ''}\n"
        except UnicodeDecodeError:
            info += f"Type: Binary file\n"
        
        response = f"Retrieved info for '{safe_filename}'"
        log_message("assistant", response)
        
        return info
    except Exception as e:
        error_msg = f"Error getting file info '{filename}': {str(e)}"
        log_message("assistant", error_msg)
        return error_msg

@mcp.tool()
def get_storage_stats() -> str:
    """
    Get storage statistics
    
    Returns:
        Storage usage statistics
    """
    try:
        log_message("user", "Getting storage stats")
        
        if not os.path.exists(FILESYSTEM_BASE_DIR):
            return f"Storage directory does not exist: {FILESYSTEM_BASE_DIR}"
        
        total_files = 0
        total_directories = 0
        total_size = 0
        file_types = {}
        
        for root, dirs, files in os.walk(FILESYSTEM_BASE_DIR):
            total_directories += len(dirs)
            for file in files:
                total_files += 1
                file_path = os.path.join(root, file)
                try:
                    file_size = os.path.getsize(file_path)
                    total_size += file_size
                    
                    _, ext = os.path.splitext(file)
                    ext = ext.lower() if ext else 'no extension'
                    file_types[ext] = file_types.get(ext, 0) + 1
                except:
                    continue
        
        result = f"Storage Statistics:\n\n"
        result += f"Base Directory: {FILESYSTEM_BASE_DIR}\n"
        result += f"Total Files: {total_files}\n"
        result += f"Total Directories: {total_directories}\n"
        result += f"Total Size: {total_size} bytes ({total_size / 1024:.2f} KB)\n\n"
        
        if file_types:
            result += "File Types:\n"
            for ext, count in sorted(file_types.items()):
                result += f"  • {ext}: {count} files\n"
        
        response = f"Retrieved storage stats: {total_files} files, {total_directories} directories"
        log_message("assistant", response)
        
        return result
    except Exception as e:
        error_msg = f"Error getting storage stats: {str(e)}"
        log_message("assistant", error_msg)
        return error_msg

# Run the server
if __name__ == "__main__":
    mcp.run()