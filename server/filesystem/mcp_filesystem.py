import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import json

# Carpeta base donde se permitirán operaciones
BASE_DIR = os.path.join(os.path.dirname(__file__), "storage")
os.makedirs(BASE_DIR, exist_ok=True)

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.post("/filesystem/write")
async def write_file(request: Request):
    data = await request.json()
    filename = data.get("filename")
    content = data.get("content", "")

    if not filename:
        return {"error": "Se requiere el nombre del archivo."}

    filepath = os.path.join(BASE_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return {"status": "ok", "message": f"Archivo '{filename}' creado/actualizado."}

@app.post("/filesystem/read")
async def read_file(request: Request):
    data = await request.json()
    filename = data.get("filename")

    if not filename:
        return {"error": "Se requiere el nombre del archivo."}

    filepath = os.path.join(BASE_DIR, filename)
    if not os.path.exists(filepath):
        return {"error": f"Archivo '{filename}' no encontrado."}

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    return {"status": "ok", "filename": filename, "content": content}

@app.post("/filesystem/list")
async def list_files():
    files = os.listdir(BASE_DIR)
    return {"status": "ok", "files": files}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8100)
