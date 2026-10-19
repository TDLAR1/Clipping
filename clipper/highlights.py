"""Finding the moments worth clipping.

Every window of whole sentences between --min and --max seconds is a candidate.
Each candidate gets a virality score from signals that the paid clippers also
lean on: a strong hook in the first seconds, vocal energy, pace, emotional or
curiosity-driving words, a complete thought with a payoff at the end, and few
fillers or dead air. An optional free LLM (see llm.py) then re-ranks the best
candidates and writes titles.
"""

import re
from dataclasses import dataclass, field

import numpy as np

from .transcribe import Sentence

HOP = 0.25  # must match media.loudness_curve

HOOK_PHRASES = [
    "here's the thing", "the truth is", "nobody", "no one", "most people",
    "the problem", "the secret", "the reason", "the biggest", "the worst",
    "the best", "stop", "never", "don't", "you need", "you have to",
    "what if", "imagine", "let me tell you", "i'll tell you", "listen",
    "the craziest", "the moment", "i was", "i remember", "true story",
    "here's why", "here's how", "this is why", "this is how", "the one thing",
    "if you", "why do", "why does", "why is", "how do", "how does", "what's",
    "i can't believe", "people don't", "everyone thinks", "everybody thinks",
    "unpopular opinion", "hot take", "the mistake", "i lost", "i made",
    "million", "billion",
]

STRONG_WORDS = set("""
insane crazy unbelievable shocking secret mistake mistakes biggest worst best
never always everyone nobody million billion money rich broke fired quit
died dead death kill killed love hate afraid scared fear lie lied lying truth
wrong right genius stupid dumb huge massive ridiculous honestly literally
actually seriously wild hilarious embarrassing failure failed success won lost
win lose fight war crazy illegal banned changed realized discovered exposed
""".split())

FILLERS = {"um", "uh", "erm", "ah", "hmm", "like", "basically", "kinda", "sorta"}
FILLER_PHRASES = ["you know", "i mean", "sort of", "kind of"]
BAD_OPENERS = {"and", "but", "so", "because", "or", "which", "that", "then",
               "also", "um", "uh", "yeah", "right", "okay", "ok"}
CONTEXT_OPENERS = {"it", "this", "they", "he", "she", "that", "those", "these"}


def _clean(text: str) -> str:
    return re.sub(r"[^a-z0-9' ]+", " ", text.lower())


@dataclass
class Clip:
    start: float
    end: float
    sentences: list
    score: float = 0.0
    heuristic: float = 0.0
    llm_score: float | None = None
    title: str = ""
    reason: str = ""
    signals: dict = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def text(self) -> str:
        return " ".join(s.text for s in self.sentences)

    @property
    def words(self):
        return [w for s in self.sentences for w in s.words]


def _window_db(loud: np.ndarray, start: float, end: float) -> np.ndarray:
    a, b = int(start / HOP), max(int(end / HOP), int(start / HOP) + 1)
    return loud[a:b] if a < len(loud) else np.array([loud.mean()])


def _hook_score(text: str) -> float:
    t = _clean(text)
    score = 0.0
    if "?" in text:
        score += 0.35
    score += min(0.5, 0.25 * sum(p in t for p in HOOK_PHRASES))
    if re.search(r"\b\d+\b|\b(one|two|three|five|ten|hundred|thousand)\b", t):
        score += 0.15
    if re.search(r"\byou\b|\byour\b", t):
        score += 0.1
    score += min(0.3, 0.1 * sum(w in STRONG_WORDS for w in t.split()))
    return min(score, 1.0)


