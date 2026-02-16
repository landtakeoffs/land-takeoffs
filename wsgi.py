"""WSGI entry point with error catching."""
import sys
import traceback

try:
    from app import app
    print("✅ App imported successfully", flush=True)
except Exception as e:
    print(f"❌ FATAL IMPORT ERROR: {e}", flush=True)
    traceback.print_exc()
    sys.exit(1)
