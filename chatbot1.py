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
        self.reader_thread = None
        self.output_queue = Queue()
        self.is_initialized = False
        self.request_counter = 0

    def get_request_id(self) -> str:
        """Generate a unique request ID"""
        self.request_counter += 1
        return f"{self.name}_req_{self.request_counter}_{uuid.uuid4().hex[:8]}"

# Server configurations
MCP_SERVERS = {
    "git": MCPServerConfig(
        name="Git Server",
        command="python",
        args=["server/git/git_mcp.py"],
        description="Server for Git operations via stdio",
        enabled=True
    ),
    "filesystem": MCPServerConfig(
        name="Filesystem Server",
        command="python",
        args=["server/filesystem/filesystem_mcp.py"],
        description="Server for file operations via stdio",
        enabled=True
    ),
    "rawg": MCPServerConfig(
        name="RAWG Games Server",
        command="python",
        args=["server/videogames/server_mcp.py"],
        description="Server for game info via stdio",
        enabled=True
    ),
    "sleep_coach": MCPServerConfig(
        name="Sleep Coach Server",
        command="python",
        args=[r'sleep_coach.py'],
        description="AI-powered sleep coach that provides personalized sleep analysis, recommendations, schedules, and guidance. Use for questions about sleep patterns, insomnia, sleep quality, bedtime routines, chronotypes, and sleep optimization.",
        enabled=True,
        cwd=r"C:\Users\diego\OneDrive\Escritorio\2025\Semestre VIII\Redes\SleepCoachServer"
    ),
    "movies_server": MCPServerConfig(
        name="Movies Server",
        command="python",
        args=[r'movie_server.py'],
        description="Movie recommendations and information server",
        enabled=True,
        cwd=r"C:\Users\diego\OneDrive\Escritorio\2025\Semestre VIII\Redes\Movies_ChatBot"
    ),
    "kitchen_server": MCPServerConfig(
        name="Kitchen Server",
        command="node",
        args=[r'src/mcp-server.js'],
        description="Server focused on food, nutrition, and recipe suggestions.",
        enabled=True,
        cwd=r"C:\Users\diego\OneDrive\Escritorio\2025\Semestre VIII\Redes\kitchen-mcp"
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
# MCP Communication functions
# ======================
def enqueue_output(out, queue):
    """Function to read output from a process and put it into a queue."""
    for line in iter(out.readline, ''):
        queue.put(line)
    out.close()

def start_mcp_server(server: MCPServerConfig) -> bool:
    """Start an MCP server as a subprocess."""
    if not server.enabled:
        return False
        
    try:
        print(f"Starting {server.name}...")
        
        # Check if server file exists
        server_file = os.path.join(server.cwd, server.args[0])
        if not os.path.exists(server_file):
            print(f"Warning: {server_file} not found, skipping {server.name}")
            server.enabled = False
            return False
        
        # Start the process
        server.process = subprocess.Popen(
            [server.command] + server.args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=server.cwd,
            bufsize=1
        )
        
        # Start a non-blocking reader thread for stdout
        server.reader_thread = threading.Thread(
            target=enqueue_output, 
            args=(server.process.stdout, server.output_queue), 
            daemon=True
        )
        server.reader_thread.start()
        
        # Wait a moment for server to start
        time.sleep(2)
        
        # Check if process is still running
        if server.process.poll() is not None:
            stderr_output = server.process.stderr.read()
            print(f"Failed to start {server.name} - process exited")
            print(f"Error output: {stderr_output}")
            server.enabled = False
            return False
        
        # Initialize MCP connection
        if initialize_mcp_server(server):
            print(f" Started and initialized {server.name} (PID: {server.process.pid})")
            return True
        else:
            print(f" Failed to initialize {server.name}")
            server.enabled = False
            return False
        
    except Exception as e:
        print(f"Error starting {server.name}: {e}")
        server.enabled = False
        return False

def initialize_mcp_server(server: MCPServerConfig) -> bool:
    """Initialize MCP connection with proper handshake"""
    try:
        print(f"Initializing MCP connection for {server.name}...")
        
        # 1. Send initialize message
        init_message = {
            "jsonrpc": "2.0",
            "id": server.get_request_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "roots": {
                        "listChanged": True
                    },
                    "sampling": {}
                },
                "clientInfo": {
                    "name": "mcp-python-client",
                    "version": "1.0.0"
                }
            }
        }
        
        response = send_mcp_request_raw(server, init_message, timeout=10)
        if not response or "error" in response:
            print(f" Error in initialization for {server.name}: {response.get('error') if response else 'No response'}")
            return False
        
        print(f" Initialize response from {server.name}: {response.get('result', {}).get('serverInfo', {}).get('name', 'Unknown')}")
        
        # 2. Send initialized notification
        initialized_notification = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {}
        }
        
        # Send notification (no response expected)
        send_notification(server, initialized_notification)
        
        server.is_initialized = True
        print(f" MCP initialization complete for {server.name}")
        return True
        
    except Exception as e:
        print(f" Error in MCP initialization for {server.name}: {e}")
        return False

