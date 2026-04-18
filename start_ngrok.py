import subprocess
import time
import requests
import os
import sys

# Configuration
BACKEND_PORT = 8001
FRONTEND_ENV_PATH = "../finova-front/finova-front/.env.local"
BACKEND_ENV_PATH = ".env"

def update_env_file(file_path, key, value):
    if not os.path.exists(file_path):
        with open(file_path, "w") as f:
            f.write(f"{key}={value}\n")
        return

    with open(file_path, "r") as f:
        lines = f.readlines()

    found = False
    with open(file_path, "w") as f:
        for line in lines:
            if line.startswith(f"{key}="):
                f.write(f"{key}={value}\n")
                found = True
            else:
                f.write(line)
        if not found:
            f.write(f"{key}={value}\n")

def start_ngrok():
    print(f"--- Starting ngrok on port {BACKEND_PORT} ---")
    
    # Run ngrok in the background
    try:
        ngrok_proc = subprocess.Popen(["ngrok", "http", str(BACKEND_PORT)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        print("Error: 'ngrok' command not found. Please install ngrok and add it to your PATH.")
        sys.exit(1)

    # Wait for ngrok to initialize
    time.sleep(3)

    # Get the public URL from ngrok local API
    try:
        response = requests.get("http://127.0.0.1:4040/api/tunnels")
        data = response.json()
        public_url = data['tunnels'][0]['public_url']
        print(f"Success! ngrok is live at: {public_url}")
    except Exception as e:
        print(f"Error: Could not retrieve ngrok URL. {e}")
        ngrok_proc.terminate()
        sys.exit(1)

    # Update Frontend .env
    print(f"Updating Frontend environment: {FRONTEND_ENV_PATH}")
    update_env_file(FRONTEND_ENV_PATH, "NEXT_PUBLIC_API_URL", f"{public_url}/api")
    
    ws_url = public_url.replace("https://", "wss://").replace("http://", "ws://")
    update_env_file(FRONTEND_ENV_PATH, "NEXT_PUBLIC_WS_URL", f"{ws_url}/ws")

    # Update Backend .env
    print(f"Updating Backend environment: {BACKEND_ENV_PATH}")
    update_env_file(BACKEND_ENV_PATH, "NGROK_URL", public_url)

    print("\n--- Done! ---")
    print("1. Please restart your Django server (python manage.py runserver 0.0.0.0:8001)")
    print("2. Please restart your Frontend dev server if needed.")
    print("\nKeep this terminal open to keep the ngrok tunnel alive.")

    try:
        # Keep the script running to track the process
        ngrok_proc.wait()
    except KeyboardInterrupt:
        print("\nShutting down ngrok...")
        ngrok_proc.terminate()

if __name__ == "__main__":
    start_ngrok()
