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
import signal
import sys

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

# Solo Sleep Coach server
sleep_server = MCPServerConfig(
    name="Sleep Coach Server",
    command="python",
    args=[r'sleep_coach.py'],
    description="AI-powered sleep coach for personalized sleep analysis and recommendations",
    enabled=True,
    cwd=r"C:\Users\diego\OneDrive\Escritorio\2025\Semestre VIII\Redes\SleepCoachServer"
)

# Session variables
messages = []
interaction_log = []
all_tools = []

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
session_file = os.path.join(LOG_DIR, f"sleep_coach_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")

# ======================
# Signal handler for graceful shutdown
# ======================
def signal_handler(sig, frame):
    print('\nShutting down gracefully...')
    stop_server()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# ======================
# MCP Communication functions
# ======================
def enqueue_output(out, queue):
    """Function to read output from a process and put it into a queue."""
    try:
        for line in iter(out.readline, ''):
            if line:
                queue.put(line)
        out.close()
    except Exception as e:
        print(f"Reader thread error: {e}")

def start_sleep_server() -> bool:
    """Start the Sleep Coach MCP server."""
    global sleep_server
    
    try:
        print(f"Starting {sleep_server.name}...")
        
        # Check if server file exists
        server_file = os.path.join(sleep_server.cwd, sleep_server.args[0])
        if not os.path.exists(server_file):
            print(f"Error: {server_file} not found")
            return False
        
        # Start the process with better error handling
        sleep_server.process = subprocess.Popen(
            [sleep_server.command] + sleep_server.args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=sleep_server.cwd,
            bufsize=0  # Unbuffered
        )
        
        # Start reader thread
        sleep_server.reader_thread = threading.Thread(
            target=enqueue_output, 
            args=(sleep_server.process.stdout, sleep_server.output_queue), 
            daemon=True
        )
        sleep_server.reader_thread.start()
        
        # Wait longer for async server to initialize
        print("Waiting for server to initialize...")
        time.sleep(8)
        
        # Check if process is still running
        if sleep_server.process.poll() is not None:
            stderr_output = sleep_server.process.stderr.read()
            print(f"Failed to start {sleep_server.name} - process exited")
            print(f"Error output: {stderr_output}")
            return False
        
        print(f"Started {sleep_server.name} (PID: {sleep_server.process.pid})")
        
        # Send initialization request
        print("Initializing server...")
        init_response = send_mcp_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "sleep-coach-client",
                "version": "1.0.0"
            }
        })
        
        if "error" in init_response:
            print(f"Initialization failed: {init_response['error']['message']}")
            return False
            
        print("Server initialized successfully")
        
        # Send initialized notification (required by MCP protocol)
        print("Sending initialized notification...")
        initialized_request = {
            "jsonrpc": "2.0",
            "method": "initialized",
            "params": {}
        }
        request_line = json.dumps(initialized_request) + "\n"
        sleep_server.process.stdin.write(request_line)
        sleep_server.process.stdin.flush()
        
        # Give server a moment to process the notification
        time.sleep(1)
        print("Initialization sequence complete")
        
        return True
        
    except Exception as e:
        print(f"Error starting {sleep_server.name}: {e}")
        return False

