#!/usr/bin/env python3
import os
import json
import sys
import requests
from datetime import datetime
from dotenv import load_dotenv

# ======================
# Configuration
# ======================
load_dotenv()
RAWG_API_KEY = os.getenv("RAWG_API_KEY")
if not RAWG_API_KEY:
    sys.stderr.write("RAWG_API_KEY not found in .env file\n")
    sys.stderr.flush()
    sys.exit(1)

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "rawg_mcp_stdio_log.json")
os.makedirs(LOG_DIR, exist_ok=True)

rawg_conversation = []

# ======================
# Logging
# ======================
def save_log():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(rawg_conversation, f, indent=2, ensure_ascii=False)

def log_message(role, content):
    rawg_conversation.append({"role": role, "content": content, "timestamp": datetime.now().isoformat()})
    save_log()

# ======================
# RAWG API Helpers
# ======================
def rawg_fetch(endpoint, params=None):
    try:
        params = params or {}
        params["key"] = RAWG_API_KEY
        url = f"https://api.rawg.io/api/{endpoint}"
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        return {"success": True, "data": response.json(), "error": None}
    except requests.exceptions.RequestException as e:
        return {"success": False, "data": None, "error": str(e)}
    except Exception as e:
        return {"success": False, "data": None, "error": f"Unexpected error: {str(e)}"}

def simplify_games(raw_games):
    simplified = []
    for game in raw_games:
        simplified.append({
            "id": game.get("id"),
            "name": game.get("name"),
            "released": game.get("released"),
            "rating": game.get("rating"),
            "metacritic": game.get("metacritic"),
            "platforms": [p["platform"]["name"] for p in game.get("platforms", [])],
            "genres": [genre["name"] for genre in game.get("genres", [])],
            "background_image": game.get("background_image")
        })
    return simplified

# ======================
# MCP Command Handlers
# ======================
def handle_rawg_search(params):
    try:
        query = params.get("query")
        page_size = params.get("page_size", 5)
        
        if not query:
            return {"error": {"code": -1, "message": "query is required"}}
        
        log_message("user", f"Searching games: {query}")
        
        response = rawg_fetch("games", {
            "search": query,
            "page_size": min(page_size, 20),
            "search_precise": "true"
        })
        
        if not response["success"]:
            return {"error": {"code": -1, "message": f"RAWG API error: {response['error']}"}}
        
        games = simplify_games(response["data"].get("results", []))
        result_msg = f"Found {len(games)} games for '{query}'"
        
        log_message("assistant", result_msg)
        
        return {"result": {
            "success": True,
            "message": result_msg,
            "query": query,
            "count": len(games),
            "games": games
        }}
    except Exception as e:
        error_msg = f"Error searching games: {str(e)}"
        log_message("assistant", error_msg)
        return {"error": {"code": -1, "message": error_msg}}

def handle_rawg_popular(params):
    try:
        page_size = params.get("page_size", 10)
        
        log_message("user", "Getting popular games")
        
        response = rawg_fetch("games", {
            "ordering": "-added",
            "page_size": min(page_size, 20)
        })
        
        if not response["success"]:
            return {"error": {"code": -1, "message": f"RAWG API error: {response['error']}"}}
        
        games = simplify_games(response["data"].get("results", []))
        result_msg = f"Retrieved {len(games)} popular games"
        
        log_message("assistant", result_msg)
        
        return {"result": {
            "success": True,
            "message": result_msg,
            "count": len(games),
            "games": games
        }}
    except Exception as e:
        error_msg = f"Error getting popular games: {str(e)}"
        log_message("assistant", error_msg)
        return {"error": {"code": -1, "message": error_msg}}

def handle_rawg_by_genre(params):
    try:
        genre = params.get("genre")
        page_size = params.get("page_size", 10)
        
        if not genre:
            return {"error": {"code": -1, "message": "genre is required"}}
        
        log_message("user", f"Searching games by genre: {genre}")
        
        response = rawg_fetch("games", {
            "genres": genre.lower(),
            "page_size": min(page_size, 20),
            "ordering": "-rating"
        })
        
        if not response["success"]:
            return {"error": {"code": -1, "message": f"RAWG API error: {response['error']}"}}
        
        games = simplify_games(response["data"].get("results", []))
        result_msg = f"Found {len(games)} games in '{genre}' genre"
        
        log_message("assistant", result_msg)
        
        return {"result": {
            "success": True,
            "message": result_msg,
            "genre": genre,
            "count": len(games),
            "games": games
        }}
    except Exception as e:
        error_msg = f"Error getting games by genre: {str(e)}"
        log_message("assistant", error_msg)
        return {"error": {"code": -1, "message": error_msg}}

