import os
import json
import uuid
import subprocess
import threading
import time
from datetime import datetime
from dotenv import load_dotenv
import requests
from typing import Dict, List, Optional
from queue import Queue, Empty

# ======================
# Initial configuration
# ======================
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found in .env")

OPENAI_URL = "https://api.openai.com/v1/chat/completions"

HEADERS = {
    "Authorization": f"Bearer {OPENAI_API_KEY}",
    "Content-Type": "application/json"
}

# ======================
# MCP Server configuration
# ======================
class MCPServerConfig:
    def __init__(self, name: str, command: str, args: List[str] = None, 
                 description: str = "", enabled: bool = True, cwd: str = None):
        self.name = name
        self.command = command
        self.args = args or []
        self.description = description
        self.enabled = enabled
        self.cwd = cwd or "."
        self.tools = []
        self.process = None
        self.client = None

# FastMCP Server configurations
MCP_SERVERS = {
    "filesystem": MCPServerConfig(
        name="Filesystem Server",
        command="python",
        args=["filesystem_mcp.py"],  # Actualiza estas rutas según tu estructura
        description="FastMCP server for file operations",
        enabled=True
    ),
    "git": MCPServerConfig(
        name="Git Server", 
        command="python",
        args=["git_mcp.py"],
        description="FastMCP server for Git operations",
        enabled=True
    ),
    "rawg": MCPServerConfig(
        name="RAWG Games Server",
        command="python", 
        args=["rawg_mcp.py"],
        description="FastMCP server for game information",
        enabled=True
    ),
    "playlist": MCPServerConfig(
        name="Playlist Server",
        command="python",
        args=["playlist_mcp.py"], 
        description="FastMCP server for music playlists",
        enabled=False  # Deshabilitado por defecto, habilita si tienes este servidor
    )
}

# Session variables
messages = []
interaction_log = []
all_tools = []
function_server_map = {}

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
session_file = os.path.join(LOG_DIR, f"mcp_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")

# ======================
# FastMCP Communication functions
# ======================
def start_mcp_server(server: MCPServerConfig) -> bool:
    """Start a FastMCP server as a subprocess."""
    if not server.enabled:
        return False
        
    try:
        print(f"Starting {server.name}...")
        
        # Check if server file exists
        server_file = server.args[0] if server.args else server.command
        if not os.path.exists(server_file):
            print(f"Warning: {server_file} not found, skipping {server.name}")
            server.enabled = False
            return False
        
        # Start the FastMCP process
        server.process = subprocess.Popen(
            [server.command] + server.args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=server.cwd,
            bufsize=0
        )
        
        # Give FastMCP server time to initialize
        time.sleep(2)
        
        # Check if process is still running
        if server.process.poll() is not None:
            print(f"Failed to start {server.name} - process exited")
            stderr_output = server.process.stderr.read()
            if stderr_output:
                print(f"Error output: {stderr_output}")
            server.enabled = False
            return False
        
        print(f"Started {server.name} (PID: {server.process.pid})")
        return True
        
    except Exception as e:
        print(f"Error starting {server.name}: {e}")
        server.enabled = False
        return False

def send_mcp_request(server: MCPServerConfig, method: str, params: dict, timeout: int = 15) -> dict:
    """Send a request to FastMCP server via stdio."""
    if not server.process or server.process.poll() is not None:
        return {"error": {"code": -1, "message": "Server process not running"}}
    
    # FastMCP uses standard JSON-RPC 2.0
    request = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": method,
        "params": params
    }
    
    try:
        # Send request to FastMCP server
        request_line = json.dumps(request) + "\n"
        server.process.stdin.write(request_line)
        server.process.stdin.flush()
        
        # Wait for response from FastMCP
        start_time = time.time()
        while time.time() - start_time < timeout:
            if server.process.stdout.readable():
                line = server.process.stdout.readline()
                if line:
                    raw = line.strip()
                    if raw:
                        try:
                            response = json.loads(raw)
                            return response
                        except json.JSONDecodeError:
                            print(f"[DEBUG] Invalid JSON from {server.name}: {raw}")
                            continue
            else:
                time.sleep(0.1)
        
        return {"error": {"code": -1, "message": f"Timeout ({timeout}s) waiting for response from {server.name}"}}
    
    except BrokenPipeError:
        print(f"[ERROR] Broken pipe with {server.name} - server may have crashed")
        server.enabled = False
        return {"error": {"code": -1, "message": "Server communication failed"}}
    except Exception as e:
        return {"error": {"code": -1, "message": f"Communication error: {str(e)}"}}