def send_mcp_request(method: str, params: dict, timeout: int = 30) -> dict:
    """Send a JSON-RPC request to the Sleep Coach server."""
    global sleep_server
    
    if not sleep_server.process or sleep_server.process.poll() is not None:
        return {"error": {"code": -1, "message": "Server process not running"}}
    
    request_id = str(uuid.uuid4())
    request = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params
    }
    
    try:
        # Send request
        request_line = json.dumps(request) + "\n"
        print(f"Sending request: {method} with params: {params}")
        print(f"Full request: {request_line.strip()}")
        sleep_server.process.stdin.write(request_line)
        sleep_server.process.stdin.flush()
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                line = sleep_server.output_queue.get(timeout=2)
                raw = line.strip()
                if not raw:
                    continue
                
                print(f"Received raw: {raw}")
                
                try:
                    response = json.loads(raw)
                    print(f"Parsed response: {response}")
                    
                    if "id" in response and response["id"] == request_id:
                        return response
                    elif "method" in response:
                        print(f"Got notification: {response}")
                        continue
                    else:
                        print(f"Got response with different ID or format: {response}")
                        continue
                        
                except json.JSONDecodeError as e:
                    print(f"JSON decode error: {e}")
                    print(f"Raw response that failed: {raw}")
                    continue
            
            except Empty:
                print("Queue timeout, continuing...")
                continue
        
        # Check if process is still alive
        if sleep_server.process.poll() is not None:
            stderr_output = sleep_server.process.stderr.read()
            return {"error": {"code": -1, "message": f"Process died. Stderr: {stderr_output}"}}
        
        return {"error": {"code": -1, "message": f"Timeout ({timeout}s) waiting for response"}}
    
    except Exception as e:
        return {"error": {"code": -1, "message": f"Communication error: {str(e)}"}}

def get_server_tools() -> List[dict]:
    """Get tools from the Sleep Coach server."""
    global sleep_server, all_tools
    
    print(f"Getting tools from {sleep_server.name}...")
    
    # Send the tools list request with empty params
    response = send_mcp_request("list_tools", {})
    
    if "result" in response:
        tools = response["result"]
        print(f"Raw tools response: {tools}")
        
        # The MCP server returns tools directly as a list
        if isinstance(tools, list):
            # Convert to OpenAI tools format
            openai_tools = []
            for tool in tools:
                if "name" in tool and "inputSchema" in tool:
                    openai_tool = {
                        "type": "function",
                        "function": {
                            "name": tool["name"],
                            "description": tool.get("description", ""),
                            "parameters": tool["inputSchema"]
                        }
                    }
                    openai_tools.append(openai_tool)
            
            sleep_server.tools = openai_tools
            all_tools = openai_tools
            
            print(f"{sleep_server.name}: {len(tools)} tools loaded")
            for tool in openai_tools:
                func_name = tool["function"]["name"]
                func_desc = tool["function"].get("description", "No description")[:100]
                print(f"    - {func_name}: {func_desc}")
            
            return openai_tools
        else:
            print(f"Unexpected tools format: {type(tools)}")
    
    elif "error" in response:
        print(f"Error getting tools: {response['error']['message']}")
        print(f"Full error response: {response}")
    
    return []

def execute_tool_call(tool_call: dict) -> str:
    """Execute a tool call on the Sleep Coach server."""
    function_name = tool_call["function"]["name"]
    arguments = json.loads(tool_call["function"]["arguments"])
    
    print(f"Executing {function_name}")
    print(f"Parameters: {arguments}")
    
    # Send tool call request
    response = send_mcp_request("call_tool", {
        "name": function_name, 
        "arguments": arguments
    })
    
    if "result" in response:
        result = response["result"]
        # Handle different result formats
        if isinstance(result, list):
            # MCP TextContent format
            if all(isinstance(item, dict) and "text" in item for item in result):
                return "\n".join([item["text"] for item in result])
        
        if isinstance(result, dict) and "message" in result:
            return result["message"]
            
        return str(result)
    
    elif "error" in response:
        error_msg = response["error"]["message"]
        return f"Error: {error_msg}"
    
    return "Operation completed"

def stop_server():
    """Stop the Sleep Coach server process."""
    global sleep_server
    if sleep_server.process and sleep_server.process.poll() is None:
        print(f"Stopping {sleep_server.name}...")
        sleep_server.process.terminate()
        try:
            sleep_server.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            sleep_server.process.kill()
            print(f"Force killed {sleep_server.name}")

