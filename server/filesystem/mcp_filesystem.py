import os
import json
import sys
from datetime import datetime

# ======================
# Configuration
# ======================
BASE_DIR = os.path.join(os.path.dirname(__file__), "storage")
os.makedirs(BASE_DIR, exist_ok=True)

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "filesystem_mcp_stdio_log.json")
os.makedirs(LOG_DIR, exist_ok=True)

fs_conversation = []

# ======================
# Logging
# ======================
def save_log():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(fs_conversation, f, indent=2, ensure_ascii=False)

def log_message(role, content):
    fs_conversation.append({"role": role, "content": content, "timestamp": datetime.now().isoformat()})
    save_log()

# ======================
# MCP Command Handlers
# ======================
def handle_write_file(params):
    try:
        filename = params.get("filename")
        content = params.get("content", "")
        
        if not filename:
            return {"error": {"code": -1, "message": "filename is required"}}
        
        # Sanitize filename
        safe_filename = os.path.basename(filename)
        filepath = os.path.join(BASE_DIR, safe_filename)
        
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        
        response = f"File '{safe_filename}' created/updated successfully ({len(content)} characters)"
        log_message("assistant", response)
        
        return {"result": {
            "success": True,
            "message": response,
            "filename": safe_filename,
            "size": len(content)
        }}
    except Exception as e:
        error_msg = f"Error writing file '{filename}': {str(e)}"
        log_message("assistant", error_msg)
        return {"error": {"code": -1, "message": error_msg}}

def handle_read_file(params):
    try:
        filename = params.get("filename")
        
        if not filename:
            return {"error": {"code": -1, "message": "filename is required"}}
        
        safe_filename = os.path.basename(filename)
        filepath = os.path.join(BASE_DIR, safe_filename)
        
        if not os.path.exists(filepath):
            error_msg = f"File '{safe_filename}' not found"
            return {"error": {"code": -1, "message": error_msg}}
        
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        
        response = f"File '{safe_filename}' read successfully ({len(content)} characters)"
        log_message("assistant", response)
        
        return {"result": {
            "success": True,
            "message": response,
            "filename": safe_filename,
            "content": content,
            "size": len(content)
        }}
    except UnicodeDecodeError:
        error_msg = f"Cannot read file '{filename}' - appears to be binary"
        return {"error": {"code": -1, "message": error_msg}}
    except Exception as e:
        error_msg = f"Error reading file '{filename}': {str(e)}"
        log_message("assistant", error_msg)
        return {"error": {"code": -1, "message": error_msg}}

def handle_list_files(params):
    try:
        if not os.path.exists(BASE_DIR):
            return {"result": {
                "success": True,
                "message": "Storage directory empty",
                "files": [],
                "count": 0
            }}
        
        files = []
        for filename in os.listdir(BASE_DIR):
            filepath = os.path.join(BASE_DIR, filename)
            if os.path.isfile(filepath):
                file_info = {
                    "name": filename,
                    "size": os.path.getsize(filepath),
                    "modified": datetime.fromtimestamp(os.path.getmtime(filepath)).isoformat()
                }
                files.append(file_info)
        
        files.sort(key=lambda x: x["name"])
        
        response = f"Found {len(files)} files in storage"
        log_message("assistant", response)
        
        return {"result": {
            "success": True,
            "message": response,
            "files": files,
            "count": len(files),
            "storage_path": BASE_DIR
        }}
    except Exception as e:
        error_msg = f"Error listing files: {str(e)}"
        log_message("assistant", error_msg)
        return {"error": {"code": -1, "message": error_msg}}

def handle_delete_file(params):
    try:
        filename = params.get("filename")
        
        if not filename:
            return {"error": {"code": -1, "message": "filename is required"}}
        
        safe_filename = os.path.basename(filename)
        filepath = os.path.join(BASE_DIR, safe_filename)
        
        if not os.path.exists(filepath):
            error_msg = f"File '{safe_filename}' not found"
            return {"error": {"code": -1, "message": error_msg}}
        
        if os.path.isdir(filepath):
            error_msg = f"'{safe_filename}' is a directory, not a file"
            return {"error": {"code": -1, "message": error_msg}}
        
        os.remove(filepath)
        
        response = f"File '{safe_filename}' deleted successfully"
        log_message("assistant", response)
        
        return {"result": {"success": True, "message": response, "filename": safe_filename}}
    except Exception as e:
        error_msg = f"Error deleting file '{filename}': {str(e)}"
        log_message("assistant", error_msg)
        return {"error": {"code": -1, "message": error_msg}}

def handle_file_exists(params):
    try:
        filename = params.get("filename")
        
        if not filename:
            return {"error": {"code": -1, "message": "filename is required"}}
        
        safe_filename = os.path.basename(filename)
        filepath = os.path.join(BASE_DIR, safe_filename)
        
        exists = os.path.exists(filepath)
        is_file = os.path.isfile(filepath) if exists else False
        
        if exists and is_file:
            file_size = os.path.getsize(filepath)
            modified = datetime.fromtimestamp(os.path.getmtime(filepath)).isoformat()
            response = f"File '{safe_filename}' exists ({file_size} bytes)"
        elif exists:
            response = f"'{safe_filename}' exists but is a directory"
        else:
            response = f"File '{safe_filename}' does not exist"
        
        log_message("assistant", response)
        
        return {"result": {
            "success": True,
            "message": response,
            "filename": safe_filename,
            "exists": exists and is_file,
            "size": os.path.getsize(filepath) if exists and is_file else 0,
            "modified": datetime.fromtimestamp(os.path.getmtime(filepath)).isoformat() if exists and is_file else None
        }}
    except Exception as e:
        error_msg = f"Error checking file '{filename}': {str(e)}"
        log_message("assistant", error_msg)
        return {"error": {"code": -1, "message": error_msg}}

def handle_list_tools(params):
    tools = [
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Create or update a file in storage",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "Name of file to create/update"
                        },
                        "content": {
                            "type": "string",
                            "description": "File content",
                            "default": ""
                        }
                    },
                    "required": ["filename"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read file content from storage",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "Name of file to read"
                        }
                    },
                    "required": ["filename"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "List all files in storage",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "delete_file",
                "description": "Delete a file from storage",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "Name of file to delete"
                        }
                    },
                    "required": ["filename"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "file_exists",
                "description": "Check if a file exists in storage",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "Name of file to check"
                        }
                    },
                    "required": ["filename"]
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
        "write_file": handle_write_file,
        "read_file": handle_read_file,
        "list_files": handle_list_files,
        "delete_file": handle_delete_file,
        "file_exists": handle_file_exists,
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