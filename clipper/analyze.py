"""Style scan: break a reference Short into pictures + timed text that can be
shared in a chat, so its look (captions, framing, pacing) can be copied.

    python -m clipper.analyze "https://youtube.com/shorts/..."
"""

import argparse
import re
import subprocess
from pathlib import Path

from . import media, transcribe


def _scene_cuts(video: Path, threshold: float = 0.3) -> list[float]:
    log = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(video), "-an",
         "-vf", f"select='gt(scene,{threshold})',showinfo", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    return [float(t) for t in re.findall(r"pts_time:([\d.]+)", log)]


def _sheet(video: Path, out: Path, start: float, length: float, frames: int, cols: int):
    """Save `frames` evenly spaced frames from [start, start+length] as one grid image."""
    rows = -(-frames // cols)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.2f}", "-t", f"{length:.2f}",
         "-i", str(video),
         "-vf", f"fps={frames / length:.4f},scale=480:-2,tile={cols}x{rows}:padding=6:color=white",
         "-frames:v", "1", str(out)],
        check=True,
    )


def main(argv=None):
    p = argparse.ArgumentParser(prog="clipper.analyze",
                                description="Make a shareable style report for a reference video.")
    p.add_argument("source", nargs="?", help="video link or file")
    p.add_argument("-o", "--out", type=Path, default=Path("style"))
    p.add_argument("--work", type=Path, default=Path("work"))
    p.add_argument("--model", default="small")
    args = p.parse_args(argv)
    if not args.source:
        args.source = input("Paste the link of a Short whose style you like: ").strip().strip('"')
    media.require_ffmpeg(captions=False)

    video = media.fetch_source(args.source, args.work / "downloads")
    info = media.probe(video)
    dur = info["duration"]
    name = re.sub(r"[^a-zA-Z0-9]+", "-", video.stem).strip("-").lower() or "video"
    out = args.out / name
    out.mkdir(parents=True, exist_ok=True)
    print(f"Analyzing {video.name} ({dur:.0f}s) ...")

    hook_len = min(6.0, dur)
    _sheet(video, out / "1-hook-first-seconds.png", 0, hook_len, 12, 4)
    _sheet(video, out / "2-whole-video.png", 0, dur, 16, 4)

    cuts = _scene_cuts(video)
    words = transcribe.transcribe(video, args.work / name / f"transcript-{args.model}.json",
                                  args.model)
    words = [w for w in words if w.start < dur]

    lines = [
        "CLIP STYLE REPORT",
        f"Length: {dur:.1f}s   Size: {info['width']}x{info['height']}   FPS: {info['fps']:.0f}",
        f"Pictures: 1-hook-first-seconds.png = 12 frames from 0-{hook_len:.0f}s "
        f"(one every {hook_len / 12:.2f}s); 2-whole-video.png = 16 frames, one every {dur / 16:.1f}s.",
        f"Cuts/scene changes: {len(cuts)}"
        + (f" (avg shot {dur / (len(cuts) + 1):.1f}s) at " + ", ".join(f"{c:.1f}s" for c in cuts[:40])
           if cuts else ""),
    ]
    if words:
        speech = sum(w.end - w.start for w in words)
        first = words[0].start
        lines += [
            f"Speech: {len(words)} words, {len(words) / max(dur, 1):.1f} words/sec overall; "
            f"first word at {first:.1f}s; talking {100 * speech / max(dur, 1):.0f}% of the time.",
            "",
            "TRANSCRIPT (seconds):",
        ]
        for s in transcribe.split_sentences(words):
            lines.append(f"[{s.start:5.1f}-{s.end:5.1f}] {s.text}")
    else:
        lines.append("Speech: none detected (music/visual only).")

    report = "\n".join(lines) + "\n"
    (out / "report.txt").write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"Saved to {out.resolve()}\n"
          "Send the two pictures and paste report.txt into your chat with Claude.")
    return out


if __name__ == "__main__":
    main()
