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
# CARGA DE VARIABLES DE ENTORNO
# ==============================
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
RAWG_API_KEY = os.getenv("RAWG_API_KEY")

if not OPENAI_API_KEY or not RAWG_API_KEY:
    raise ValueError("Configura OPENAI_API_KEY y RAWG_API_KEY en tu .env")

# ==============================
# CONFIGURACIÓN FASTAPI
# ==============================
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# Carpeta de logs
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "chat_log.json")
os.makedirs(LOG_DIR, exist_ok=True)

# Historial global
conversation_history = []

# ==============================
# FUNCIONES AUXILIARES
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
        return {"error": f"Error al consultar RAWG API: {str(e)}"}

def call_openai(messages):
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "gpt-4o-mini", "messages": messages, "max_tokens": 500}
    resp = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]

# ==============================
# ENDPOINT PRINCIPAL
# ==============================
@app.post("/chat")
async def chat_endpoint(request: Request):
    data = await request.json()
    user_message = data.get("message", "")

    # Guardar mensaje del usuario
    conversation_history.append({"role": "user", "content": user_message, "timestamp": datetime.now().isoformat()})

    # Prompt de instrucciones para OpenAI
    system_prompt = """
Eres un asistente experto en videojuegos.
Tienes acceso a la herramienta RAWG (API: https://api.rawg.io/docs).
Si necesitas info sobre un juego, devuelve un JSON así:
{"tool": "RAWG", "query": "<nombre del juego>"}
Solo usa RAWG para videojuegos. Si la pregunta no es sobre videojuegos, responde normalmente.
"""
    messages = [{"role": "system", "content": system_prompt}] + \
               [{"role": msg["role"], "content": msg["content"]} for msg in conversation_history]

    # Paso 1: LLM decide si usar RAWG
    llm_response = call_openai(messages)

    # Paso 2: Detectar si LLM quiere usar RAWG
    if '"tool": "RAWG"' in llm_response:
        try:
            match = re.search(r'\{.*"tool":\s*"RAWG".*\}', llm_response, re.DOTALL)
            tool_call = ast.literal_eval(match.group())
            query = tool_call.get("query")
            rawg_data = call_rawg_api(query)

            # Paso 3: Dar info RAWG al LLM para generar respuesta final
            final_prompt = f"""
Tienes información de los juegos relacionados con la búsqueda '{query}':
{json.dumps(rawg_data, indent=2, ensure_ascii=False)}

Usa esta información para responder de manera **natural y conversacional** a la pregunta del usuario:
{user_message}

Incluye todos los títulos relevantes y detalles importantes sin dar links.
"""
            messages.append({"role": "assistant", "content": llm_response})
            messages.append({"role": "user", "content": final_prompt})
            assistant_msg = call_openai(messages)
        except Exception as e:
            assistant_msg = f"Error procesando herramienta RAWG: {str(e)}"
    else:
        assistant_msg = llm_response

    # Guardar respuesta del asistente
    conversation_history.append({"role": "assistant", "content": assistant_msg, "timestamp": datetime.now().isoformat()})
    save_log()
    return {"response": assistant_msg}

# ==============================
# EJECUCIÓN DEL SERVIDOR
# ==============================
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