def _score(clip: Clip, loud: np.ndarray, speech_db: float, median_wps: float,
           target: float) -> float:
    words = clip.words
    first = clip.sentences[0]
    last = clip.sentences[-1]
    tokens = [_clean(w.text).strip() for w in words]
    n = max(len(tokens), 1)
    text = _clean(clip.text)

    # Hook: what is said in roughly the first 6 seconds.
    hook_words = [w.text for w in words if w.start < clip.start + 6]
    hook = _hook_score(" ".join(hook_words))

    # Energy: louder than this speaker's normal, with peaks (laughs, emphasis).
    db = _window_db(loud, clip.start, clip.end)
    energy = float(np.clip((db.mean() - speech_db + 4) / 10, 0, 1))
    peaks = float(np.clip(np.mean(db > speech_db + 6) * 5, 0, 1))
    hook_db = _window_db(loud, clip.start, min(clip.end, clip.start + 4))
    hook_energy = float(np.clip((hook_db.mean() - speech_db + 3) / 8, 0, 1))

    # Pace: excited speech is faster; long gaps kill retention.
    wps = n / max(clip.duration, 1e-6)
    pace = float(np.clip(0.5 + (wps - median_wps) / max(median_wps, 1e-6), 0, 1))
    gaps = [b.start - a.end for a, b in zip(words, words[1:])]
    dead_air = sum(g for g in gaps if g > 1.2)

    # Content: emotional and curiosity words, direct address, numbers, stories.
    strong = sum(t in STRONG_WORDS for t in tokens) / n
    content = float(np.clip(strong * 12, 0, 1))
    content += 0.15 if "?" in clip.text else 0
    content += 0.1 if re.search(r"\bi (was|remember|had|told|said)\b", text) else 0
    content = min(content, 1.0)

    # Structure: start on a fresh thought, end on a complete one.
    opener = _clean(first.words[0].text).strip()
    structure = 1.0
    if opener in BAD_OPENERS:
        structure -= 0.5
    elif opener in CONTEXT_OPENERS:
        structure -= 0.25
    if not re.search(r"[.!?…]['\"”’)]*$", last.words[-1].text):
        structure -= 0.3
    if last.words[-1].text.endswith("!"):
        structure += 0.1
    structure = float(np.clip(structure, 0, 1))

    fillers = sum(t in FILLERS for t in tokens) + sum(text.count(p) for p in FILLER_PHRASES)
    filler_ratio = fillers / n

    fit = float(np.exp(-((clip.duration - target) / (target * 0.6)) ** 2))

    score = (
        26 * hook
        + 10 * hook_energy
        + 12 * energy
        + 6 * peaks
        + 8 * pace
        + 14 * content
        + 16 * structure
        + 8 * fit
        - 60 * filler_ratio
        - 4 * dead_air
    )
    clip.signals = {
        "hook": round(hook, 2), "hook_energy": round(hook_energy, 2),
        "energy": round(energy, 2), "peaks": round(peaks, 2), "pace": round(pace, 2),
        "content": round(content, 2), "structure": round(structure, 2),
        "fillers": round(filler_ratio, 3), "dead_air": round(dead_air, 1),
    }
    return float(np.clip(score, 0, 100))


def candidates(sentences: list[Sentence], loud: np.ndarray,
               min_len: float, max_len: float) -> list[Clip]:
    if not sentences:
        return []
    speech = np.concatenate([_window_db(loud, s.start, s.end) for s in sentences])
    speech_db = float(np.median(speech))
    rates = [len(s.words) / max(s.end - s.start, 0.3) for s in sentences]
    median_wps = float(np.median(rates))
    target = min(max((min_len + max_len) / 2, min_len), max_len)

    out = []
    for i in range(len(sentences)):
        for j in range(i, len(sentences)):
            dur = sentences[j].end - sentences[i].start
            if dur > max_len:
                break
            if dur < min_len:
                continue
            clip = Clip(sentences[i].start, sentences[j].end, sentences[i:j + 1])
            clip.heuristic = clip.score = _score(clip, loud, speech_db, median_wps, target)
            out.append(clip)
    return out


def pick(cands: list[Clip], count: int, min_gap: float = 2.0) -> list[Clip]:
    """Best-scoring clips that don't overlap each other."""
    chosen = []
    for c in sorted(cands, key=lambda c: c.score, reverse=True):
        if all(c.end + min_gap <= o.start or c.start >= o.end + min_gap for o in chosen):
            chosen.append(c)
            if len(chosen) == count:
                break
    return chosen


def default_title(clip: Clip, max_words: int = 9) -> str:
    words = clip.sentences[0].text.split()
    title = " ".join(words[:max_words]).rstrip(",;:")
    return title + ("..." if len(words) > max_words else "")
