#!/usr/bin/env python3
import os
import requests
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from dotenv import load_dotenv

# ==============================
# LOAD ENVIRONMENT VARIABLES
# ==============================
load_dotenv()
RAWG_API_KEY = os.getenv("RAWG_API_KEY")
if not RAWG_API_KEY:
    raise ValueError("Please configure RAWG_API_KEY in your .env file")

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

# ==============================
# RAWG HELPER
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
    """Devuelve solo los campos clave"""
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

def fetch_game_details(game_id: str):
    """Obtiene información completa de un juego usando /games/{id}"""
    print(f"[DEBUG] Obteniendo detalles de juego id={game_id}")
    resp = rawg_fetch(f"games/{game_id}")
    if not resp["success"]:
        print(f"[WARN] No se pudo obtener detalles de {game_id}: {resp['error']}")
        return None

    d = resp["data"]
    game_info = {
        "id": d.get("id"),
        "name": d.get("name"),
        "released": d.get("released"),
        "rating": d.get("rating"),
        "description": d.get("description_raw"),
        "platforms": [p["platform"]["name"] for p in d.get("platforms", [])],
        "genres": [g_["name"] for g_ in d.get("genres", [])],
        "tags": [t["name"] for t in d.get("tags", [])]
    }
    print(f"[DEBUG] Juego agregado: id={d.get('id')}, name={d.get('name')}")
    return game_info

# ==============================
# RAWG TOOLS ENDPOINTS
# ==============================

@app.get("/rawg/search")
async def rawg_search(query: str = Query(..., description="Nombre del juego"), page_size: int = 5):
    """Buscar juegos por nombre y devolver información completa"""
    print(f"[DEBUG] Buscando juegos con query: {query}")
    resp = rawg_fetch("games", {"search": query, "page_size": page_size})
    if not resp["success"]:
        print(f"[ERROR] Error buscando juegos: {resp['error']}")
        return {"success": False, "data": [], "error": resp["error"]}

    results = resp["data"].get("results", [])
    print(f"[DEBUG] Se encontraron {len(results)} juegos")

    games = []
    for g in results:
        game_info = fetch_game_details(str(g.get("id")))
        if game_info:
            games.append(game_info)

    return {"success": True, "data": games, "error": None}

@app.get("/rawg/dlcs")
async def rawg_dlcs(query: str = Query(..., description="Nombre del juego"), page_size: int = 5):
    """
    Buscar un juego por nombre y devolver sus DLCs, GOTY y otras ediciones.
    """
    print(f"[DEBUG] Buscando juego para DLCs con query: {query}")
    resp = rawg_fetch("games", {"search": query, "page_size": 1})  # Tomamos solo el primer resultado
    if not resp["success"]:
        print(f"[ERROR] Error buscando juego: {resp['error']}")
        return {"success": False, "data": [], "error": resp["error"]}

    results = resp["data"].get("results", [])
    if not results:
        print("[WARN] No se encontró ningún juego con ese nombre")
        return {"success": False, "data": [], "error": "No se encontró ningún juego con ese nombre"}

    game_id = results[0].get("id")
    print(f"[DEBUG] Obtenido game_id={game_id} para query={query}")

    dlc_resp = rawg_fetch(f"games/{game_id}/additions", {"page_size": page_size})
    if not dlc_resp["success"]:
        print(f"[ERROR] Error obteniendo DLCs: {dlc_resp['error']}")
        return {"success": False, "data": [], "error": dlc_resp["error"]}

    dlc_results = dlc_resp["data"].get("results", [])
    dlcs = []
    for d in dlc_results:
        dlc_info = fetch_game_details(str(d.get("id")))
        if dlc_info:
            dlcs.append(dlc_info)

    return {"success": True, "data": dlcs, "error": None}

@app.get("/rawg/parent-games")
async def rawg_parent_games(query: str = Query(..., description="Nombre del juego"), page_size: int = 5):
    """
    Buscar un juego por nombre y devolver sus juegos padres (para DLCs, GOTY, ediciones, etc.)
    """
    print(f"[DEBUG] Buscando juego para parent-games con query: {query}")
    resp = rawg_fetch("games", {"search": query, "page_size": 1})  # Tomamos solo el primer resultado
    if not resp["success"]:
        print(f"[ERROR] Error buscando juego: {resp['error']}")
        return {"success": False, "data": [], "error": resp["error"]}

    results = resp["data"].get("results", [])
    if not results:
        print("[WARN] No se encontró ningún juego con ese nombre")
        return {"success": False, "data": [], "error": "No se encontró ningún juego con ese nombre"}

    game_id = results[0].get("id")
    print(f"[DEBUG] Obtenido game_id={game_id} para query={query}")

    parent_resp = rawg_fetch(f"games/{game_id}/parent-games", {"page_size": page_size})
    if not parent_resp["success"]:
        print(f"[ERROR] Error obteniendo parent-games: {parent_resp['error']}")
        return {"success": False, "data": [], "error": parent_resp["error"]}

    parent_results = parent_resp["data"].get("results", [])
    parents = []
    for p in parent_results:
        parent_info = fetch_game_details(str(p.get("id")))
        if parent_info:
            parents.append(parent_info)

    return {"success": True, "data": parents, "error": None}

