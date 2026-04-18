import os
import sys
import time
from pyngrok import ngrok, conf
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Configuration
BACKEND_PORT = 8001
FRONTEND_ENV_PATH = "../finova-front/finova-front/.env.local"
BACKEND_ENV_PATH = ".env"

def update_env_file(file_path, key, value):
    if not os.path.exists(file_path):
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
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
    print(f"--- Starting pyngrok on port {BACKEND_PORT} ---")
    
    # Set authtoken if available
    authtoken = os.getenv("NGROK_AUTHTOKEN")
    if authtoken:
        print("Using authtoken from .env")
        ngrok.set_auth_token(authtoken)
    else:
        print("WARNING: No NGROK_AUTHTOKEN found in .env. Tunnels will expire in 2 hours.")
        print("Get your token at: https://dashboard.ngrok.com/get-started/your-authtoken")

    try:
        # Start ngrok tunnel
        # We explicitly use 127.0.0.1 to avoid IPv6 connection issues on Windows
        public_url = ngrok.connect(f"127.0.0.1:{BACKEND_PORT}").public_url
        print(f"Success! ngrok is live at: {public_url}")
        
    except Exception as e:
        print(f"Error: Could not start ngrok. {e}")
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
    print(f"1. RUN: python manage.py runserver 0.0.0.0:{BACKEND_PORT}")
    print("2. RESTART: Your Frontend dev server to pick up new URLs.")
    print("\nKeep this script running to keep the tunnel alive (Ctrl+C to stop).")

    # Keep the script running
    try:
        # ngrok process is managed by pyngrok in the background
        # We just wait for keyboard interrupt
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down ngrok...")
        ngrok.kill()

if __name__ == "__main__":
    start_ngrok()