def get_server_tools(server: MCPServerConfig) -> List[dict]:
    """Get available tools from a FastMCP server using introspection."""
    if not server.enabled or not server.process:
        return []
    
    print(f"Getting tools from {server.name}...")
    
    # FastMCP uses different introspection - let's try a direct approach
    # Send a simple test to see what the server responds with
    test_response = send_mcp_request(server, "ping", {})
    
    if "error" in test_response and "method not found" in test_response["error"]["message"].lower():
        print(f"Server {server.name} is responding but doesn't have ping method - this is normal for FastMCP")
    elif "error" in test_response:
        print(f"Communication error with {server.name}: {test_response['error']['message']}")
        server.enabled = False
        return []
    
    # For FastMCP, we need to extract tools from the server's code or use manual definition
    # Since FastMCP auto-generates from @mcp.tool() decorators, let's define them manually
    # based on what we know from our servers
    
    tools_mapping = {
        "Filesystem Server": [
            {
                "type": "function", 
                "function": {
                    "name": "write_file",
                    "description": "Create or update a file in storage",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filename": {"type": "string", "description": "Name of file to create/update"},
                            "content": {"type": "string", "description": "File content", "default": ""}
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
                            "filename": {"type": "string", "description": "Name of file to read"}
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
                    "parameters": {"type": "object", "properties": {}, "required": []}
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
                            "filename": {"type": "string", "description": "Name of file to delete"}
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
                            "filename": {"type": "string", "description": "Name of file to check"}
                        },
                        "required": ["filename"]
                    }
                }
            }
        ],
        "Git Server": [
            {
                "type": "function",
                "function": {
                    "name": "create_repo",
                    "description": "Create a new Git repository",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "repo_name": {"type": "string", "description": "Name of the repository to create"}
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
                            "repo_name": {"type": "string", "description": "Repository name"},
                            "file_name": {"type": "string", "description": "File name to create"},
                            "content": {"type": "string", "description": "File content", "default": ""}
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
                            "repo_name": {"type": "string", "description": "Repository name"},
                            "message": {"type": "string", "description": "Commit message", "default": "Commit from MCP"}
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
                            "repo_name": {"type": "string", "description": "Repository name"}
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
                            "repo_name": {"type": "string", "description": "Repository name"}
                        },
                        "required": ["repo_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_repos",
                    "description": "List all available repositories",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            }
        ],
        "RAWG Games Server": [
            {
                "type": "function",
                "function": {
                    "name": "search_games",
                    "description": "Search for games by name in RAWG database",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Game name to search for"},
                            "page_size": {"type": "integer", "description": "Number of results (max 20)", "default": 5}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_popular_games",
                    "description": "Get popular games list",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "page_size": {"type": "integer", "description": "Number of games (max 20)", "default": 10}
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_games_by_genre", 
                    "description": "Search games filtered by genre",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "genre": {"type": "string", "description": "Game genre (action, rpg, strategy)"},
                            "page_size": {"type": "integer", "description": "Number of games (max 20)", "default": 10}
                        },
                        "required": ["genre"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_game_details",
                    "description": "Get detailed information about a specific game",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "game_name": {"type": "string", "description": "Exact or partial game name"}
                        },
                        "required": ["game_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_trending_games",
                    "description": "Get currently trending games",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "page_size": {"type": "integer", "description": "Number of games (max 20)", "default": 10}
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_games_by_platform",
                    "description": "Get games filtered by platform",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "platform": {"type": "string", "description": "Platform name (pc, playstation-5, xbox-one, nintendo-switch)"},
                            "page_size": {"type": "integer", "description": "Number of games (max 20)", "default": 10}
                        },
                        "required": ["platform"]
                    }
                }
            }
        ]
    }
    
    # Get tools for this server
    server_tools = tools_mapping.get(server.name, [])
    
    # Map functions to this server
    for tool in server_tools:
        if "function" in tool:
            function_name = tool["function"]["name"]
            function_server_map[function_name] = server
    
    server.tools = server_tools
    
    print(f"{server.name}: {len(server_tools)} tools loaded")
    for tool in server_tools:
        func_name = tool["function"]["name"]
        func_desc = tool["function"]["description"]
        print(f"   - {func_name}: {func_desc}")
    
    return server_tools

