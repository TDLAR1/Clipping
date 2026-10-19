"""Getting the source video and reading its audio/metadata with ffmpeg."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np


def require_ffmpeg():
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise SystemExit(
                f"'{tool}' was not found. Install ffmpeg first (see README.md) "
                "and make sure it is on your PATH."
            )


def is_url(source: str) -> bool:
    return bool(re.match(r"^https?://", source.strip(), re.I))


def fetch_source(source: str, work_dir: Path) -> Path:
    """Return a local video path, downloading it with yt-dlp if `source` is a link."""
    if not is_url(source):
        path = Path(source).expanduser()
        if not path.exists():
            raise SystemExit(f"File not found: {path}")
        return path

    try:
        import yt_dlp
    except ImportError:
        raise SystemExit("yt-dlp is not installed. Run: pip install -r requirements.txt")

    work_dir.mkdir(parents=True, exist_ok=True)
    opts = {
        # Best quality up to 1080p is plenty for a 1080x1920 crop.
        "format": "bv*[height<=1080]+ba/b[height<=1080]/b",
        "merge_output_format": "mp4",
        "outtmpl": str(work_dir / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    print(f"Downloading {source} ...")
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(source, download=True)
        path = Path(ydl.prepare_filename(info))
    if not path.exists():
        path = path.with_suffix(".mp4")
    return path


def probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_streams", "-show_format", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    data = json.loads(out)
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    if video is None:
        raise SystemExit(f"No video stream in {path}")
    num, den = (video.get("avg_frame_rate") or "30/1").split("/")
    fps = float(num) / float(den) if float(den) else 30.0
    width, height = int(video["width"]), int(video["height"])
    # Phone videos store rotation as metadata; swap so we see the displayed size.
    rotation = 0
    for side in video.get("side_data_list", []):
        rotation = int(side.get("rotation", rotation))
    if abs(rotation) in (90, 270):
        width, height = height, width
    return {
        "width": width,
        "height": height,
        "fps": fps or 30.0,
        "duration": float(data["format"].get("duration", 0)),
    }


def loudness_curve(path: Path, hop: float = 0.25) -> np.ndarray:
    """RMS loudness in dB for every `hop` seconds of the file's audio."""
    sr = 8000
    step = int(sr * hop)
    proc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1",
         "-ar", str(sr), "-f", "s16le", "-"],
        stdout=subprocess.PIPE,
    )
    levels = []
    while True:
        chunk = proc.stdout.read(step * 2 * 4096)  # ~17 min of audio per read
        if not chunk:
            break
        samples = np.frombuffer(chunk[: len(chunk) // 2 * 2], dtype=np.int16)
        frames = samples[: len(samples) // step * step].astype(np.float32).reshape(-1, step) / 32768.0
        levels.append(20 * np.log10(np.sqrt(np.mean(frames ** 2, axis=1) + 1e-10)))
    proc.wait()
    return np.concatenate(levels) if levels else np.array([-60.0])
