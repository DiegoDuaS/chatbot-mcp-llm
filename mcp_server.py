# mcp_server.py
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI()

# Permitir CORS localmente
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.post("/chat")
async def chat_endpoint(request: Request):
    data = await request.json()
    messages = data.get("messages", [])
    system_prompt = data.get("system_prompt", "")
    
    # Respuesta dummy: solo repite el último mensaje del usuario
    last_user_msg = ""
    for msg in reversed(messages):
        if msg["role"] == "user":
            last_user_msg = msg["content"]
            break
    
    response_text = f"Respuesta dummy: {last_user_msg}" if last_user_msg else "Hola! Soy el MCP server local."
    
    return {"response": response_text}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
