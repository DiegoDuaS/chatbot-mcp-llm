#!/usr/bin/env python3
import os
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import uvicorn
from typing import List
from pydantic import BaseModel

# ==============================
# LOAD ENV VARIABLES
# ==============================
load_dotenv()
RAWG_API_KEY = os.getenv("RAWG_API_KEY")
if not RAWG_API_KEY:
    raise ValueError("Please configure RAWG_API_KEY in your .env file")

# ==============================
# FASTAPI CONFIG
# ==============================
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# ==============================
# HELPERS
# ==============================
def rawg_fetch(endpoint, params=None):
    try:
        params = params or {}
        params["key"] = RAWG_API_KEY
        url = f"https://api.rawg.io/api/{endpoint}"
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        return {"success": True, "data": resp.json(), "error": None}
    except Exception as e:
        return {"success": False, "data": None, "error": str(e)}

def simplify_games(raw_games):
    simplified = []
    for g in raw_games:
        simplified.append({
            "id": g.get("id"),
            "name": g.get("name"),
            "released": g.get("released"),
            "rating": g.get("rating"),
            "platforms": [p["platform"]["name"] for p in g.get("platforms", [])],
            "genres": [g_["name"] for g_ in g.get("genres", [])]
        })
    return simplified

# ==============================
# MODELS
# ==============================
class ToolCall(BaseModel):
    tool: str
    params: dict

class TextContent(BaseModel):
    type: str
    text: str

# ==============================
# TOOLS LIST
# ==============================
TOOLS = [
    {
        "name": "rawg_search",
        "description": "Buscar juegos por nombre",
        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "page_size": {"type": "integer", "default": 5}}, "required": ["query"]}
    },
    {
        "name": "rawg_popular",
        "description": "Lista los juegos más populares",
        "inputSchema": {"type": "object", "properties": {"page_size": {"type": "integer", "default": 5}}, "required": []}
    },
    {
        "name": "rawg_genre",
        "description": "Filtrar juegos por género",
        "inputSchema": {"type": "object", "properties": {"genre": {"type": "string"}, "page_size": {"type": "integer", "default": 5}}, "required": ["genre"]}
    },
    {
        "name": "rawg_platform",
        "description": "Filtrar juegos por plataforma",
        "inputSchema": {"type": "object", "properties": {"platform": {"type": "string"}, "page_size": {"type": "integer", "default": 5}}, "required": ["platform"]}
    },
    {
        "name": "rawg_dlcs",
        "description": "Obtener DLCs de un juego",
        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "page_size": {"type": "integer", "default": 5}}, "required": ["query"]}
    },
    {
        "name": "rawg_parent_games",
        "description": "Obtener juegos padre de DLCs y ediciones",
        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "page_size": {"type": "integer", "default": 5}}, "required": ["query"]}
    },
    {
        "name": "rawg_stores",
        "description": "Obtener enlaces a tiendas donde se vende el juego",
        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "page_size": {"type": "integer", "default": 5}}, "required": ["query"]}
    }
]

# ==============================
# LIST TOOLS ENDPOINT
# ==============================
@app.get("/list_tools")
async def list_tools():
    return TOOLS

# ==============================
# CALL TOOL ENDPOINT
# ==============================
@app.post("/call_tool")
async def call_tool(call: ToolCall) -> List[TextContent]:
    name = call.tool
    args = call.params
    print(f"Llamada a tool: {name} con args={args}")

    # --------------------------
    # RAWG TOOLS
    # --------------------------
    if name == "rawg_search":
        resp = rawg_fetch("games", {"search": args["query"], "page_size": args.get("page_size", 5)})
        games = simplify_games(resp["data"].get("results", [])) if resp["success"] else []
        return [TextContent(type="text", text=str(games))]

    elif name == "rawg_popular":
        resp = rawg_fetch("games", {"ordering": "-added", "page_size": args.get("page_size", 5)})
        games = simplify_games(resp["data"].get("results", [])) if resp["success"] else []
        return [TextContent(type="text", text=str(games))]

    elif name == "rawg_genre":
        resp = rawg_fetch("games", {"genres": args["genre"], "page_size": args.get("page_size", 5)})
        games = simplify_games(resp["data"].get("results", [])) if resp["success"] else []
        return [TextContent(type="text", text=str(games))]

    elif name == "rawg_platform":
        resp = rawg_fetch("games", {"platforms": args["platform"], "page_size": args.get("page_size", 5)})
        games = simplify_games(resp["data"].get("results", [])) if resp["success"] else []
        return [TextContent(type="text", text=str(games))]

    elif name == "rawg_dlcs":
        resp = rawg_fetch("games", {"search": args["query"], "page_size": 1})
        if not resp["success"] or not resp["data"]["results"]:
            return [TextContent(type="text", text="Juego no encontrado")]
        game_id = resp["data"]["results"][0]["id"]
        dlc_resp = rawg_fetch(f"games/{game_id}/additions", {"page_size": args.get("page_size", 5)})
        dlcs = simplify_games(dlc_resp["data"].get("results", [])) if dlc_resp["success"] else []
        return [TextContent(type="text", text=str(dlcs))]

    elif name == "rawg_parent_games":
        resp = rawg_fetch("games", {"search": args["query"], "page_size": 1})
        if not resp["success"] or not resp["data"]["results"]:
            return [TextContent(type="text", text="Juego no encontrado")]
        game_id = resp["data"]["results"][0]["id"]
        parent_resp = rawg_fetch(f"games/{game_id}/parent-games", {"page_size": args.get("page_size", 5)})
        parents = simplify_games(parent_resp["data"].get("results", [])) if parent_resp["success"] else []
        return [TextContent(type="text", text=str(parents))]

    elif name == "rawg_stores":
        resp = rawg_fetch("games", {"search": args["query"], "page_size": 1})
        if not resp["success"] or not resp["data"]["results"]:
            return [TextContent(type="text", text="Juego no encontrado")]
        game_id = resp["data"]["results"][0]["id"]
        stores_resp = rawg_fetch(f"games/{game_id}/stores")
        stores = [{"store": s["store"]["name"], "url": s["url"]} for s in stores_resp["data"].get("results", [])] if stores_resp["success"] else []
        return [TextContent(type="text", text=str(stores))]

    else:
        return [TextContent(type="text", text=f"Herramienta desconocida: {name}")]

# ==============================
# RUN SERVER
# ==============================
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
