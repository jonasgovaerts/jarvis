"""Thin Gmail API wrapper. All calls are sync (google-api-python-client);
callers wrap in asyncio.to_thread."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from email.message import EmailMessage

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

LABELS = {
    "task": "Jarvis/Task",
    "informational": "Jarvis/Info",
    "newsletter": "Jarvis/Newsletter",
    "spam_ish": "Jarvis/Spamish",
}
PROCESSED_LABEL = "Jarvis/Processed"


@dataclass
class ParsedEmail:
    gmail_message_id: str
    thread_id: str
    subject: str
    from_addr: str
    to_addr: str
    body_text: str
    message_id_header: str = ""
    references: str = ""
    label_ids: list[str] = field(default_factory=list)


class GmailClient:
    def __init__(self, credentials_path: str):
        creds = Credentials.from_authorized_user_file(credentials_path)
        self._service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        self._label_ids: dict[str, str] = {}

    # --- profile / history ----------------------------------------------------

    def get_profile(self) -> dict:
        return self._service.users().getProfile(userId="me").execute()

    def history_since(self, history_id: str) -> tuple[list[str], str]:
        """New INBOX message ids since history_id; returns (ids, newHistoryId).
        Raises googleapiclient.errors.HttpError 404 when the id has expired."""
        ids: list[str] = []
        latest = history_id
        page_token = None
        while True:
            request = (
                self._service.users()
                .history()
                .list(
                    userId="me",
                    startHistoryId=history_id,
                    historyTypes=["messageAdded"],
                    labelId="INBOX",
                    pageToken=page_token,
                )
            )
            response = request.execute()
            latest = response.get("historyId", latest)
            for entry in response.get("history", []):
                for added in entry.get("messagesAdded", []):
                    ids.append(added["message"]["id"])
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return list(dict.fromkeys(ids)), str(latest)

    def list_inbox_ids(self, max_results: int = 200) -> list[str]:
        """Full resync fallback when the history id has expired."""
        response = (
            self._service.users()
            .messages()
            .list(userId="me", q="in:inbox", maxResults=max_results)
            .execute()
        )
        return [m["id"] for m in response.get("messages", [])]

    # --- messages ---------------------------------------------------------------

    def get_message(self, message_id: str) -> ParsedEmail:
        raw = (
            self._service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        headers = {h["name"].lower(): h["value"] for h in raw.get("payload", {}).get("headers", [])}
        return ParsedEmail(
            gmail_message_id=message_id,
            thread_id=raw.get("threadId", ""),
            subject=headers.get("subject", ""),
            from_addr=headers.get("from", ""),
            to_addr=headers.get("to", ""),
            body_text=_extract_text(raw.get("payload", {}))[:24_000],
            message_id_header=headers.get("message-id", ""),
            references=headers.get("references", ""),
            label_ids=raw.get("labelIds", []),
        )

    # --- labels ---------------------------------------------------------------

    def ensure_labels(self) -> None:
        existing = {
            label["name"]: label["id"]
            for label in self._service.users().labels().list(userId="me").execute()["labels"]
        }
        for name in [*LABELS.values(), PROCESSED_LABEL]:
            if name in existing:
                self._label_ids[name] = existing[name]
            else:
                created = (
                    self._service.users()
                    .labels()
                    .create(userId="me", body={"name": name})
                    .execute()
                )
                self._label_ids[name] = created["id"]

    def apply_category(self, message_id: str, category: str, *, archive: bool) -> None:
        add = [self._label_ids[LABELS[category]], self._label_ids[PROCESSED_LABEL]]
        body: dict = {"addLabelIds": add}
        if archive and category != "task":
            body["removeLabelIds"] = ["INBOX"]
        self._service.users().messages().modify(userId="me", id=message_id, body=body).execute()

    # --- drafts ---------------------------------------------------------------

    def create_reply_draft(self, email: ParsedEmail, reply_text: str, own_addr: str) -> str:
        mime = build_reply_mime(email, reply_text, own_addr)
        encoded = base64.urlsafe_b64encode(mime.as_bytes()).decode()
        draft = (
            self._service.users()
            .drafts()
            .create(
                userId="me",
                body={"message": {"threadId": email.thread_id, "raw": encoded}},
            )
            .execute()
        )
        return draft["id"]


def build_reply_mime(email: ParsedEmail, reply_text: str, own_addr: str) -> EmailMessage:
    """RFC822 reply with proper threading headers."""
    mime = EmailMessage()
    mime["To"] = email.from_addr
    mime["From"] = own_addr
    mime["Subject"] = (
        email.subject if email.subject.lower().startswith("re:") else f"Re: {email.subject}"
    )
    if email.message_id_header:
        mime["In-Reply-To"] = email.message_id_header
        mime["References"] = (
            f"{email.references} {email.message_id_header}".strip()
            if email.references
            else email.message_id_header
        )
    mime.set_content(reply_text)
    return mime


def _extract_text(payload: dict) -> str:
    """Prefer text/plain parts; fall back to tag-stripped text/html."""
    plain, html = [], []

    def walk(part: dict) -> None:
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if data:
            decoded = base64.urlsafe_b64decode(data + "===").decode(errors="replace")
            if mime == "text/plain":
                plain.append(decoded)
            elif mime == "text/html":
                html.append(decoded)
        for sub in part.get("parts", []) or []:
            walk(sub)

    walk(payload)
    if plain:
        return "\n".join(plain)
    if html:
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", "\n".join(html), flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s{2,}", " ", text).strip()
    return ""
