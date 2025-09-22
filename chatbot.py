import os
import json
import uuid
from datetime import datetime
from dotenv import load_dotenv
import requests

# ======================
# Configuración inicial
# ======================
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("❌ No se encontró OPENAI_API_KEY en el .env")

OPENAI_URL = "https://api.openai.com/v1/chat/completions"

HEADERS = {
    "Authorization": f"Bearer {OPENAI_API_KEY}",
    "Content-Type": "application/json"
}

# MCP Servers
MCP_GIT_URL = "http://localhost:8002/"

# ======================
# Variables de sesión
# ======================
messages = [{"role": "system", "content": """Eres un asistente experto en Git y desarrollo de software. 
Tienes acceso a herramientas para manejar repositorios Git locales.

Puedes:
- Crear repositorios nuevos
- Agregar archivos con contenido específico
- Realizar commits con mensajes descriptivos
- Listar archivos y ver el estado del repositorio

Cuando el usuario te pida hacer algo relacionado con Git, usa las herramientas disponibles para ayudarle.
Sé descriptivo sobre lo que haces y confirma cada acción realizada."""}]

log_interacciones = []

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
session_file = os.path.join(LOG_DIR, f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")

# ======================
# Funciones MCP
# ======================
def llamar_mcp(server_url, metodo, params):
    """
    Envía una request JSON-RPC a un servidor MCP y devuelve la respuesta.
    """
    request_jsonrpc = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": metodo,
        "params": params
    }
    try:
        resp = requests.post(server_url, json=request_jsonrpc, timeout=10)
        return resp.json()
    except Exception as e:
        return {"error": {"code": -1, "message": str(e)}}

def obtener_tools_del_servidor(server_url):
    """
    Obtiene la lista de herramientas disponibles en un MCP server.
    """
    request_jsonrpc = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "list_tools",
        "params": {}
    }
    try:
        resp = requests.post(server_url, json=request_jsonrpc, timeout=10).json()
        if "result" in resp and "tools" in resp["result"]:
            return resp["result"]["tools"]
    except Exception as e:
        print(f"⚠️ Error obteniendo tools del servidor: {e}")
    return []

def ejecutar_tool_call(tool_call):
    """
    Ejecuta una llamada a herramienta MCP.
    """
    function_name = tool_call["function"]["name"]
    arguments = json.loads(tool_call["function"]["arguments"])
    
    print(f"🔧 Ejecutando: {function_name} con argumentos: {arguments}")
    
    # Mapear nombre de función a método MCP
    mcp_response = llamar_mcp(MCP_GIT_URL, function_name, arguments)
    
    if "result" in mcp_response:
        result = mcp_response["result"]
        if isinstance(result, dict) and "message" in result:
            return result["message"]
        return str(result)
    elif "error" in mcp_response:
        return f"❌ Error: {mcp_response['error']['message']}"
    
    return "✅ Operación completada"

# ======================
# Funciones LLM
# ======================
def enviar_a_openai(messages_context, tools=None):
    """
    Envía mensajes a OpenAI y maneja tool calls.
    """
    payload = {
        "model": "gpt-4o-mini",
        "messages": messages_context,
        "max_tokens": 1000,
        "temperature": 0.7
    }
    
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    
    try:
        response = requests.post(OPENAI_URL, headers=HEADERS, json=payload, timeout=30)
        
        if response.status_code != 200:
            return f"⚠️ Error HTTP {response.status_code}: {response.text}"
        
        data = response.json()
        message = data["choices"][0]["message"]
        
        # Si hay tool calls, ejecutarlos
        if "tool_calls" in message and message["tool_calls"]:
            # Agregar el mensaje del asistente (con tool calls) al contexto
            messages_context.append(message)
            
            # Ejecutar cada tool call
            for tool_call in message["tool_calls"]:
                tool_result = ejecutar_tool_call(tool_call)
                
                # Agregar el resultado de la tool al contexto
                tool_message = {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": tool_result
                }
                messages_context.append(tool_message)
            
            # Obtener respuesta final del asistente
            final_payload = {
                "model": "gpt-4o-mini",
                "messages": messages_context,
                "max_tokens": 1000,
                "temperature": 0.7
            }
            
            final_response = requests.post(OPENAI_URL, headers=HEADERS, json=final_payload, timeout=30)
            final_data = final_response.json()
            return final_data["choices"][0]["message"]["content"]
        
        return message["content"]
        
    except Exception as e:
        return f"❌ Error de conexión: {str(e)}"

