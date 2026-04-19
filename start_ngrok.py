import os
import sys
import time
from pyngrok import ngrok, conf
from pyngrok.exception import PyngrokNgrokError
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Configuration
BACKEND_PORT = 8001
FRONTEND_ENV_PATH = "../finova-front/finova-front/.env.local"
BACKEND_ENV_PATH = ".env"

# Reconnect settings
MAX_RETRIES = 50
RETRY_DELAY = 5       # seconds between retries
HEALTH_CHECK_INTERVAL = 10  # seconds between health checks


def update_env_file(file_path, key, value):
    if not os.path.exists(file_path):
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


def write_env_urls(public_url):
    """Update both frontend and backend env files with the new tunnel URL."""
    print(f"  → Updating Frontend environment: {FRONTEND_ENV_PATH}")
    update_env_file(FRONTEND_ENV_PATH, "NEXT_PUBLIC_API_URL", f"{public_url}/api")

    ws_url = public_url.replace("https://", "wss://").replace("http://", "ws://")
    update_env_file(FRONTEND_ENV_PATH, "NEXT_PUBLIC_WS_URL", f"{ws_url}/ws")

    print(f"  → Updating Backend environment: {BACKEND_ENV_PATH}")
    update_env_file(BACKEND_ENV_PATH, "NGROK_URL", public_url)


def connect_tunnel():
    """Create a new ngrok tunnel to the backend. Returns the public URL string."""
    # Kill any existing tunnels first to avoid 'address already in use'
    try:
        ngrok.kill()
    except Exception:
        pass

    time.sleep(1)

    tunnel = ngrok.connect(f"127.0.0.1:{BACKEND_PORT}")
    return tunnel.public_url


def is_tunnel_alive():
    """Quick check — if ngrok has no active tunnels, the connection is dead."""
    try:
        tunnels = ngrok.get_tunnels()
        return len(tunnels) > 0
    except Exception:
        return False


def start_ngrok():
    print(f"--- Starting pyngrok on port {BACKEND_PORT} ---")
    print(f"    Auto-reconnect enabled (max {MAX_RETRIES} retries)")
    print()

    # Set authtoken if available
    authtoken = os.getenv("NGROK_AUTHTOKEN")
    if authtoken:
        print("Using authtoken from .env")
        ngrok.set_auth_token(authtoken)
    else:
        print("WARNING: No NGROK_AUTHTOKEN found in .env. Tunnels will expire in 2 hours.")
        print("Get your token at: https://dashboard.ngrok.com/get-started/your-authtoken")

    # Initial connection
    retries = 0
    public_url = None
    while retries < MAX_RETRIES:
        try:
            public_url = connect_tunnel()
            print(f"\n✅ Tunnel LIVE at: {public_url}")
            write_env_urls(public_url)
            print()
            print("─" * 50)
            print("  1. RUN: python manage.py runserver 0.0.0.0:8001")
            print("  2. RESTART your Frontend dev server to pick up new URLs.")
            print("  3. This script will auto-reconnect if the tunnel drops.")
            print("─" * 50)
            break
        except PyngrokNgrokError as e:
            retries += 1
            print(f"⚠ Connection attempt {retries}/{MAX_RETRIES} failed: {e}")
            print(f"  Retrying in {RETRY_DELAY}s...")
            time.sleep(RETRY_DELAY)
        except Exception as e:
            retries += 1
            print(f"⚠ Unexpected error on attempt {retries}/{MAX_RETRIES}: {e}")
            time.sleep(RETRY_DELAY)

    if not public_url:
        print("❌ Could not establish ngrok tunnel after maximum retries. Exiting.")
        sys.exit(1)

    # ── Health check loop ─────────────────────────────────────
    print("\n🔄 Monitoring tunnel health...\n")
    consecutive_failures = 0
    try:
        while True:
            time.sleep(HEALTH_CHECK_INTERVAL)

            if is_tunnel_alive():
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                print(f"⚠ Tunnel appears down (check {consecutive_failures}/3)")
                
                if consecutive_failures >= 3:
                    print("🔁 Tunnel confirmed dead. Reconnecting...")
                    reconnect_retries = 0
                    while reconnect_retries < MAX_RETRIES:
                        try:
                            public_url = connect_tunnel()
                            print(f"✅ Reconnected! New URL: {public_url}")
                            write_env_urls(public_url)
                            print("   ⚠ IMPORTANT: Restart your frontend dev server to use the new URL!")
                            consecutive_failures = 0
                            break
                        except Exception as e:
                            reconnect_retries += 1
                            print(f"   Reconnect attempt {reconnect_retries}/{MAX_RETRIES} failed: {e}")
                            time.sleep(RETRY_DELAY)
                    
                    if consecutive_failures > 0:
                        print("❌ Could not reconnect. Exiting.")
                        sys.exit(1)

    except KeyboardInterrupt:
        print("\nShutting down ngrok...")
        ngrok.kill()


if __name__ == "__main__":
    start_ngrok()
