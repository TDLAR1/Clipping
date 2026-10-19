"""Speech-to-text with word timestamps (faster-whisper, runs locally for free)."""

import json
import os
import re
import subprocess
import sys
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
    if not cache.exists():
        # Whisper runs in its own process: its audio library (PyAV) and OpenCV
        # each bundle their own ffmpeg, and loading both in one process can
        # crash on macOS.
        cmd = [sys.executable, "-m", "clipper.transcribe", str(video.resolve()),
               str(cache.resolve()), model_size, language or ""]
        env = {**os.environ, "HF_HUB_VERBOSITY": "error"}
        result = subprocess.run(cmd, cwd=Path(__file__).resolve().parent.parent, env=env)
        if result.returncode != 0 or not cache.exists():
            raise SystemExit("Transcription failed - see the message above.")
    else:
        print(f"Using cached transcript: {cache}")
    return [Word(**w) for w in json.loads(cache.read_text())]


def _load_audio(video: Path, sr: int = 16000):
    """Decode audio with the ffmpeg program (avoids PyAV version problems)."""
    import numpy as np
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video), "-vn", "-ac", "1",
         "-ar", str(sr), "-f", "s16le", "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def _run_whisper(video: Path, cache: Path, model_size: str, language: str | None):
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
        _load_audio(video),
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
        print(f"\r  transcribed {seg.end / 60:5.1f} of {info.duration / 60:.1f} min",
              end="", flush=True)
    print()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps([asdict(w) for w in words]))


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


if __name__ == "__main__":
    _video, _cache, _model, _lang = sys.argv[1:5]
    _run_whisper(Path(_video), Path(_cache), _model, _lang or None)
