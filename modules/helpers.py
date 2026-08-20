
import html
import re

from html.parser import HTMLParser


def markdown_to_telegram_html(text: str) -> str:
    """Convert the small Markdown subset commonly returned by Gemini."""
    if not text:
        return ""

    converted_lines: list[str] = []
    for line in text.splitlines():
        line = re.sub(r"^\s*[-+*]\s+", "• ", line)
        line = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)
        line = re.sub(r"__(.+?)__", r"<b>\1</b>", line)
        converted_lines.append(line)
    return "\n".join(converted_lines)


def sanitize_telegram_html(text: str) -> str:
    """Keeps Telegram-supported HTML and escapes literal text safely."""
    if not text:
        return ""

    tag_names = {
        "b": "b",
        "strong": "b",
        "i": "i",
        "em": "i",
        "u": "u",
        "ins": "u",
        "s": "s",
        "strike": "s",
        "del": "s",
        "tg-spoiler": "tg-spoiler",
        "code": "code",
        "pre": "pre",
        "blockquote": "blockquote",
        "a": "a",
    }

    class TelegramHtmlParser(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=False)
            self.output: list[str] = []
            self.open_tags: list[str] = []

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            normalized_tag = tag.lower()
            telegram_tag = tag_names.get(normalized_tag)
            if telegram_tag is None:
                return

            if telegram_tag == "a":
                href = next((value for name, value in attrs if name.lower() == "href"), None)
                if href is None or not href.lower().startswith(("http://", "https://", "tg://")):
                    self.output.append("<a>")
                else:
                    self.output.append(f'<a href="{html.escape(href, quote=True)}">')
            else:
                self.output.append(f"<{telegram_tag}>")
            self.open_tags.append(telegram_tag)

        def handle_endtag(self, tag: str) -> None:
            telegram_tag = tag_names.get(tag.lower())
            if telegram_tag is None or telegram_tag not in self.open_tags:
                return

            self.output.append(f"</{telegram_tag}>")
            self.open_tags.remove(telegram_tag)

        def handle_data(self, data: str) -> None:
            self.output.append(html.escape(data, quote=False))

        def handle_entityref(self, name: str) -> None:
            if name in {"lt", "gt", "amp", "quot"}:
                self.output.append(f"&{name};")
            else:
                self.output.append(html.escape(f"&{name};", quote=False))

        def handle_charref(self, name: str) -> None:
            self.output.append(f"&#{name};")

    parser = TelegramHtmlParser()
    parser.feed(text)
    parser.close()
    for tag in reversed(parser.open_tags):
        parser.output.append(f"</{tag}>")
    return "".join(parser.output)


def remove_markup(text: str) -> str:
    """
    Removes supported HTML and common Markdown formatting from the text.
    """
    text = re.sub(r"</?[A-Za-z][^>]*>", "", text)
    text = text.replace("**", "")
    text = text.replace("__", "")
    return html.unescape(text)


def _split_telegram_html(text: str, limit: int = 4096) -> list[str]:
    """Splits Telegram HTML without leaving formatting tags unbalanced."""
    if not text:
        return [""]
    if len(text) <= limit:
        return [text]

    tokens = re.split(r"(</?[A-Za-z][^>]*>)", text)
    chunks: list[str] = []
    current: list[str] = []
    open_tags: list[str] = []

    def closing_tags() -> str:
        return "".join(f"</{tag}>" for tag in reversed(open_tags))

    def opening_tags() -> str:
        return "".join(f"<{tag}>" for tag in open_tags)

    def flush_chunk() -> None:
        nonlocal current
        if not current:
            return
        current_text = "".join(current)
        chunks.append(current_text + closing_tags())
        current = [opening_tags()]

    for token in tokens:
        if not token:
            continue

        tag_match = re.fullmatch(r"</?([A-Za-z][A-Za-z0-9-]*)[^>]*>", token)
        if tag_match:
            tag_name = tag_match.group(1).lower()
            is_closing = token.startswith("</")
            token_length = len(token)
            if len("".join(current)) + token_length + len(closing_tags()) > limit:
                flush_chunk()
            current.append(token)
            if is_closing:
                if tag_name in open_tags:
                    open_tags.remove(tag_name)
            else:
                open_tags.append(tag_name)
            continue

        remaining = token
        while remaining:
            current_length = len("".join(current))
            capacity = limit - current_length - len(closing_tags())
            if capacity <= 0:
                flush_chunk()
                continue
            if len(remaining) <= capacity:
                current.append(remaining)
                break

            split_at = remaining.rfind("\n\n", 0, capacity + 1)
            if split_at <= 0:
                split_at = remaining.rfind("\n", 0, capacity + 1)
            if split_at <= 0:
                split_at = capacity
            current.append(remaining[:split_at])
            remaining = remaining[split_at:]
            flush_chunk()

    if current and "".join(current) != opening_tags():
        chunks.append("".join(current) + closing_tags())

    return chunks


