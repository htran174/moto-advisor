# test_openai_key.py
from dotenv import load_dotenv
from openai import OpenAI
import os

# Load environment
load_dotenv()

key = os.getenv("OPENAI_API_KEY")
print("Has OPENAI_API_KEY?", bool(key))
print("Starts with:", str(key)[:10] if key else "(none)")

if not key:
    raise SystemExit("❌ No API key found. Check your .env file path or spelling.")

try:
    client = OpenAI(api_key=key)
    response = client.responses.create(model="gpt-4o-mini", input="Hello from RideReady test")
    print("✅ OpenAI connection OK — model responded.")
except Exception as e:
    print("❌ OpenAI connection ERROR:", e)