def start_all_servers() -> List[dict]:
    """Start all FastMCP servers and load their tools."""
    global all_tools, function_server_map
    all_tools = []
    function_server_map = {}
    
    print("\nStarting FastMCP servers...")
    print("=" * 50)
    
    active_servers = 0
    for server_key, server in MCP_SERVERS.items():
        if start_mcp_server(server):
            # Wait a bit more for FastMCP to be ready
            time.sleep(1)
            tools = get_server_tools(server)
            all_tools.extend(tools)
            if tools:
                active_servers += 1
        else:
            print(f"Skipped {server.name}")
    
    print("=" * 50)
    print(f"Summary: {active_servers} active servers, {len(all_tools)} tools available")
    
    return all_tools

def execute_tool_call(tool_call: dict) -> str:
    """Execute a tool call on the corresponding FastMCP server."""
    function_name = tool_call["function"]["name"]
    try:
        arguments = json.loads(tool_call["function"]["arguments"])
    except json.JSONDecodeError:
        return f"Error: Invalid arguments for {function_name}"
    
    server = function_server_map.get(function_name)
    if not server:
        return f"Error: Unknown function '{function_name}'"
    
    print(f"Executing {function_name} on {server.name}")
    print(f"Parameters: {arguments}")
    
    # Call FastMCP server directly with the function name and arguments
    # FastMCP servers expect direct function calls, not tools/call wrapper
    response = send_mcp_request(server, function_name, arguments)
    
    if "result" in response:
        result = response["result"]
        # FastMCP returns the function result directly
        return str(result)
            
    elif "error" in response:
        error_msg = response["error"]["message"]
        return f"Error on {server.name}: {error_msg}"
    
    return "Operation completed"

def stop_all_servers():
    """Stop all FastMCP server processes."""
    print("\nShutting down FastMCP servers...")
    for server_key, server in MCP_SERVERS.items():
        if server.process and server.process.poll() is None:
            print(f"Stopping {server.name}...")
            server.process.terminate()
            try:
                server.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.process.kill()
                print(f"Force killed {server.name}")

# ======================
# OpenAI functions
# ======================
def create_system_prompt() -> str:
    """Create system prompt based on available FastMCP tools."""
    active_servers = [s for s in MCP_SERVERS.values() if s.enabled and s.tools]
    
    prompt = """You are an expert assistant with access to multiple FastMCP (Model Context Protocol) servers.

AVAILABLE SERVERS:
"""
    
    for server in active_servers:
        prompt += f"\n{server.name.upper()}:\n"
        if server.description:
            prompt += f"   Description: {server.description}\n"
        prompt += "   Tools:\n"
        for tool in server.tools:
            if "function" in tool:
                func_name = tool["function"]["name"]
                func_desc = tool["function"].get("description", "No description")
                prompt += f"   - {func_name}: {func_desc}\n"
    
    prompt += """
INSTRUCTIONS:
- Use the available tools to help users accomplish their tasks
- Be descriptive about what you're doing with the tools
- Ask for clarification if you need more information  
- You can combine tools from different servers
- Always confirm the results of operations
- Handle errors gracefully and explain what went wrong
- When creating files or repos, use descriptive names
- For Git operations, make meaningful commit messages

Respond helpfully and professionally."""
    
    return prompt

def send_to_openai(messages_context: List[dict], tools: Optional[List[dict]] = None) -> tuple:
    """Send messages to OpenAI and handle tool calls."""
    payload = {
        "model": "gpt-4o-mini", 
        "messages": messages_context,
        "max_tokens": 2000,
        "temperature": 0.7
    }
    
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    
    try:
        response = requests.post(OPENAI_URL, headers=HEADERS, json=payload, timeout=30)
        
        if response.status_code != 200:
            return f"HTTP error {response.status_code}: {response.text}", []
        
        data = response.json()
        message = data["choices"][0]["message"]
        
        # Handle tool calls
        if "tool_calls" in message and message["tool_calls"]:
            messages_context.append(message)
            
            used_tools = []
            for tool_call in message["tool_calls"]:
                used_tools.append(tool_call["function"]["name"])
                tool_result = execute_tool_call(tool_call)
                
                tool_message = {
                    "role": "tool", 
                    "tool_call_id": tool_call["id"],
                    "content": tool_result
                }
                messages_context.append(tool_message)
            
            # Get final response after tool execution
            final_payload = {
                "model": "gpt-4o-mini",
                "messages": messages_context,
                "max_tokens": 2000,
                "temperature": 0.7
            }
            
            final_response = requests.post(OPENAI_URL, headers=HEADERS, json=final_payload, timeout=30)
            final_data = final_response.json()
            final_content = final_data["choices"][0]["message"]["content"]
            
            return final_content, used_tools
        
        return message["content"], []
        
    except Exception as e:
        return f"Connection error: {str(e)}", []

