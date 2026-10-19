"""Speech-to-text with word timestamps (faster-whisper, runs locally for free)."""

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class Sentence:
    words: list
    start: float
    end: float

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words).strip()


def transcribe(video: Path, cache: Path, model_size: str = "small",
               language: str | None = None) -> list[Word]:
    """Transcribe once and cache the result next to the work files."""
    if cache.exists():
        print(f"Using cached transcript: {cache}")
        return [Word(**w) for w in json.loads(cache.read_text())]

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise SystemExit("faster-whisper is not installed. Run: pip install -r requirements.txt")

    device, compute = "cpu", "int8"
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            device, compute = "cuda", "float16"
    except Exception:
        pass

    print(f"Transcribing with Whisper '{model_size}' on {device} "
          "(first run downloads the model; long videos take a while) ...")
    model = WhisperModel(model_size, device=device, compute_type=compute)
    segments, info = model.transcribe(
        str(video),
        language=language,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 400},
    )
    words = []
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append(Word(text, round(w.start, 3), round(w.end, 3)))
        print(f"\r  transcribed {seg.end / 60:5.1f} min", end="", flush=True)
    print()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps([asdict(w) for w in words]))
    return words


_END = re.compile(r"[.!?…]['\"”’)]*$")


def split_sentences(words: list[Word], pause: float = 0.8, max_words: int = 40) -> list[Sentence]:
    """Group words into sentences using punctuation, long pauses and a length cap."""
    sentences, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        gap = (nxt.start - w.end) if nxt else 99
        if _END.search(w.text) or gap >= pause or len(cur) >= max_words or nxt is None:
            sentences.append(Sentence(cur, cur[0].start, cur[-1].end))
            cur = []
    return sentences
