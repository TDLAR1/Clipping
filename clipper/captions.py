"""Animated word-by-word captions (the bold, highlighted style used on Shorts/TikTok)."""

import re

from .campaign import censor

STYLES = {
    # name: (text colour, highlight colour, outline colour) in ASS &HBBGGRR order
    "yellow": ("&H00FFFFFF", "&H0000E5FF", "&H00000000"),
    "green": ("&H00FFFFFF", "&H0000FF7F", "&H00000000"),
    "red": ("&H00FFFFFF", "&H003C3CFF", "&H00000000"),
    "white": ("&H00FFFFFF", "&H00FFFFFF", "&H00000000"),
}


def _ts(t: float) -> str:
    t = max(t, 0)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _safe(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")")


def _chunks(words, max_words: int, max_chars: int):
    chunk = []
    for i, w in enumerate(words):
        chunk.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        chars = sum(len(x.text) + 1 for x in chunk)
        if (nxt is None or len(chunk) >= max_words
                or chars + len(nxt.text) > max_chars
                or re.search(r"[.,!?;:…]$", w.text)
                or nxt.start - w.end > 0.35):
            yield chunk
            chunk = []


def build_ass(words, clip_start: float, clip_end: float, *, font: str = "Arial Black",
              size: int = 84, style: str = "yellow", uppercase: bool = True,
              max_words: int = 3, max_chars: int = 18, position: float = 0.70,
              title: str | None = None, title_seconds: float = 0.0,
              censor_words: dict | None = None) -> str:
    """ASS subtitle file for one 1080x1920 clip. Times are relative to clip_start."""
    base, hi, outline = STYLES.get(style, STYLES["yellow"])
    margin_v = int(1920 * (1 - position))
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},{size},{base},{base},{outline},&H80000000,-1,0,0,0,100,100,1,0,1,7,3,2,80,170,{margin_v},1
Style: Title,{font},62,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,3,18,0,8,80,80,190,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    if title and title_seconds > 0:
        t = _safe(censor(title.upper() if uppercase else title, censor_words))
        events.append(f"Dialogue: 1,{_ts(0)},{_ts(min(title_seconds, clip_end - clip_start))},"
                      f"Title,,0,0,0,,{{\\fad(150,250)}}{t}")

    words = [w for w in words if w.end > clip_start and w.start < clip_end]
    chunks = list(_chunks(words, max_words, max_chars))
    for ci, chunk in enumerate(chunks):
        nxt_start = chunks[ci + 1][0].start if ci + 1 < len(chunks) else clip_end
        # Keep the caption up through short pauses so it doesn't flicker.
        chunk_end = nxt_start if nxt_start - chunk[-1].end < 0.6 else chunk[-1].end + 0.25
        labels = [_safe(censor(w.text.upper() if uppercase else w.text, censor_words))
                  for w in chunk]
        for k, w in enumerate(chunk):
            start = w.start
            end = chunk[k + 1].start if k + 1 < len(chunk) else chunk_end
            parts = []
            for j, label in enumerate(labels):
                if j == k:
                    parts.append(f"{{\\c{hi}\\fscx112\\fscy112}}{label}{{\\c{base}\\fscx100\\fscy100}}")
                else:
                    parts.append(label)
            pop = "{\\t(0,80,\\fscx104\\fscy104)\\t(80,160,\\fscx100\\fscy100)}" if k == 0 else ""
            events.append(
                f"Dialogue: 0,{_ts(start - clip_start)},{_ts(end - clip_start)},Cap,,0,0,0,,"
                f"{pop}{' '.join(parts)}"
            )
    return header + "\n".join(events) + "\n"
