#!/usr/bin/env python3
"""
Chatbot usando Postman MCP Server
- Conexión con MCP Server local
- Mantiene contexto de conversación
- Log de interacciones
"""

import json
import logging
from datetime import datetime
from typing import List, Dict, Optional
import os
import requests
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('chatbot_interactions.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ======================
# CLASES DE CHAT
# ======================
class ChatSession:
    """Maneja una sesión de chat con contexto persistente"""
    def __init__(self):
        self.messages: List[Dict[str, str]] = []
        self.session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
    def add_message(self, role: str, content: str):
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        self.messages.append(message)
        
    def get_conversation_history(self) -> List[Dict[str, str]]:
        return [{"role": msg["role"], "content": msg["content"]} 
                for msg in self.messages]
    
    def save_session(self, filename: Optional[str] = None):
        if not filename:
            filename = f"session_{self.session_id}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump({
                "session_id": self.session_id,
                "messages": self.messages,
                "created_at": datetime.now().isoformat()
            }, f, indent=2, ensure_ascii=False)
        logger.info(f"Sesión guardada en {filename}")

class MCPLogger:
    """Sistema de logging para interacciones MCP"""
    def __init__(self):
        self.interactions: List[Dict] = []
    
    def log_mcp_interaction(self, server_name: str, tool_name: str, 
                            request_data: Dict, response_data: Dict, 
                            success: bool = True, error: Optional[str] = None):
        interaction = {
            "timestamp": datetime.now().isoformat(),
            "server_name": server_name,
            "tool_name": tool_name,
            "request": request_data,
            "response": response_data,
            "success": success,
            "error": error
        }
        self.interactions.append(interaction)
        logger.info(f"MCP Interaction - Server: {server_name}, Tool: {tool_name}, Success: {success}")
        if error:
            logger.error(f"MCP Error: {error}")
    
    def show_recent_interactions(self, count: int = 5):
        recent = self.interactions[-count:]
        print("\n" + "="*60)
        print(f"ÚLTIMAS {len(recent)} INTERACCIONES MCP")
        print("="*60)
        for i, interaction in enumerate(recent, 1):
            status = "✅ ÉXITO" if interaction["success"] else "❌ ERROR"
            print(f"\n{i}. {interaction['timestamp']}")
            print(f"   Servidor: {interaction['server_name']}")
            print(f"   Herramienta: {interaction['tool_name']}")
            print(f"   Estado: {status}")
            if interaction["error"]:
                print(f"   Error: {interaction['error']}")
            if interaction["response"]:
                response_preview = str(interaction["response"])[:100] + "..." if len(str(interaction["response"])) > 100 else str(interaction["response"])
                print(f"   Respuesta: {response_preview}")
        print("="*60)

# ======================
# CHATBOT
# ======================
class BasicChatbot:
    """Chatbot usando MCP Server"""
    def __init__(self):
        self.api_key = os.getenv("POSTMAN_API_KEY")
        self.server_url = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8000")
        
        if not self.api_key:
            raise ValueError("Se requiere POSTMAN_API_KEY. Configura tu .env")
        
        self.session = ChatSession()
        self.mcp_logger = MCPLogger()
        self.system_prompt = "Eres un asistente conversacional inteligente, útil y amigable. Mantén el contexto de la conversación y responde en español."
    
    def send_to_mcp(self, endpoint: str, payload: dict) -> dict:
        """Enviar petición al MCP Server usando Postman API Key"""
        url = f"{self.server_url}/{endpoint}"
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }
        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            self.mcp_logger.log_mcp_interaction(
                server_name=self.server_url,
                tool_name=endpoint,
                request_data=payload,
                response_data=data,
                success=True
            )
            return data
        except Exception as e:
            self.mcp_logger.log_mcp_interaction(
                server_name=self.server_url,
                tool_name=endpoint,
                request_data=payload,
                response_data={},
                success=False,
                error=str(e)
            )
            return {"error": str(e)}
    
    def chat(self, user_message: str) -> str:
        """Procesar mensaje del usuario"""
        self.session.add_message("user", user_message)
        payload = {
            "messages": self.session.get_conversation_history(),
            "system_prompt": self.system_prompt
        }
        result = self.send_to_mcp("chat", payload)
        assistant_response = result.get("response", "Lo siento, no hubo respuesta del MCP server.")
        self.session.add_message("assistant", assistant_response)
        return assistant_response
    
    def show_conversation_summary(self):
        print("\n" + "="*50)
        print("RESUMEN DE LA CONVERSACIÓN")
        print("="*50)
        print(f"Sesión: {self.session.session_id}")
        print(f"Total mensajes: {len(self.session.messages)}")
        for i, msg in enumerate(self.session.messages[-6:], 1):
            role_emoji = "👤" if msg["role"] == "user" else "🤖"
            role_name = "Usuario" if msg["role"] == "user" else "Asistente"
            content_preview = msg["content"][:100] + "..." if len(msg["content"]) > 100 else msg["content"]
            print(f"\n{i}. {role_emoji} {role_name} ({msg['timestamp']}): {content_preview}")
        print("="*50)
    
    def save_current_session(self):
        self.session.save_session()
    
    def run_console_interface(self):
        print("🤖 CHATBOT CON POSTMAN MCP SERVER")
        print("="*40)
        print("Comandos: /resumen | /log | /guardar | /salir")
        try:
            while True:
                user_input = input("👤 Tú: ").strip()
                if user_input.lower() == '/salir':
                    print("\n👋 ¡Hasta luego!")
                    break
                elif user_input.lower() == '/resumen':
                    self.show_conversation_summary()
                    continue
                elif user_input.lower() == '/log':
                    self.mcp_logger.show_recent_interactions()
                    continue
                elif user_input.lower() == '/guardar':
                    self.save_current_session()
                    continue
                elif not user_input:
                    print("Escribe un mensaje o un comando.")
                    continue
                print("🤖 Asistente: ", end="", flush=True)
                response = self.chat(user_input)
                print(response + "\n")
        except KeyboardInterrupt:
            print("\n\n👋 Chat interrumpido.")
        finally:
            self.save_current_session()
            print("💾 Sesión guardada automáticamente.")

# ======================
# MAIN
# ======================
def main():
    try:
        chatbot = BasicChatbot()
        chatbot.run_console_interface()
    except Exception as e:
        print(f"❌ Error al iniciar chatbot: {e}")

if __name__ == "__main__":
    main()
