
import io
import re

import matplotlib
import matplotlib.pyplot as plt

from telegram.helpers import escape_markdown

matplotlib.use("Agg")

ZERO_WIDTH_SPACE = "\u200b"


def escape_telegram_markdown(text: str) -> str:
    """
    Escapes special characters in the text for Telegram MarkdownV2.
    """
    return escape_markdown(text, version=2)


def _format_markdown_v2(text: str) -> str:
    """
    Best-effort conversion from common Markdown to Telegram MarkdownV2.
    Preserves basic formatting while escaping unsafe characters.
    """
    if not text:
        return ""

    normalized_text = text.replace("\r\n", "\n").replace("\r", "\n")
    placeholders = {}

    def add_placeholder(value: str) -> str:
        key = f"PLHDR{len(placeholders)}XPLHDR"
        placeholders[key] = value
        return key

    # Code blocks
    code_block_pattern = re.compile(r"```(\w+)?\n([\s\S]*?)```", re.MULTILINE)

    def replace_code_block(match: re.Match) -> str:
        language = match.group(1) or ""
        code = match.group(2)
        escaped_code = escape_markdown(code, version=2, entity_type="pre")
        if language:
            return add_placeholder(f"```{language}\n{escaped_code}```")
        return add_placeholder(f"```\n{escaped_code}```")

    normalized_text = code_block_pattern.sub(replace_code_block, normalized_text)

    # Inline code
    inline_code_pattern = re.compile(r"`([^`\n]+)`")

    def replace_inline_code(match: re.Match) -> str:
        code = match.group(1)
        escaped_code = escape_markdown(code, version=2, entity_type="code")
        return add_placeholder(f"`{escaped_code}`")

    normalized_text = inline_code_pattern.sub(replace_inline_code, normalized_text)

    # Links
    link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

    def replace_link(match: re.Match) -> str:
        label = escape_markdown(match.group(1), version=2)
        url = match.group(2).replace("\\", "\\\\").replace(")", "\\)")
        return add_placeholder(f"[{label}]({url})")

    normalized_text = link_pattern.sub(replace_link, normalized_text)

    # Bold **text**
    normalized_text = re.sub(
        r"\*\*([^*\n]+)\*\*",
        lambda m: add_placeholder(f"*{escape_markdown(m.group(1), version=2)}*"),
        normalized_text,
    )

    # Underline __text__
    normalized_text = re.sub(
        r"__([^_\n]+)__",
        lambda m: add_placeholder(f"__{escape_markdown(m.group(1), version=2)}__"),
        normalized_text,
    )

    # Italic *text*
    normalized_text = re.sub(
        r"(?<!\*)\*([^*\n]+)\*(?!\*)",
        lambda m: add_placeholder(f"_{escape_markdown(m.group(1), version=2)}_"),
        normalized_text,
    )

    # Italic _text_
    normalized_text = re.sub(
        r"(?<!_)_([^_\n]+)_(?!_)",
        lambda m: add_placeholder(f"_{escape_markdown(m.group(1), version=2)}_"),
        normalized_text,
    )

    # Strikethrough ~~text~~
    normalized_text = re.sub(
        r"~~([^~\n]+)~~",
        lambda m: add_placeholder(f"~{escape_markdown(m.group(1), version=2)}~"),
        normalized_text,
    )

    # Spoiler ||text||
    normalized_text = re.sub(
        r"\|\|([^|\n]+)\|\|",
        lambda m: add_placeholder(f"||{escape_markdown(m.group(1), version=2)}||"),
        normalized_text,
    )

    # Escape remaining text
    escaped_text = escape_markdown(normalized_text, version=2)

    # Restore placeholders
    for key, value in placeholders.items():
        escaped_text = escaped_text.replace(key, value)

    return escaped_text


def remove_markdown(text: str) -> str:
    """
    Removes Markdown formatting from the text.
    """
    text = text.replace("**", "")
    text = text.replace("__", "")
    return text


def _split_telegram_message(text: str, limit: int = 4096) -> list[str]:
    """
    Splits text into chunks within Telegram's message size limit.
    Attempts to split on paragraph boundaries first.
    """
    if not text:
        return [""]

    if len(text) <= limit:
        return [text]

    chunks = []
    remaining = text

    while len(remaining) > limit:
        split_index = remaining.rfind("\n\n", 0, limit)
        if split_index == -1:
            split_index = remaining.rfind("\n", 0, limit)
        if split_index == -1 or split_index < 1:
            split_index = limit

        chunk = remaining[:split_index].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_index:].lstrip()

    if remaining:
        chunks.append(remaining)

    return chunks


def split_text_with_latex(text: str) -> list[tuple[str, str]]:
    """
    Splits text into a sequence of (type, content), where type is 'text' or 'latex'.
    Handles both $$...$$ and $...$ (non-escaped) blocks.
    """
    if not text:
        return [("text", "")]

    pattern = re.compile(r"(?<!\\)\$\$(.+?)(?<!\\)\$\$|(?<!\\)\$(.+?)(?<!\\)\$", re.DOTALL)
    segments: list[tuple[str, str]] = []
    last_index = 0

    for match in pattern.finditer(text):
        start, end = match.span()
        if start > last_index:
            segments.append(("text", text[last_index:start]))

        latex_content = match.group(1) if match.group(1) is not None else match.group(2)
        if latex_content is None:
            latex_content = ""
        segments.append(("latex", latex_content))
        last_index = end

    if last_index < len(text):
        segments.append(("text", text[last_index:]))

    return segments


def render_latex_to_png_bytes(latex: str, fontsize: int = 14, dpi: int = 200) -> bytes | None:
    """
    Renders LaTeX to PNG bytes using matplotlib's mathtext.
    Returns None if rendering fails.
    """
    if latex is None:
        return None

    latex = latex.strip()
    if not latex:
        return None

    latex = latex.replace("\n", " \\ ")

    try:
        fig = plt.figure(figsize=(0.01, 0.01))
        fig.patch.set_alpha(0)
        text = fig.text(0, 0, f"${latex}$", fontsize=fontsize)
        fig.canvas.draw()
        bbox = text.get_window_extent()
        width, height = bbox.size / dpi
        fig.set_size_inches((width, height))
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", pad_inches=0.1, transparent=True)
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()
    except (RuntimeError, ValueError, OSError):
        try:
            plt.close("all")
        except (RuntimeError, ValueError, OSError):
            pass
        return None
