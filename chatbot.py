#!/usr/bin/env python3
import os
import requests
import json
from datetime import datetime
from dotenv import load_dotenv

# ==============================
# LOAD ENVIRONMENT VARIABLES
# ==============================
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("Please configure OPENAI_API_KEY in your .env file")

# ==============================
# CONFIG
# ==============================
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
HEADERS = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# ==============================
# MULTI-SERVER MCP MANAGEMENT
# ==============================
servers = {}  # {"server_name": {"url": "...", "tools": [...]}}
active_server = None

def add_server(name, url):
    try:
        resp = requests.get(f"{url}/tools")
        resp.raise_for_status()
        tools = resp.json().get("tools", [])
        servers[name] = {"url": url, "tools": tools}
        print(f"Server '{name}' added with {len(tools)} tools")
        return True
    except Exception as e:
        print(f"Could not add server '{name}': {e}")
        return False

def list_servers():
    return [f"{name} ({info['url']})" for name, info in servers.items()]

def set_active_server(name):
    global active_server
    if name in servers:
        active_server = name
        print(f"Active server set to '{name}'")
        return True
    else:
        print(f"Server '{name}' not found")
        return False

def log_interaction(server_name, role, message):
    filename = os.path.join(LOG_DIR, f"{server_name}.log")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(filename, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {role}: {message}\n")

# ==============================
# OPENAI CALL
# ==============================
def call_openai(messages):
    payload = {"model": "gpt-4o-mini", "messages": messages, "max_tokens": 500}
    resp = requests.post(OPENAI_URL, headers=HEADERS, json=payload)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]

# ==============================
# TOOL CALL
# ==============================
def call_tool(server_name, tool_name, params):
    server_info = servers.get(server_name)
    if not server_info:
        return {"success": False, "error": f"Server '{server_name}' not found"}
    
    tool_info = next((t for t in server_info["tools"] if t["name"] == tool_name), None)
    if not tool_info:
        return {"success": False, "error": f"Tool '{tool_name}' not found on server '{server_name}'"}
    
    try:
        endpoint = tool_info["endpoint"]
        url = f"{server_info['url']}{endpoint}"
        resp = requests.post(url, json=params)  # <-- POST JSON
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"success": False, "error": str(e)}
    
# ==============================
# MAIN LOOP
# ==============================
def main():
    global active_server
    print("🤖 Multi-MCP Assistant")
    print("Commands: /exit | /summary | /list_servers | /server <name> | /add_server <name> <url>")
    
    conversation = []

    while True:
        user_input = input("👤 You: ").strip()
        if not user_input:
            continue
        if user_input.lower() == "/exit":
            print("👋 Goodbye!")
            break
        elif user_input.lower() == "/summary":
            if active_server:
                filename = os.path.join(LOG_DIR, f"{active_server}.log")
                print(f"\n--- Last 10 messages for {active_server} ---")
                if os.path.exists(filename):
                    with open(filename, "r", encoding="utf-8") as f:
                        lines = f.readlines()[-10:]
                        for line in lines:
                            print(line.strip())
                else:
                    print("No log yet.")
            continue
        elif user_input.lower() == "/list_servers":
            for s in list_servers():
                print(s)
            continue
        elif user_input.startswith("/server "):
            _, name = user_input.split(maxsplit=1)
            set_active_server(name)
            continue
        elif user_input.startswith("/add_server "):
            try:
                _, name, url = user_input.split(maxsplit=2)
                add_server(name, url)
            except ValueError:
                print("Usage: /add_server <name> <url>")
            continue

        if not active_server:
            print("❌ No active server. Add one with /add_server and set it with /server")
            continue

        # SYSTEM PROMPT for forcing tool usage
        active_tools = servers[active_server]["tools"]
        system_prompt = {
            "role": "system",
            "content": f"""
            You are a Multi-MCP assistant. The active server is '{active_server}'.
            Available tools for this server:
            {json.dumps(active_tools, indent=2)}

            Always respond in JSON ONLY to call a tool if you need to perform an action:
            {{"tool": "<tool_name>", "params": {{...}}}}

            Do NOT give general instructions. Always use the MCP server endpoints.
            """
        }

        conversation.append(system_prompt)
        conversation.append({"role": "user", "content": user_input})
        log_interaction(active_server, "User", user_input)

        try:
            print("🤔 Thinking...")
            llm_response = call_openai(conversation)

            # Try parsing JSON tool call
            try:
                parsed = json.loads(llm_response)
                if isinstance(parsed, dict) and "tool" in parsed:
                    tool_name = parsed["tool"]
                    params = parsed.get("params", {})
                    print(f"🔎 Calling tool {tool_name} on server {active_server} with {params}")
                    tool_result = call_tool(active_server, tool_name, params)
                    log_interaction(active_server, "ToolResult", json.dumps(tool_result, ensure_ascii=False))
                    
                    # Feed result back to LLM
                    followup = f"Here is the result from tool '{tool_name}': {json.dumps(tool_result, ensure_ascii=False)}\nPlease answer the user's original question: {user_input}"
                    conversation.append({"role": "assistant", "content": llm_response})
                    conversation.append({"role": "user", "content": followup})
                    final_answer = call_openai(conversation)
                    conversation.append({"role": "assistant", "content": final_answer})
                    log_interaction(active_server, "Assistant", final_answer)
                    print(f"🤖 {final_answer}\n")
                else:
                    # Normal text
                    conversation.append({"role": "assistant", "content": llm_response})
                    log_interaction(active_server, "Assistant", llm_response)
                    print(f"🤖 {llm_response}\n")
            except json.JSONDecodeError:
                conversation.append({"role": "assistant", "content": llm_response})
                log_interaction(active_server, "Assistant", llm_response)
                print(f"🤖 {llm_response}\n")
        except Exception as e:
            print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()
