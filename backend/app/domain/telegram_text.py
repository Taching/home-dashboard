def telegram_message(summary: str, url: str) -> str:
    """The phone notification shows the start of the text. Keep the link after it."""
    body = summary.strip()
    link = url.strip()
    if not body:
        return link
    return f"{body}\n{link}"