# ======================
# OpenAI functions
# ======================
def create_system_prompt() -> str:
    """Create system prompt for Sleep Coach."""
    prompt = """You are a Sleep Coach AI assistant with access to specialized sleep analysis and recommendation tools.

AVAILABLE TOOLS:
"""
    
    for tool in all_tools:
        func = tool["function"]
        prompt += f"- {func['name']}: {func.get('description', 'No description')}\n"
    
    prompt += """
INSTRUCTIONS:
- You are an expert sleep coach who helps users improve their sleep quality and habits
- Use the available tools to provide personalized sleep analysis and recommendations
- For new users, start by creating a user profile with create_user_profile
- Always provide actionable, evidence-based sleep advice
- Be supportive and understanding about sleep difficulties
- Explain the reasoning behind your recommendations
- Ask follow-up questions to better understand sleep issues

Your goal is to help users achieve better sleep through personalized guidance and practical recommendations."""
    
    return prompt

def send_to_openai(messages_context: List[dict], tools: Optional[List[dict]] = None) -> tuple:
    """Send messages to OpenAI and handle tool calls."""
    payload = {
        "model": "gpt-4o-mini",
        "messages": messages_context,
        "max_tokens": 2000,
        "temperature": 0.3  # Lower temperature for more consistent sleep advice
    }
    
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    
    try:
        response = requests.post(OPENAI_URL, headers=HEADERS, json=payload, timeout=60)
        
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
                "max_tokens": 2000,
                "temperature": 0.3
            }
            
            final_response = requests.post(OPENAI_URL, headers=HEADERS, json=final_payload, timeout=60)
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

def show_help():
    """Show available commands."""
    print("\nAvailable commands:")
    print("    'exit' - End session and stop server")
    print("    'log' - View interaction history")
    print("    'status' - Show server status")
    print("    'restart' - Restart server")
    print("    'help' - Show this help")
    print("\nSleep Coach Commands (examples):")
    print("    'Create my sleep profile'")
    print("    'Analyze my sleep pattern'")
    print("    'I have trouble falling asleep'")
    print("    'Create a weekly sleep schedule for me'")
    print()

# ======================
# Main function
# ======================
def main():
    global messages, all_tools
    
    print("Sleep Coach MCP Client")
    print("=" * 40)
    
    try:
        # Start Sleep Coach server
        if not start_sleep_server():
            print("Failed to start Sleep Coach server. Exiting.")
            return
        
        # Get tools
        all_tools = get_server_tools()
        
        if not all_tools:
            print("No tools available from Sleep Coach server.")
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
                    if not interaction_log:
                        print("No interactions recorded yet")
                    else:
                        for i, entry in enumerate(interaction_log[-5:], 1):  # Show last 5
                            timestamp = entry['timestamp'].split('T')[1][:8]
                            print(f"[{i}] {timestamp} - Tools: {', '.join(entry.get('tools_used', []))}")
                            print(f"You: {entry['user'][:100]}...")
                            print(f"Bot: {entry['bot'][:100]}...\n")
                    continue
                elif user_input.lower() == "status":
                    if sleep_server.process and sleep_server.process.poll() is None:
                        print(f"Sleep Coach Server: Running (PID: {sleep_server.process.pid})")
                        print(f"Tools available: {len(all_tools)}")
                    else:
                        print("Sleep Coach Server: Not running")
                    continue
                elif user_input.lower() == "restart":
                    print("Restarting Sleep Coach server...")
                    stop_server()
                    time.sleep(3)
                    if start_sleep_server():
                        all_tools = get_server_tools()
                        system_prompt = create_system_prompt()
                        messages = [{"role": "system", "content": system_prompt}]
                        print("Server restarted successfully")
                    else:
                        print("Failed to restart server")
                    continue
                elif user_input.lower() == "help":
                    show_help()
                    continue
                
                # Process user message
                messages.append({"role": "user", "content": user_input})
                
                response, tools_used = send_to_openai(messages.copy(), tools=all_tools)
                
                messages.append({"role": "assistant", "content": response})
                
                save_log(user_input, response, tools_used)
                
                print(f"\nSleep Coach: {response}")
                if tools_used:
                    print(f"\nTools used: {', '.join(tools_used)}")
                print("-" * 50)
                
            except KeyboardInterrupt:
                print("\nSession interrupted")
                break
            except Exception as e:
                print(f"Error: {e}")
                continue
    
    finally:
        # Always clean up
        stop_server()
        print(f"\nSession saved to: {session_file}")

if __name__ == "__main__":
    main()