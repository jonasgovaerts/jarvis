"""One-time Gmail OAuth bootstrap (run from your workstation, never in-cluster).

Prereqs (personal @gmail.com):
1. GCP project → enable the Gmail API.
2. OAuth consent screen: External. PUBLISH the app to "In production"
   (unverified is fine for yourself — accept the warning once). Testing-status
   apps get refresh tokens that expire every 7 days; published ones do not.
3. Credentials → OAuth client ID → Desktop app → download client_secret.json
   into tools/ (gitignored).

Run: make google-auth
Output: tools/authorized_user.json (gitignored) + instructions to seal it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]  # no permanent delete
HERE = Path(__file__).resolve().parent
CLIENT_SECRET = HERE / "client_secret.json"
OUTPUT = HERE / "authorized_user.json"


def main() -> int:
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Run via: uv run --with google-auth-oauthlib python tools/google_auth_bootstrap.py")
        return 1

    if not CLIENT_SECRET.exists():
        print(f"Missing {CLIENT_SECRET}. Download the Desktop-app OAuth client JSON there first.")
        return 1

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")

    OUTPUT.write_text(
        json.dumps(
            {
                "type": "authorized_user",
                "client_id": creds.client_id,
                "client_secret": creds.client_secret,
                "refresh_token": creds.refresh_token,
            },
            indent=2,
        )
    )
    print(f"\nWrote {OUTPUT}")
    print(
        "\nSeal it for the cluster, then DELETE the plaintext:\n"
        "  kubectl create secret generic gmail-credentials \\\n"
        f"    --from-file=authorized_user.json={OUTPUT} \\\n"
        "    --namespace jarvis-system --dry-run=client -o yaml \\\n"
        "  | kubeseal --format yaml > deploy/apps/workspace/overlays/prod/sealedsecret-gmail.yaml\n"
        f"  rm {OUTPUT}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