def handle_rawg_game_details(params):
    try:
        game_name = params.get("game_name")
        
        if not game_name:
            return {"error": {"code": -1, "message": "game_name is required"}}
        
        log_message("user", f"Getting details for game: {game_name}")
        
        # Search for the game first
        search_response = rawg_fetch("games", {
            "search": game_name,
            "page_size": 1,
            "search_precise": "true"
        })
        
        if not search_response["success"] or not search_response["data"].get("results"):
            return {"error": {"code": -1, "message": f"Game '{game_name}' not found"}}
        
        game_id = search_response["data"]["results"][0]["id"]
        
        # Get detailed info
        details_response = rawg_fetch(f"games/{game_id}")
        
        if not details_response["success"]:
            return {"error": {"code": -1, "message": f"Error getting details: {details_response['error']}"}}
        
        game_data = details_response["data"]
        
        game_details = {
            "id": game_data.get("id"),
            "name": game_data.get("name"),
            "description": game_data.get("description_raw", "")[:500] + "..." if game_data.get("description_raw", "") else "No description",
            "released": game_data.get("released"),
            "rating": game_data.get("rating"),
            "metacritic": game_data.get("metacritic"),
            "playtime": game_data.get("playtime", 0),
            "developers": [dev["name"] for dev in game_data.get("developers", [])],
            "publishers": [pub["name"] for pub in game_data.get("publishers", [])],
            "genres": [genre["name"] for genre in game_data.get("genres", [])],
            "platforms": [p["platform"]["name"] for p in game_data.get("platforms", [])],
            "website": game_data.get("website", ""),
            "background_image": game_data.get("background_image")
        }
        
        result_msg = f"Details retrieved for '{game_name}'"
        log_message("assistant", result_msg)
        
        return {"result": {
            "success": True,
            "message": result_msg,
            "game": game_details
        }}
    except Exception as e:
        error_msg = f"Error getting game details: {str(e)}"
        log_message("assistant", error_msg)
        return {"error": {"code": -1, "message": error_msg}}

def handle_list_tools(params):
    tools = [
        {
            "type": "function",
            "function": {
                "name": "rawg_search",
                "description": "Search for games by name in RAWG database",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Game name to search for"
                        },
                        "page_size": {
                            "type": "integer",
                            "description": "Number of results (max 20)",
                            "default": 5,
                            "minimum": 1,
                            "maximum": 20
                        }
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "rawg_popular",
                "description": "Get popular games list",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "page_size": {
                            "type": "integer",
                            "description": "Number of games to get (max 20)",
                            "default": 10,
                            "minimum": 1,
                            "maximum": 20
                        }
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "rawg_by_genre",
                "description": "Search games filtered by genre",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "genre": {
                            "type": "string",
                            "description": "Game genre (e.g. action, rpg, strategy)"
                        },
                        "page_size": {
                            "type": "integer",
                            "description": "Number of games to get (max 20)",
                            "default": 10,
                            "minimum": 1,
                            "maximum": 20
                        }
                    },
                    "required": ["genre"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "rawg_game_details",
                "description": "Get detailed information about a specific game",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "game_name": {
                            "type": "string",
                            "description": "Exact game name"
                        }
                    },
                    "required": ["game_name"]
                }
            }
        }
    ]
    
    return {"result": {"status": "ok", "tools": tools}}

# ======================
# Main MCP loop
# ======================
def main():
    # Method handlers
    handlers = {
        "rawg_search": handle_rawg_search,
        "rawg_popular": handle_rawg_popular,
        "rawg_by_genre": handle_rawg_by_genre,
        "rawg_game_details": handle_rawg_game_details,
        "list_tools": handle_list_tools
    }
    
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            
            try:
                request = json.loads(line)
                
                if "method" not in request:
                    response = {
                        "jsonrpc": "2.0",
                        "id": request.get("id"),
                        "error": {"code": -32600, "message": "Invalid Request"}
                    }
                else:
                    method = request["method"]
                    params = request.get("params", {})
                    
                    if method in handlers:
                        result = handlers[method](params)
                        response = {
                            "jsonrpc": "2.0",
                            "id": request.get("id"),
                            **result
                        }
                    else:
                        response = {
                            "jsonrpc": "2.0",
                            "id": request.get("id"),
                            "error": {"code": -32601, "message": f"Method not found: {method}"}
                        }
                
                print(json.dumps(response))
                sys.stdout.flush()
                
            except json.JSONDecodeError as e:
                response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {str(e)}"}
                }
                print(json.dumps(response))
                sys.stdout.flush()
            except Exception as e:
                response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id") if 'request' in locals() else None,
                    "error": {"code": -32000, "message": f"Server error: {str(e)}"}
                }
                print(json.dumps(response))
                sys.stdout.flush()
    
    except KeyboardInterrupt:
        pass
    except Exception as e:
        sys.stderr.write(f"Fatal error: {str(e)}\n")
        sys.stderr.flush()

if __name__ == "__main__":
    main()