def send_notification(server: MCPServerConfig, notification: dict):
    """Send a notification (no response expected)"""
    if not server.process or server.process.poll() is not None:
        return
    
    try:
        notification_line = json.dumps(notification) + "\n"
        server.process.stdin.write(notification_line)
        server.process.stdin.flush()
        print(f"Sent notification to {server.name}: {notification['method']}")
    except Exception as e:
        print(f"Error sending notification to {server.name}: {e}")

def send_mcp_request_raw(server: MCPServerConfig, request: dict, timeout: int = 15) -> dict:
    """Send a raw JSON-RPC request to an MCP server"""
    if not server.process or server.process.poll() is not None:
        return {"error": {"code": -1, "message": "Server process not running"}}
    
    try:
        # Send request
        request_line = json.dumps(request) + "\n"
        server.process.stdin.write(request_line)
        server.process.stdin.flush()
        
        request_id = request.get("id")
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                line = server.output_queue.get(timeout=1)
                raw = line.strip()
                if not raw:
                    continue
                
                try:
                    response = json.loads(raw)
                    if "id" in response and response["id"] == request_id:
                        return response
                    elif "method" in response and "params" in response:
                        # This is a notification, log it and continue
                        print(f"[NOTIFICATION] from {server.name}: {response['method']}")
                        continue
                    else:
                        print(f"[DEBUG] Ignoring message from {server.name}: {raw}")
                        continue
                        
                except json.JSONDecodeError:
                    print(f"[DEBUG] Invalid JSON from {server.name}: {raw}")
                    continue
            
            except Empty:
                continue
        
        return {"error": {"code": -1, "message": f"Timeout ({timeout}s) waiting for response from {server.name}"}}
    
    except Exception as e:
        return {"error": {"code": -1, "message": f"Communication error: {str(e)}"}}

def send_mcp_request(server: MCPServerConfig, method: str, params: dict, timeout: int = 15) -> dict:
    """Send a JSON-RPC request to an MCP server via stdin/stdout."""
    if not server.is_initialized and method != "initialize":
        return {"error": {"code": -1, "message": "Server not initialized"}}
    
    request = {
        "jsonrpc": "2.0",
        "id": server.get_request_id(),
        "method": method,
        "params": params
    }
    
    return send_mcp_request_raw(server, request, timeout)

def get_server_tools(server: MCPServerConfig) -> List[dict]:
    """Get tools from an MCP server."""
    if not server.enabled or not server.process or not server.is_initialized:
        return []
    
    print(f"Getting tools from {server.name}...")
    
    # Send the list_tools request
    response = send_mcp_request(server, "tools/list", {})
    
    if "result" in response and isinstance(response["result"], dict) and "tools" in response["result"]:
        tools = response["result"]["tools"]
        server.tools = tools
        
        # Map functions to this server
        for tool in tools:
            if "name" in tool:
                function_name = tool["name"]
                function_server_map[function_name] = server
        
        print(f"{server.name}: {len(tools)} tools loaded")
        for tool in tools:
            name = tool.get("name", "Unknown")
            desc = tool.get("description", "No description")
            print(f"    - {name}: {desc}")
        
        return tools
    elif "error" in response:
        print(f"Error getting tools from {server.name}: {response['error']['message']}")
        server.enabled = False
    
    return []

def start_all_servers() -> List[dict]:
    """Start all MCP servers and load their tools."""
    global all_tools, function_server_map
    all_tools = []
    function_server_map = {}
    
    print("\nStarting MCP servers...")
    print("=" * 50)
    
    active_servers = 0
    for server_key, server in MCP_SERVERS.items():
        if start_mcp_server(server):
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
    """Execute a tool call on the corresponding server."""
    function_name = tool_call["function"]["name"]
    arguments = json.loads(tool_call["function"]["arguments"])
    
    server = function_server_map.get(function_name)
    if not server:
        return f"Error: Unknown function '{function_name}'"
    
    print(f"Executing {function_name} on {server.name}")
    print(f"Parameters: {arguments}")
    
    # Use the correct MCP method for calling tools
    response = send_mcp_request(server, "tools/call", {
        "name": function_name, 
        "arguments": arguments
    })
    
    if "result" in response:
        result = response["result"]
        
        # Handle different result formats
        if isinstance(result, list):
            # MCP servers return a list of content items
            content_items = []
            for item in result:
                if isinstance(item, dict):
                    if "text" in item:
                        content_items.append(item["text"])
                    elif "content" in item:
                        content_items.append(str(item["content"]))
                    else:
                        content_items.append(str(item))
                else:
                    content_items.append(str(item))
            return "\n".join(content_items)
        
        elif isinstance(result, dict):
            if "content" in result:
                return str(result["content"])
            elif "message" in result:
                return result["message"]
            else:
                return str(result)
        
        return str(result)
    elif "error" in response:
        error_msg = response["error"]["message"]
        return f"Error on {server.name}: {error_msg}"
    
    return "Operation completed"

