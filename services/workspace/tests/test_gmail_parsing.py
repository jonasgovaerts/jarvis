import base64

from workspace.gmail import ParsedEmail, _extract_text, build_reply_mime


def b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def test_extract_prefers_plain_text():
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/plain", "body": {"data": b64("hello plain")}},
            {"mimeType": "text/html", "body": {"data": b64("<p>hello <b>html</b></p>")}},
        ],
    }
    assert _extract_text(payload) == "hello plain"


def test_extract_falls_back_to_stripped_html():
    payload = {
        "mimeType": "text/html",
        "body": {"data": b64("<style>x{}</style><p>Invoice <b>attached</b></p>")},
    }
    assert _extract_text(payload) == "Invoice attached"


def email(subject: str = "Quarterly numbers", refs: str = "") -> ParsedEmail:
    return ParsedEmail(
        gmail_message_id="m1",
        thread_id="t1",
        subject=subject,
        from_addr="alice@example.com",
        to_addr="me@gmail.com",
        body_text="Can you send the numbers?",
        message_id_header="<msg-1@example.com>",
        references=refs,
    )


def test_reply_mime_threading_headers():
    mime = build_reply_mime(email(), "On it — will send today.", "me@gmail.com")
    assert mime["Subject"] == "Re: Quarterly numbers"
    assert mime["To"] == "alice@example.com"
    assert mime["In-Reply-To"] == "<msg-1@example.com>"
    assert mime["References"] == "<msg-1@example.com>"
    assert "On it" in mime.get_content()


def test_reply_mime_keeps_re_prefix_and_appends_references():
    mime = build_reply_mime(
        email(subject="Re: Quarterly numbers", refs="<root@example.com>"),
        "Done.",
        "me@gmail.com",
    )
    assert mime["Subject"] == "Re: Quarterly numbers"
    assert mime["References"] == "<root@example.com> <msg-1@example.com>"
