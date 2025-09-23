from fastmcp import FastMCP
import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional

# Initialize FastMCP server
mcp = FastMCP("rawg-gaming-mcp")

# Configuration
load_dotenv()
RAWG_API_KEY = os.getenv("RAWG_API_KEY")

if not RAWG_API_KEY:
    print("Warning: RAWG_API_KEY not found in .env file")
    print("Please add RAWG_API_KEY=your_api_key to your .env file")

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "rawg_mcp_log.json")
os.makedirs(LOG_DIR, exist_ok=True)

rawg_conversation = []

# Logging functions
def save_log():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(rawg_conversation, f, indent=2, ensure_ascii=False)

def log_message(role: str, content: str):
    rawg_conversation.append({
        "role": role, 
        "content": content, 
        "timestamp": datetime.now().isoformat()
    })
    save_log()

# RAWG API helper
def rawg_fetch(endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
    """Make a request to RAWG API"""
    try:
        if not RAWG_API_KEY:
            return {"success": False, "data": None, "error": "RAWG_API_KEY not configured"}
        
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

def simplify_games(raw_games: List[Dict]) -> List[Dict]:
    """Simplify game data for better readability"""
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

def format_games_list(games: List[Dict], title: str) -> str:
    """Format games list for display"""
    if not games:
        return f"{title}\n\nNo games found."
    
    result = f"{title}\n\n"
    
    for i, game in enumerate(games, 1):
        result += f"{i}. **{game['name']}**\n"
        
        if game.get('released'):
            result += f"   Released: {game['released']}\n"
        
        if game.get('rating'):
            result += f"   Rating: {game['rating']}/5.0\n"
        
        if game.get('metacritic'):
            result += f"   Metacritic: {game['metacritic']}/100\n"
        
        if game.get('platforms'):
            platforms_str = ", ".join(game['platforms'][:3])
            if len(game['platforms']) > 3:
                platforms_str += f" (+{len(game['platforms'])-3} more)"
            result += f"   Platforms: {platforms_str}\n"
        
        if game.get('genres'):
            result += f"   Genres: {', '.join(game['genres'])}\n"
        
        result += "\n"
    
    return result

@mcp.tool()
def search_games(query: str, page_size: int = 5) -> str:
    """
    Search for games by name in RAWG database
    
    Args:
        query: Game name to search for
        page_size: Number of results (max 20, default 5)
    
    Returns:
        Formatted list of matching games
    """
    try:
        if not query:
            return "Error: query is required"
        
        page_size = min(max(page_size, 1), 20)  # Clamp between 1 and 20
        
        log_message("user", f"Searching games: {query}")
        
        response = rawg_fetch("games", {
            "search": query,
            "page_size": page_size,
            "search_precise": "true"
        })
        
        if not response["success"]:
            return f"RAWG API error: {response['error']}"
        
        games = simplify_games(response["data"].get("results", []))
        
        result = format_games_list(games, f"Search results for '{query}' ({len(games)} games)")
        
        log_message("assistant", f"Found {len(games)} games for '{query}'")
        return result
    except Exception as e:
        error_msg = f"Error searching games: {str(e)}"
        log_message("assistant", error_msg)
        return error_msg

@mcp.tool()
def get_popular_games(page_size: int = 10) -> str:
    """
    Get popular games list
    
    Args:
        page_size: Number of games to get (max 20, default 10)
    
    Returns:
        Formatted list of popular games
    """
    try:
        page_size = min(max(page_size, 1), 20)  # Clamp between 1 and 20
        
        log_message("user", "Getting popular games")
        
        response = rawg_fetch("games", {
            "ordering": "-added",
            "page_size": page_size
        })
        
        if not response["success"]:
            return f"RAWG API error: {response['error']}"
        
        games = simplify_games(response["data"].get("results", []))
        
        result = format_games_list(games, f"Popular Games ({len(games)} games)")
        
        log_message("assistant", f"Retrieved {len(games)} popular games")
        return result
    except Exception as e:
        error_msg = f"Error getting popular games: {str(e)}"
        log_message("assistant", error_msg)
        return error_msg

@mcp.tool()
def get_games_by_genre(genre: str, page_size: int = 10) -> str:
    """
    Search games filtered by genre
    
    Args:
        genre: Game genre (e.g. action, rpg, strategy, adventure, shooter)
        page_size: Number of games to get (max 20, default 10)
    
    Returns:
        Formatted list of games in the specified genre
    """
    try:
        if not genre:
            return "Error: genre is required"
        
        page_size = min(max(page_size, 1), 20)  # Clamp between 1 and 20
        
        log_message("user", f"Searching games by genre: {genre}")
        
        response = rawg_fetch("games", {
            "genres": genre.lower(),
            "page_size": page_size,
            "ordering": "-rating"
        })
        
        if not response["success"]:
            return f"RAWG API error: {response['error']}"
        
        games = simplify_games(response["data"].get("results", []))
        
        result = format_games_list(games, f"Top {genre.title()} Games ({len(games)} games)")
        
        log_message("assistant", f"Found {len(games)} games in '{genre}' genre")
        return result
    except Exception as e:
        error_msg = f"Error getting games by genre: {str(e)}"
        log_message("assistant", error_msg)
        return error_msg

@mcp.tool()
def get_game_details(game_name: str) -> str:
    """
    Get detailed information about a specific game
    
    Args:
        game_name: Exact or partial game name
    
    Returns:
        Detailed game information including description, platforms, developers, etc.
    """
    try:
        if not game_name:
            return "Error: game_name is required"
        
        log_message("user", f"Getting details for game: {game_name}")
        
        # Search for the game first
        search_response = rawg_fetch("games", {
            "search": game_name,
            "page_size": 1,
            "search_precise": "true"
        })
        
        if not search_response["success"] or not search_response["data"].get("results"):
            return f"Game '{game_name}' not found in RAWG database"
        
        game_id = search_response["data"]["results"][0]["id"]
        
        # Get detailed info
        details_response = rawg_fetch(f"games/{game_id}")
        
        if not details_response["success"]:
            return f"Error getting details: {details_response['error']}"
        
        game_data = details_response["data"]
        
        # Format detailed information
        result = f"**{game_data.get('name', 'Unknown')}** - Game Details\n\n"
        
        # Basic info
        if game_data.get('released'):
            result += f"**Released:** {game_data['released']}\n"
        
        if game_data.get('rating'):
            result += f"**Rating:** {game_data['rating']}/5.0\n"
        
        if game_data.get('metacritic'):
            result += f"**Metacritic Score:** {game_data['metacritic']}/100\n"
        
        if game_data.get('playtime'):
            result += f"**Average Playtime:** {game_data['playtime']} hours\n"
        
        # Developers and Publishers
        developers = [dev["name"] for dev in game_data.get("developers", [])]
        if developers:
            result += f"**Developers:** {', '.join(developers)}\n"
        
        publishers = [pub["name"] for pub in game_data.get("publishers", [])]
        if publishers:
            result += f"**Publishers:** {', '.join(publishers)}\n"
        
        # Genres
        genres = [genre["name"] for genre in game_data.get("genres", [])]
        if genres:
            result += f"**Genres:** {', '.join(genres)}\n"
        
        # Platforms
        platforms = [p["platform"]["name"] for p in game_data.get("platforms", [])]
        if platforms:
            result += f"**Platforms:** {', '.join(platforms)}\n"
        
        # Website
        if game_data.get('website'):
            result += f"**Website:** {game_data['website']}\n"
        
        # Description
        description = game_data.get('description_raw', '').strip()
        if description:
            # Limit description length
            if len(description) > 500:
                description = description[:500] + "..."
            result += f"\n**Description:**\n{description}\n"
        else:
            result += f"\n**Description:** No description available\n"
        
        log_message("assistant", f"Retrieved details for '{game_name}'")
        return result
    except Exception as e:
        error_msg = f"Error getting game details: {str(e)}"
        log_message("assistant", error_msg)
        return error_msg

@mcp.tool()
def get_trending_games(page_size: int = 10) -> str:
    """
    Get currently trending games
    
    Args:
        page_size: Number of games to get (max 20, default 10)
    
    Returns:
        Formatted list of trending games
    """
    try:
        page_size = min(max(page_size, 1), 20)  # Clamp between 1 and 20
        
        log_message("user", "Getting trending games")
        
        # Get games ordered by recent popularity
        response = rawg_fetch("games", {
            "dates": "2023-01-01,2024-12-31",  # Recent games
            "ordering": "-metacritic",
            "page_size": page_size
        })
        
        if not response["success"]:
            return f"RAWG API error: {response['error']}"
        
        games = simplify_games(response["data"].get("results", []))
        
        result = format_games_list(games, f"Trending Games ({len(games)} games)")
        
        log_message("assistant", f"Retrieved {len(games)} trending games")
        return result
    except Exception as e:
        error_msg = f"Error getting trending games: {str(e)}"
        log_message("assistant", error_msg)
        return error_msg

@mcp.tool()
def get_games_by_platform(platform: str, page_size: int = 10) -> str:
    """
    Get games filtered by platform
    
    Args:
        platform: Platform name (e.g. pc, playstation-5, xbox-one, nintendo-switch)
        page_size: Number of games to get (max 20, default 10)
    
    Returns:
        Formatted list of games for the specified platform
    """
    try:
        if not platform:
            return "Error: platform is required"
        
        page_size = min(max(page_size, 1), 20)  # Clamp between 1 and 20
        
        log_message("user", f"Searching games by platform: {platform}")
        
        response = rawg_fetch("games", {
            "platforms": platform.lower(),
            "page_size": page_size,
            "ordering": "-rating"
        })
        
        if not response["success"]:
            return f"RAWG API error: {response['error']}"
        
        games = simplify_games(response["data"].get("results", []))
        
        result = format_games_list(games, f"Top Games for {platform.title()} ({len(games)} games)")
        
        log_message("assistant", f"Found {len(games)} games for platform '{platform}'")
        return result
    except Exception as e:
        error_msg = f"Error getting games by platform: {str(e)}"
        log_message("assistant", error_msg)
        return error_msg

# Run the server
if __name__ == "__main__":
    mcp.run()