def stop_all_servers():
    """Stop all MCP server processes."""
    print("\nShutting down MCP servers...")
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
    """Create system prompt based on available tools."""
    active_servers = [s for s in MCP_SERVERS.values() if s.enabled and s.tools]
    
    prompt = """You are an expert assistant with access to multiple MCP (Model Context Protocol) servers.

AVAILABLE SERVERS:
"""
    
    for server in active_servers:
        prompt += f"\n{server.name.upper()}:\n"
        if server.description:
            prompt += f"    Description: {server.description}\n"
        prompt += "    Tools:\n"
        for tool in server.tools:
            name = tool.get("name", "Unknown")
            desc = tool.get("description", "No description")
            prompt += f"    - {name}: {desc}\n"
    
    prompt += """
INSTRUCTIONS:
- Use the available tools to help users accomplish their tasks
- Be descriptive about what you're doing
- Ask for clarification if you need more information
- You can combine tools from different servers
- Always confirm the results of operations
- Handle errors and explain what went wrong
- If you can't recieve information don't give suposed answers, just say that the tool didn't function or returned anything.

Respond helpfully and professionally."""
    
    return prompt

def convert_mcp_tools_to_openai_format(mcp_tools: List[dict]) -> List[dict]:
    """Convert MCP tool format to OpenAI function calling format"""
    openai_tools = []
    
    for tool in mcp_tools:
        if "name" in tool:
            openai_tool = {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", "No description available"),
                    "parameters": tool.get("inputSchema", {
                        "type": "object",
                        "properties": {},
                        "required": []
                    })
                }
            }
            openai_tools.append(openai_tool)
    
    return openai_tools

def send_to_openai(messages_context: List[dict], tools: Optional[List[dict]] = None) -> tuple:
    """Send messages to OpenAI and handle tool calls."""
    # Convert MCP tools to OpenAI format
    openai_tools = convert_mcp_tools_to_openai_format(tools) if tools else None
    
    payload = {
        "model": "gpt-4o-mini",
        "messages": messages_context,
        "max_tokens": 1500,
        "temperature": 0.7
    }
    
    if openai_tools:
        payload["tools"] = openai_tools
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
            
            # Get final response
            final_payload = {
                "model": "gpt-4o-mini",
                "messages": messages_context,
                "max_tokens": 1500,
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
    """Show status of all MCP servers."""
    print("\nMCP Server Status:")
    print("=" * 50)
    for key, server in MCP_SERVERS.items():
        status_parts = []
        
        if server.process and server.process.poll() is None:
            status_parts.append(f"Running (PID: {server.process.pid})")
        else:
            status_parts.append("Not running")
        
        if server.is_initialized:
            status_parts.append("Initialized")
        else:
            status_parts.append("Not initialized")
        
        status = " - ".join(status_parts)
        
        print(f"{status} - {server.name}")
        print(f"    Command: {server.command} {' '.join(server.args)}")
        if server.description:
            print(f"    Description: {server.description}")
        print(f"    Tools: {len(server.tools)}")
        
        if server.tools:
            for tool in server.tools[:3]:
                name = tool.get("name", "Unknown")
                desc = tool.get("description", "")[:50]
                print(f"      - {name}: {desc}{'...' if len(desc) >= 50 else ''}")
            if len(server.tools) > 3:
                print(f"      ... and {len(server.tools) - 3} more")
        print()

def show_help():
    """Show available commands."""
    print("\nAvailable commands:")
    print("    'exit' - End session and stop servers")
    print("    'log' - View interaction history")
    print("    'servers' - Show MCP server status")
    print("    'reload' - Restart servers and reload tools")
    print("    'help' - Show this help")
    print()

# ======================
# Main function
# ======================
def main():
    global messages
    
    print("MCP Client with Proper Initialization")
    print("=" * 50)
    
    try:
        # Start all servers
        tools = start_all_servers()
        
        if not tools:
            print("No tools available. Check server configurations.")
            return
        
        # Create system prompt
        system_prompt = create_system_prompt()
        messages = [{"role": "system", "content": system_prompt}]
        
        print(f"Log will be saved to: {session_file}")
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
                    print("Restarting servers...")
                    stop_all_servers()
                    time.sleep(2)
                    tools = start_all_servers()
                    system_prompt = create_system_prompt()
                    messages = [{"role": "system", "content": system_prompt}]
                    continue
                elif user_input.lower() == "help":
                    show_help()
                    continue
                
                # Process user message
                messages.append({"role": "user", "content": user_input})
                
                response, tools_used = send_to_openai(messages.copy(), tools=tools)
                
                messages.append({"role": "assistant", "content": response})
                
                save_log(user_input, response, tools_used)
                
                print(f"0-[°-°]-0 Bot: {response}")
                if tools_used:
                    print(f"Tools used: {', '.join(tools_used)}")
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
        print(f"Session saved to: {session_file}")

if __name__ == "__main__":
    main()