# ======================
# Funciones de log
# ======================
def guardar_log(usuario, bot, tools_used=None):
    entrada = {
        "timestamp": datetime.now().isoformat(),
        "usuario": usuario,
        "bot": bot,
        "tools_used": tools_used or []
    }
    log_interacciones.append(entrada)
    
    try:
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(log_interacciones, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ Error guardando log: {e}")

def mostrar_log():
    print("\n📜 Log de interacciones:")
    for i, entry in enumerate(log_interacciones, 1):
        print(f"\n[{i}] {entry['timestamp']}")
        print(f"👤 Usuario: {entry['usuario']}")
        print(f"🤖 Bot: {entry['bot'][:100]}{'...' if len(entry['bot']) > 100 else ''}")
        if entry.get('tools_used'):
            print(f"🔧 Tools usadas: {', '.join(entry['tools_used'])}")

def test_mcp_connection():
    """
    Prueba la conexión con el servidor MCP.
    """
    print("🔍 Probando conexión con MCP Git server...")
    try:
        resp = requests.get(MCP_GIT_URL + "health", timeout=5)
        if resp.status_code == 200:
            print("✅ Conexión con MCP Git server OK")
            return True
    except Exception as e:
        print(f"❌ Error conectando con MCP server: {e}")
        print("💡 Asegúrate de que el servidor Git MCP esté corriendo en puerto 8002")
        return False
    return False

# ======================
# Entrada principal
# ======================
def main():
    print("🚀 Cliente MCP Chatbot con herramientas Git")
    print("💬 Comandos disponibles:")
    print("   - 'salir': Terminar sesión")
    print("   - 'log': Ver historial de interacciones")
    print("   - 'test': Probar conexión MCP")
    print()
    
    # Verificar conexión inicial
    if not test_mcp_connection():
        print("⚠️ Continuando sin conexión MCP (funcionalidad limitada)")
    
    # Obtener tools dinámicamente del MCP Git
    git_tools = obtener_tools_del_servidor(MCP_GIT_URL)
    
    if git_tools:
        print(f"🔧 Herramientas Git cargadas: {len(git_tools)}")
        for tool in git_tools:
            print(f"   - {tool['function']['name']}: {tool['function']['description']}")
        print()
    else:
        print("⚠️ No se pudieron cargar las herramientas Git")
        print()

    while True:
        try:
            user_input = input("👤 Tú: ").strip()
            
            if not user_input:
                continue
                
            if user_input.lower() == "salir":
                print(f"📝 Log guardado en: {session_file}")
                break
                
            if user_input.lower() == "log":
                mostrar_log()
                continue
                
            if user_input.lower() == "test":
                test_mcp_connection()
                continue

            # Añadir mensaje del usuario al contexto
            messages.append({"role": "user", "content": user_input})

            # Obtener respuesta del LLM (con manejo de tool calls)
            respuesta = enviar_a_openai(messages.copy(), tools=git_tools)

            # Añadir respuesta al contexto
            messages.append({"role": "assistant", "content": respuesta})

            # Guardar log
            guardar_log(user_input, respuesta)

            print(f"🤖 Bot: {respuesta}")
            print()

        except KeyboardInterrupt:
            print("\n\n👋 Sesión interrumpida por el usuario")
            print(f"📝 Log guardado en: {session_file}")
            break
        except Exception as e:
            print(f"❌ Error inesperado: {e}")
            continue

if __name__ == "__main__":
    main()