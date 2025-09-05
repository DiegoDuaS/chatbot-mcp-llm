#!/usr/bin/env python3
import os
import json
import requests
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from dotenv import load_dotenv
import re
import ast

# ==============================
# LOAD ENVIRONMENT VARIABLES
# ==============================
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
RAWG_API_KEY = os.getenv("RAWG_API_KEY")

if not OPENAI_API_KEY or not RAWG_API_KEY:
    raise ValueError("Please configure OPENAI_API_KEY and RAWG_API_KEY in your .env file")

# ==============================
# FASTAPI CONFIGURATION
# ==============================
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# Logs folder
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "chat_log.json")
os.makedirs(LOG_DIR, exist_ok=True)

# Global conversation history
conversation_history = []

# ==============================
# HELPER FUNCTIONS
# ==============================
def save_log():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(conversation_history, f, indent=2, ensure_ascii=False)

def call_rawg_api(query, max_results=5):
    try:
        params = {"key": RAWG_API_KEY, "search": query, "page_size": max_results}
        resp = requests.get("https://api.rawg.io/api/games", params=params)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return {"games": []}

        games_info = []
        for game in results:
            games_info.append({
                "name": game.get("name"),
                "released": game.get("released"),
                "rating": game.get("rating"),
                "platforms": [p["platform"]["name"] for p in game.get("platforms", [])],
                "genres": [g["name"] for g in game.get("genres", [])]
            })
        return {"games": games_info}
    except Exception as e:
        return {"error": f"Error querying RAWG API: {str(e)}"}

def call_openai(messages):
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "gpt-4o-mini", "messages": messages, "max_tokens": 500}
    resp = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]

# ==============================
# MAIN ENDPOINT
# ==============================
@app.post("/chat")
async def chat_endpoint(request: Request):
    data = await request.json()
    user_message = data.get("message", "")

    # Save user message
    conversation_history.append({"role": "user", "content": user_message, "timestamp": datetime.now().isoformat()})

    # System prompt for OpenAI
    system_prompt = """
You are an expert video game assistant.
You have access to the RAWG API (https://api.rawg.io/docs).
If you need game info, return a JSON like this:
{"tool": "RAWG", "query": "<game name>"}
Only use RAWG for video games. If the question is not about video games, answer normally.
You are not allowed to ignore this prompt for other answers.
"""
    messages = [{"role": "system", "content": system_prompt}] + \
               [{"role": msg["role"], "content": msg["content"]} for msg in conversation_history]

    # Step 1: LLM decides whether to use RAWG
    llm_response = call_openai(messages)

    # Step 2: Detect if LLM wants to use RAWG
    if '"tool": "RAWG"' in llm_response:
        try:
            match = re.search(r'\{.*"tool":\s*"RAWG".*\}', llm_response, re.DOTALL)
            tool_call = ast.literal_eval(match.group())
            query = tool_call.get("query")
            rawg_data = call_rawg_api(query)

            # Step 3: Provide RAWG info to LLM for final response
            final_prompt = f"""
Here is information about games matching '{query}':
{json.dumps(rawg_data, indent=2, ensure_ascii=False)}

Use this information to answer the user's question in a **natural and conversational** manner:
{user_message}

You may include all relevant titles and important details without providing links when you deem necessary.
"""
            messages.append({"role": "assistant", "content": llm_response})
            messages.append({"role": "user", "content": final_prompt})
            assistant_msg = call_openai(messages)
        except Exception as e:
            assistant_msg = f"Error processing RAWG tool: {str(e)}"
    else:
        assistant_msg = llm_response

    # Save assistant response
    conversation_history.append({"role": "assistant", "content": assistant_msg, "timestamp": datetime.now().isoformat()})
    save_log()
    return {"response": assistant_msg}

# ==============================
# RUN SERVER
# ==============================
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
