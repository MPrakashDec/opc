"""Load Dhan API credentials from token.txt"""
import os
from pathlib import Path

TOKEN_FILE = Path(__file__).parent / "token.txt"


def load_credentials() -> tuple[str, str]:
    """Load client_id and access_token from token.txt.
    
    Supports formats:
      - client_id=xxx
        access_token=yyy
      - xxx (line 1 = client_id)
        yyy (line 2 = access_token)
    """
    if not TOKEN_FILE.exists():
        raise FileNotFoundError(
            f"token.txt not found at {TOKEN_FILE}\n"
            "Create token.txt with your client_id and access_token (one per line)"
        )
    
    client_id = ""
    access_token = ""
    
    with open(TOKEN_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, val = line.partition("=")
                key = key.strip().lower()
                val = val.strip()
                if key in ("client_id", "clientid"):
                    client_id = val
                elif key in ("access_token", "accesstoken", "token"):
                    access_token = val
            else:
                if not client_id:
                    client_id = line
                elif not access_token:
                    access_token = line
                    break
    
    if not client_id or not access_token:
        raise ValueError(
            "token.txt must contain client_id and access_token.\n"
            "Format: client_id=xxx\naccess_token=yyy"
        )
    
    return client_id, access_token