# ======================
# Utility functions
# ======================
def save_log(user: str, bot: str, tools_used: List[str] = None):
    """Save conversation log."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "user": user,
        "bot": bot,
        "tools_used": tools_used or []
    }
    interaction_log.append(entry)
    
    try:
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(interaction_log, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving log: {e}")

def show_log():
    """Display interaction history."""
    if not interaction_log:
        print("No interactions recorded yet")
        return
    
    print("\nInteraction History:")
    print("=" * 50)
    for i, entry in enumerate(interaction_log, 1):
        timestamp = entry['timestamp'].split('T')[1][:8]
        print(f"\n[{i}] {timestamp}")
        print(f"User: {entry['user']}")
        print(f"Bot: {entry['bot'][:150]}{'...' if len(entry['bot']) > 150 else ''}")
        if entry.get('tools_used'):
            print(f"Tools: {', '.join(entry['tools_used'])}")

def show_servers():
    """Show status of all FastMCP servers."""
    print("\nFastMCP Server Status:")
    print("=" * 50)
    for key, server in MCP_SERVERS.items():
        if server.process and server.process.poll() is None:
            status = f"✓ Running (PID: {server.process.pid})"
        else:
            status = "✗ Not running"
        
        print(f"{status} - {server.name}")
        print(f"   Command: {server.command} {' '.join(server.args)}")
        if server.description:
            print(f"   Description: {server.description}")
        print(f"   Tools: {len(server.tools)}")
        
        if server.tools:
            for tool in server.tools[:3]:
                if "function" in tool:
                    name = tool["function"]["name"]
                    desc = tool["function"].get("description", "")[:50]
                    print(f"     - {name}: {desc}{'...' if len(desc) >= 50 else ''}")
            if len(server.tools) > 3:
                print(f"     ... and {len(server.tools) - 3} more")
        print()

def show_help():
    """Show available commands."""
    print("\nAvailable commands:")
    print("  'exit' - End session and stop servers")
    print("  'log' - View interaction history")
    print("  'servers' - Show FastMCP server status")
    print("  'reload' - Restart servers and reload tools")
    print("  'help' - Show this help")
    print("\nExample requests:")
    print("  - 'Create a file called hello.txt with some content'")
    print("  - 'Show me all files in storage'")
    print("  - 'Create a git repo called my-project'")
    print("  - 'Search for games like Zelda'")
    print()

# ======================
# Main function
# ======================
def main():
    global messages
    
    print("FastMCP Client - Model Context Protocol")
    print("=" * 50)
    
    try:
        # Start all FastMCP servers
        tools = start_all_servers()
        
        if not tools:
            print("No tools available. Check server configurations and file paths.")
            return
        
        # Create system prompt
        system_prompt = create_system_prompt()
        messages = [{"role": "system", "content": system_prompt}]
        
        print(f"\nLog will be saved to: {session_file}")
        show_help()
        
        while True:
            try:
                user_input = input("You: ").strip()
                
                if not user_input:
                    continue
                
                # Handle commands
                if user_input.lower() == "exit":
                    break
                elif user_input.lower() == "log":
                    show_log()
                    continue
                elif user_input.lower() == "servers":
                    show_servers()
                    continue
                elif user_input.lower() == "reload":
                    print("Restarting FastMCP servers...")
                    stop_all_servers()
                    time.sleep(3)
                    tools = start_all_servers()
                    system_prompt = create_system_prompt()
                    messages = [{"role": "system", "content": system_prompt}]
                    print("Servers reloaded!")
                    continue
                elif user_input.lower() == "help":
                    show_help()
                    continue
                
                # Process user message
                messages.append({"role": "user", "content": user_input})
                
                response, tools_used = send_to_openai(messages.copy(), tools=tools)
                
                messages.append({"role": "assistant", "content": response})
                
                save_log(user_input, response, tools_used)
                
                print(f"\nBot: {response}")
                if tools_used:
                    print(f"🔧 Tools used: {', '.join(tools_used)}")
                print()
                
            except KeyboardInterrupt:
                print("\nSession interrupted")
                break
            except Exception as e:
                print(f"Error: {e}")
                continue
    
    finally:
        # Always clean up
        stop_all_servers()
        print(f"\nSession saved to: {session_file}")

if __name__ == "__main__":
    main()