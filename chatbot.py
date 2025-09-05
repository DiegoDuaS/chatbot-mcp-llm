#!/usr/bin/env python3
import requests

SERVER_URL = "http://127.0.0.1:8000/chat"

def main():
    print("🤖 Chatbot de videojuegos (con RAWG + OpenAI)")
    print("Comandos: /salir | /resumen")
    conversation = []

    while True:
        user_input = input("👤 Tú: ").strip()
        if user_input.lower() == "/salir":
            print("👋 Hasta luego!")
            break
        elif user_input.lower() == "/resumen":
            if not conversation:
                print("No hay mensajes todavía.")
                continue
            print("\nÚltimos 5 mensajes:")
            for msg in conversation[-5:]:
                role = "👤 Tú" if msg["role"] == "user" else "🤖 Asistente"
                print(f"{role}: {msg['content']}\n")
            continue
        elif not user_input:
            continue

        # Guardar mensaje del usuario primero
        conversation.append({"role": "user", "content": user_input})

        try:
            print("🤔 Pensando...")
            resp = requests.post(SERVER_URL, json={"message": user_input})
            resp.raise_for_status()
            data = resp.json()
            assistant_msg = data.get("response", "No hubo respuesta del servidor.")
        except Exception as e:
            assistant_msg = f"Error conectando con servidor: {str(e)}"

        # Guardar respuesta del asistente
        conversation.append({"role": "assistant", "content": assistant_msg})

        print(f"🤖 {assistant_msg}\n")

if __name__ == "__main__":
    main()
