#!/usr/bin/env python3
import requests

SERVER_URL = "http://127.0.0.1:8001/git"

def main():
    print("🤖Chatbot")
    print("Commands: /exit | /summary")
    conversation = []

    while True:
        user_input = input("👤 You: ").strip()
        if user_input.lower() == "/exit":
            print("👋 Goodbye!")
            break
        elif user_input.lower() == "/summary":
            if not conversation:
                print("No messages yet.")
                continue
            print("\nLast 5 messages:")
            for msg in conversation[-5:]:
                role = "👤 You" if msg["role"] == "user" else "🤖 Assistant"
                print(f"{role}: {msg['content']}\n")
            continue
        elif not user_input:
            continue

        # Save user message first
        conversation.append({"role": "user", "content": user_input})

        try:
            print("🤔 Thinking...")
            resp = requests.post(SERVER_URL, json={"message": user_input})
            resp.raise_for_status()
            data = resp.json()
            assistant_msg = data.get("response", "No response from the server.")
        except Exception as e:
            assistant_msg = f"Error connecting to server: {str(e)}"

        # Save assistant's response
        conversation.append({"role": "assistant", "content": assistant_msg})

        print(f"🤖 {assistant_msg}\n")

if __name__ == "__main__":
    main()
