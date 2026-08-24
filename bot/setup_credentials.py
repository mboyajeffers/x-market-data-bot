#!/usr/bin/env python3
"""
X Bot — Credential Setup & Validation
Accepts direct paste from developer.x.com. Validates against live X API.
Writes ~/.x_bot_env only on full success.

Usage:
    python3 setup_credentials.py
"""

import getpass
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import base64
import hmac
import hashlib
import time
import secrets
from pathlib import Path

ENV_PATH = Path.home() / ".x_bot_env"


def fetch_bearer_token(api_key: str, api_secret: str):
    """Fetch Bearer Token from X API using API Key + Secret.
    Returns bearer_token string or raises on failure.
    """
    creds = base64.b64encode(
        f"{urllib.parse.quote(api_key)}:{urllib.parse.quote(api_secret)}".encode()
    ).decode()
    req = urllib.request.Request(
        "https://api.twitter.com/oauth2/token",
        data=b"grant_type=client_credentials",
        headers={
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "User-Agent": "MboyaJeffers-XBot/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        if data.get("token_type") != "bearer":
            raise ValueError(f"Unexpected token_type: {data.get('token_type')}")
        return data["access_token"]
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise ValueError(f"HTTP {e.code}: {body}")


def _pct_encode(s: str) -> str:
    return urllib.parse.quote(s, safe="")


def oauth1_auth_header(method, url, params, api_key, api_secret, access_token, access_token_secret):
    """Build OAuth 1.0a Authorization header."""
    oauth_params = {
        "oauth_consumer_key":     api_key,
        "oauth_nonce":            secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp":        str(int(time.time())),
        "oauth_token":            access_token,
        "oauth_version":          "1.0",
    }
    all_params = {**params, **oauth_params}
    param_str = "&".join(
        f"{_pct_encode(k)}={_pct_encode(v)}"
        for k, v in sorted(all_params.items())
    )
    base_str = "&".join([
        _pct_encode(method.upper()),
        _pct_encode(url),
        _pct_encode(param_str),
    ])
    signing_key = f"{_pct_encode(api_secret)}&{_pct_encode(access_token_secret)}"
    sig = base64.b64encode(
        hmac.new(signing_key.encode(), base_str.encode(), hashlib.sha1).digest()
    ).decode()
    oauth_params["oauth_signature"] = sig
    header = "OAuth " + ", ".join(
        f'{_pct_encode(k)}="{_pct_encode(v)}"'
        for k, v in sorted(oauth_params.items())
    )
    return header


def verify_credentials(api_key, api_secret, access_token, access_token_secret):
    """Call GET /1.1/account/verify_credentials.json via OAuth 1.0a.
    Returns screen_name on success, raises ValueError on failure.
    """
    url = "https://api.twitter.com/1.1/account/verify_credentials.json"
    auth_header = oauth1_auth_header(
        "GET", url, {}, api_key, api_secret, access_token, access_token_secret
    )
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": auth_header,
            "User-Agent":    "MboyaJeffers-XBot/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        return data["screen_name"]
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            err = json.loads(body)
            code = err.get("errors", [{}])[0].get("code")
            msg  = err.get("errors", [{}])[0].get("message", body)
        except Exception:
            code, msg = None, body
        raise ValueError(f"Error {code}: {msg}")


def write_env(api_key, api_secret, bearer_token, access_token, access_token_secret):
    content = f"""# X Bot credentials — written by setup_credentials.py
# DO NOT EDIT MANUALLY — re-run setup_credentials.py to update
export X_API_KEY="{api_key}"
export X_API_SECRET="{api_secret}"
export X_BEARER_TOKEN="{bearer_token}"
export X_ACCESS_TOKEN="{access_token}"
export X_ACCESS_TOKEN_SECRET="{access_token_secret}"
"""
    ENV_PATH.write_text(content)
    ENV_PATH.chmod(0o600)


def main():
    print("=" * 60)
    print("X Bot Credential Setup — paste directly from developer.x.com")
    print("=" * 60)
    print()
    print("Step 1/3 — API Key & Secret (from 'Keys and Tokens' tab)")
    print("  These test the API Key + Secret pair via POST /oauth2/token")
    print()

    api_key = input("  API Key (25 chars): ").strip()
    if len(api_key) < 20:
        print(f"ERROR: API Key looks short ({len(api_key)} chars). Expected ~25.")
        sys.exit(1)

    api_secret = getpass.getpass("  API Secret (hidden, 50 chars): ").strip()
    if len(api_secret) < 40:
        print(f"ERROR: API Secret looks short ({len(api_secret)} chars). Expected ~50.")
        sys.exit(1)

    print()
    print("  Testing API Key + Secret against X API...")
    try:
        bearer_token = fetch_bearer_token(api_key, api_secret)
        print(f"  ✓ Bearer Token obtained ({len(bearer_token)} chars) — API Key+Secret valid.")
    except ValueError as e:
        print(f"\nFAILED: API Key+Secret rejected by X API.")
        print(f"  Error: {e}")
        print()
        print("  Fix: Go to developer.x.com → your app → 'Keys and Tokens'")
        print("       Click 'Regenerate' under API Key and Secret.")
        print("       Copy each value immediately after regeneration.")
        sys.exit(1)

    print()
    print("Step 2/3 — Access Token & Secret (from 'Keys and Tokens' tab)")
    print("  These test OAuth 1.0a signing via GET /1.1/account/verify_credentials")
    print()

    access_token = input("  Access Token (50 chars): ").strip()
    if len(access_token) < 30:
        print(f"ERROR: Access Token looks short ({len(access_token)} chars). Expected ~50.")
        sys.exit(1)

    access_token_secret = getpass.getpass("  Access Token Secret (hidden, 44-50 chars): ").strip()
    if len(access_token_secret) < 30:
        print(f"ERROR: Access Token Secret looks short ({len(access_token_secret)} chars). Expected 44-50.")
        sys.exit(1)

    print()
    print("  Testing OAuth 1.0a signature against X API...")
    try:
        screen_name = verify_credentials(api_key, api_secret, access_token, access_token_secret)
        print(f"  ✓ Authenticated as @{screen_name}")
    except ValueError as e:
        print(f"\nFAILED: OAuth 1.0a verification rejected.")
        print(f"  Error: {e}")
        print()
        print("  Most likely cause: wrong character in Access Token Secret.")
        print("  Fix: Go to developer.x.com → your app → 'Keys and Tokens'")
        print("       Click 'Regenerate' under Access Token and Secret.")
        print("       Copy the secret immediately — it's only shown once.")
        sys.exit(1)

    print()
    print("Step 3/3 — Writing credentials...")
    write_env(api_key, api_secret, bearer_token, access_token, access_token_secret)
    print(f"  ✓ Written to {ENV_PATH} (chmod 600)")
    print()
    print("=" * 60)
    print("VERIFIED. Run:")
    print()
    print("  source ~/.x_bot_env")
    print("  python3 post.py worldcup --dry-run")
    print()
    print("When ready to go live:")
    print("  python3 post.py worldcup")
    print("=" * 60)


if __name__ == "__main__":
    main()
