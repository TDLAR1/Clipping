"""Campaign presets: a folder under campaigns/ holding one campaign's rules.

    campaigns/<name>/
        options.txt   extra command-line options, e.g. "-n 15 --max 60"
        brief.txt     the campaign's rules, given to the AI when it picks clips
        post.txt      text added under every post caption (handle, hashtags, link)
        censor.txt    extra words to censor, one "word=w*rd" per line
        logo.png      optional logo shown at the top for the first seconds
"""

import re
import shlex
from pathlib import Path

import numpy as np

# Words the platforms commonly flag or down-rank. Censored in captions,
# titles and post text (the audio is left alone).
DEFAULT_CENSOR = {
    "sex": "s*x", "sexy": "s*xy", "sexual": "s*xual", "sexually": "s*xually",
    "porn": "p*rn", "fuck": "f*ck", "fucking": "f*cking", "fucked": "f*cked",
    "shit": "sh*t", "bitch": "b*tch", "suicide": "s*icide", "rape": "r*pe",
    "naked": "n*ked", "nude": "n*de",
}


def find(name: str) -> Path:
    path = Path(name)
    if not path.is_dir():
        path = Path(__file__).resolve().parent.parent / "campaigns" / name
    if not path.is_dir():
        raise SystemExit(f"Campaign folder not found: {name}")
    return path


def options(folder: Path) -> list[str]:
    f = folder / "options.txt"
    if not f.exists():
        return []
    text = "\n".join(l for l in f.read_text().splitlines() if not l.lstrip().startswith("#"))
    return shlex.split(text)


def read(folder: Path | None, name: str) -> str:
    if folder is None or not (folder / name).exists():
        return ""
    return (folder / name).read_text(encoding="utf-8").strip()


def censor_map(folder: Path | None) -> dict:
    words = dict(DEFAULT_CENSOR)
    for line in read(folder, "censor.txt").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            words[k.strip().lower()] = v.strip()
    return words


def censor(text: str, words: dict) -> str:
    if not words or not text:
        return text

    def swap(m):
        word = m.group(0)
        rep = words[word.lower()]
        if word.isupper() and len(word) > 1:
            return rep.upper()
        if word[0].isupper():
            return rep[0].upper() + rep[1:]
        return rep

    pattern = r"\b(" + "|".join(sorted(map(re.escape, words), key=len, reverse=True)) + r")\b"
    return re.sub(pattern, swap, text, flags=re.I)


def prepare_logo(src: Path, dest: Path, width: int = 460) -> Path:
    """Trim the logo's empty border, resize it and add a soft shadow for contrast."""
    import cv2
    img = cv2.imread(str(src), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise SystemExit(f"Couldn't read the logo: {src}")
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
    elif img.shape[2] == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    ys, xs = np.where(img[..., 3] > 10)
    if len(xs):
        img = img[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h = int(img.shape[0] * width / img.shape[1])
    img = cv2.resize(img, (width, h), interpolation=cv2.INTER_AREA)

    pad = 30
    canvas = np.zeros((h + 2 * pad, width + 2 * pad, 4), np.uint8)
    shadow = np.zeros(canvas.shape[:2], np.float32)
    shadow[pad:pad + h, pad:pad + width] = img[..., 3] / 255.0
    shadow = cv2.GaussianBlur(shadow, (0, 0), 9) * 0.75
    canvas[..., 3] = (shadow * 255).astype(np.uint8)
    a = img[..., 3:4] / 255.0
    region = canvas[pad:pad + h, pad:pad + width].astype(np.float32)
    region[..., :3] = img[..., :3] * a + region[..., :3] * (1 - a)
    region[..., 3:4] = 255 * a + region[..., 3:4] * (1 - a)
    canvas[pad:pad + h, pad:pad + width] = region.astype(np.uint8)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(dest), canvas)
    return dest
