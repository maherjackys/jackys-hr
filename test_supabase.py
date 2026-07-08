"""
Standalone Supabase connectivity test.

Run manually with: python test_supabase.py

This file intentionally avoids doing work at import time so pytest collection
does not fail on machines that do not have local Streamlit secrets.
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path


def main() -> int:
    secrets_path = Path(__file__).parent / ".streamlit" / "secrets.toml"
    print(f"[1] Looking for secrets at: {secrets_path}")

    if not secrets_path.exists():
        print("    ERROR: secrets.toml NOT FOUND.")
        print("    Create .streamlit/secrets.toml with:")
        print('      SUPABASE_URL = "https://xxxx.supabase.co"')
        print('      SUPABASE_KEY = "sb_secret_..."')
        return 1

    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib  # pip install tomli on Python < 3.11
        except ImportError:
            print("    ERROR: need tomllib (Python 3.11+) or tomli package.")
            return 1

    with open(secrets_path, "rb") as f:
        secrets = tomllib.load(f)

    url = secrets.get("SUPABASE_URL", "")
    key = secrets.get("SUPABASE_KEY", "")

    print(f"[2] SUPABASE_URL found : {'YES - ' + url[:40] + '...' if url else 'NO'}")
    print(f"    SUPABASE_KEY found : {'YES - ' + key[:12] + '...' if key else 'NO'}")

    if not url or not key:
        print("    ERROR: one or both secrets are empty. Check secrets.toml.")
        return 1

    print("\n[3] Importing supabase...")
    try:
        from supabase import create_client
        print("    OK - supabase package found.")
    except ImportError as e:
        print(f"    ERROR importing supabase: {e}")
        print("    Run: pip install supabase")
        return 1

    print("[4] Creating Supabase client...")
    try:
        client = create_client(url, key)
        print("    OK - client created.")
    except Exception as e:
        print(f"    ERROR creating client: {e}")
        traceback.print_exc()
        return 1

    print("[5] Inserting test row into 'logs' table...")
    try:
        response = client.table("logs").insert({
            "log_type": "test",
            "source": "debug",
            "question": "connection test",
        }).execute()
        print(f"    OK - response: {response}")
    except Exception as e:
        print(f"    ERROR during insert: {e}")
        traceback.print_exc()
        return 1

    print("\nAll checks passed. Check Supabase Table Editor -> logs for the test row.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