@app.get("/rawg/stores")
async def rawg_stores(query: str = Query(..., description="Nombre del juego"), page_size: int = 5, ordering: str = Query(None, description="Campo para ordenar resultados")):
    """
    Buscar un juego por nombre y devolver los links de tiendas que venden el juego
    """
    print(f"[DEBUG] Buscando juego para stores con query: {query}")
    resp = rawg_fetch("games", {"search": query, "page_size": 1})  # Tomamos solo el primer resultado
    if not resp["success"]:
        print(f"[ERROR] Error buscando juego: {resp['error']}")
        return {"success": False, "data": [], "error": resp["error"]}

    results = resp["data"].get("results", [])
    if not results:
        print("[WARN] No se encontró ningún juego con ese nombre")
        return {"success": False, "data": [], "error": "No se encontró ningún juego con ese nombre"}

    game_id = results[0].get("id")
    print(f"[DEBUG] Obtenido game_id={game_id} para query={query}")

    stores_resp = rawg_fetch(f"games/{game_id}/stores", {"page_size": page_size, "ordering": ordering})
    if not stores_resp["success"]:
        print(f"[ERROR] Error obteniendo stores: {stores_resp['error']}")
        return {"success": False, "data": [], "error": stores_resp["error"]}

    store_results = stores_resp["data"].get("results", [])
    stores = []
    for s in store_results:
        stores.append({
            "id": s.get("id"),
            "store": s.get("store", {}).get("name"),
            "url": s.get("url"),
            "games_count": s.get("games_count")
        })
        print(f"[DEBUG] Store agregado: {s.get('store', {}).get('name')} - {s.get('url')}")

    return {"success": True, "data": stores, "error": None}

@app.get("/rawg/popular")
async def rawg_popular(page_size: int = 5):
    """Juegos más populares recientes"""
    resp = rawg_fetch("games", {"ordering": "-added", "page_size": page_size})
    if not resp["success"]:
        return {"success": False, "data": [], "error": resp["error"]}
    games = simplify_games(resp["data"].get("results", []))
    return {"success": True, "data": games, "error": None}

@app.get("/rawg/genre")
async def rawg_genre(genre: str = Query(..., description="Nombre del género, ej. rpg, action"), page_size: int = 5):
    """Juegos filtrados por género"""
    resp = rawg_fetch("games", {"genres": genre.lower(), "page_size": page_size})
    if not resp["success"]:
        return {"success": False, "data": [], "error": resp["error"]}
    games = simplify_games(resp["data"].get("results", []))
    return {"success": True, "data": games, "error": None}


# ==============================
# TOOLS LIST
# ==============================
@app.get("/tools")
async def list_tools():
    return {
        "tools": [
            {
                "name": "rawg_search",
                "endpoint": "/rawg/search",
                "description": "Buscar juegos por nombre",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Nombre del juego"},
                        "page_size": {"type": "integer", "description": "Cantidad de resultados a devolver", "default": 5}
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "rawg_popular",
                "endpoint": "/rawg/popular",
                "description": "Lista los juegos más populares",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "page_size": {"type": "integer", "description": "Cantidad de resultados a devolver", "default": 5}
                    },
                    "required": []
                }
            },
            {
                "name": "rawg_genre",
                "endpoint": "/rawg/genre",
                "description": "Filtrar juegos por género",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "genre": {"type": "string", "description": "Nombre del género, ej. Action, RPG"},
                        "page_size": {"type": "integer", "description": "Cantidad de resultados a devolver", "default": 5}
                    },
                    "required": ["genre"]
                }
            },
            {
                "name": "rawg_platform",
                "endpoint": "/rawg/platform",
                "description": "Busca juegos específicos para una plataforma como pc, playstation5, xbox-one, switch y sus equivalentes",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "platform": {"type": "string", "description": "Slug o nombre de la plataforma, ej. pc, playstation5"},
                        "page_size": {"type": "integer", "description": "Cantidad de resultados a devolver", "default": 5}
                    },
                    "required": ["platform"]
                }
            },
            {
                "name": "rawg_dlcs",
                "endpoint": "/rawg/dlcs",
                "description": "Obtener DLCs, GOTY y otras ediciones de un juego",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Nombre del juego"},
                        "page_size": {"type": "integer", "description": "Cantidad de resultados a devolver", "default": 5}
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "rawg_parent_games",
                "endpoint": "/rawg/parent-games",
                "description": "Obtener juegos padre de DLCs y ediciones",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Nombre del juego"},
                        "page_size": {"type": "integer", "description": "Cantidad de resultados a devolver", "default": 5}
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "rawg_stores",
                "endpoint": "/rawg/stores",
                "description": "Obtener enlaces a tiendas donde se vende el juego",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Nombre del juego"},
                        "page_size": {"type": "integer", "description": "Cantidad de resultados a devolver", "default": 5}
                    },
                    "required": ["query"]
                }
            }
        ]
    }



# ==============================
# RUN SERVER
# ==============================
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
