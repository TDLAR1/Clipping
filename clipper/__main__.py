"""Free AI clipper: long video in, ready-to-post vertical clips out.

    python -m clipper "https://www.youtube.com/watch?v=..." --count 8
    python -m clipper podcast.mp4 --llm ollama
"""

import argparse
import json
import re
import subprocess
import time
from pathlib import Path

from . import captions, highlights, llm, media, reframe, render, transcribe


def _slug(text: str, n: int = 40) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return s[:n].rstrip("-") or "clip"


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="clipper",
        description="Turn a long video (file or YouTube/Twitch/etc. link) into "
                    "vertical, captioned short clips.",
    )
    p.add_argument("source", nargs="?", help="video file or link (asked for if left out)")
    p.add_argument("-n", "--count", type=int, default=6, help="how many clips to make (default 6)")
    p.add_argument("--min", dest="min_len", type=float, default=20, help="shortest clip in seconds (default 20)")
    p.add_argument("--max", dest="max_len", type=float, default=60, help="longest clip in seconds (default 60)")
    p.add_argument("-o", "--out", type=Path, default=Path("clips"), help="output folder (default ./clips)")
    p.add_argument("--work", type=Path, default=Path("work"), help="folder for downloads and caches")

    g = p.add_argument_group("transcription")
    g.add_argument("--model", default="small",
                   help="Whisper size: tiny, base, small, medium, large-v3 "
                        "(bigger = more accurate captions but slower; default small)")
    g.add_argument("--language", help="spoken language code, e.g. en, es, ar (auto-detected if left out)")

    g = p.add_argument_group("AI ranking (optional, free)")
    g.add_argument("--llm", choices=["ollama", "api"],
                   help="re-rank clips and write titles with an LLM: 'ollama' (local) "
                        "or 'api' (OpenAI-compatible free tier, see README)")
    g.add_argument("--llm-model", help="model name, e.g. llama3.1:8b for Ollama")

    g = p.add_argument_group("look")
    g.add_argument("--layout", choices=["auto", "face", "center", "blur"], default="auto",
                   help="auto: follow faces, or blurred background when there are none (default)")
    g.add_argument("--no-captions", action="store_true", help="don't burn in captions")
    g.add_argument("--caption-color", choices=sorted(captions.STYLES), default="yellow")
    g.add_argument("--font", default="Arial Black", help="caption font (default Arial Black)")
    g.add_argument("--font-size", type=int, default=84)
    g.add_argument("--caption-pos", type=float, default=0.70,
                   help="caption height, 0 = top .. 1 = bottom (default 0.70)")
    g.add_argument("--lowercase", action="store_true", help="keep captions in normal case instead of CAPS")
    g.add_argument("--title-seconds", type=float, default=0,
                   help="show the clip title at the top for this many seconds (default off)")
    g.add_argument("--quality", choices=["fast", "good", "best"], default="good")
    p.add_argument("--dry-run", action="store_true", help="only list the picked moments, don't render")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if not args.source:
        args.source = input("Paste a video link or file path: ").strip().strip('"')
    if args.min_len >= args.max_len:
        raise SystemExit("--min must be smaller than --max")
    media.require_ffmpeg(captions=not args.no_captions)
    t0 = time.time()

    video = media.fetch_source(args.source, args.work / "downloads")
    info = media.probe(video)
    name = _slug(video.stem, 60)
    work = args.work / name
    print(f"Video: {video.name}  {info['width']}x{info['height']}  "
          f"{info['duration'] / 60:.1f} min")

    words = transcribe.transcribe(video, work / f"transcript-{args.model}.json",
                                  args.model, args.language)
    if not words:
        raise SystemExit("No speech found in this video, so there is nothing to clip.")
    sentences = transcribe.split_sentences(words)
    loud = media.loudness_curve(video)

    cands = highlights.candidates(sentences, loud, args.min_len, args.max_len)
    if not cands:
        raise SystemExit(f"Couldn't find any {args.min_len:.0f}-{args.max_len:.0f}s stretches of "
                         "speech. Try lowering --min.")
    print(f"Scored {len(cands)} possible clips.")

    chosen = None
    if args.llm:
        pool = highlights.pick(cands, max(args.count * 3, 12), min_gap=0)
        if llm.rerank(pool, args.llm, args.llm_model):
            chosen = highlights.pick(pool, args.count)
    if chosen is None:
        chosen = highlights.pick(cands, args.count)
    chosen.sort(key=lambda c: c.score, reverse=True)

    out_dir = args.out / name
    out_dir.mkdir(parents=True, exist_ok=True)
    preset, crf = {"fast": ("veryfast", 23), "good": ("medium", 20), "best": ("slow", 18)}[args.quality]
    fonts_dir = Path(__file__).resolve().parent.parent / "fonts"
    report = []

    for i, clip in enumerate(chosen, 1):
        clip.title = clip.title or highlights.default_title(clip)
        start = max(0.0, clip.start - 0.15)
        end = min(info["duration"] or clip.end + 1, clip.end + 0.45)
        fname = f"{i:02d}_{_slug(clip.title)}.mp4"
        print(f"\n[{i}/{len(chosen)}] score {clip.score:4.1f}  "
              f"{_mmss(start)}-{_mmss(end)} ({end - start:.0f}s)  {clip.title}")
        entry = {
            "file": fname, "title": clip.title, "score": round(clip.score, 1),
            "start": round(start, 2), "end": round(end, 2),
            "ai_score": clip.llm_score, "ai_reason": clip.reason,
            "signals": clip.signals, "transcript": clip.text,
        }
        report.append(entry)
        if args.dry_run:
            continue

        tr = reframe.track(video, start, end, info["width"], info["height"], args.layout)
        entry["layout"] = "face-tracking" if tr.layout == "crop" else "blurred background"
        ass = None if args.no_captions else captions.build_ass(
            clip.words, start, end, font=args.font, size=args.font_size,
            style=args.caption_color, uppercase=not args.lowercase,
            position=args.caption_pos, title=clip.title, title_seconds=args.title_seconds,
        )
        try:
            render.render(video, out_dir / fname, start, end, tr, ass, work / f"clip{i:02d}",
                          info["fps"], fonts_dir, crf, preset)
        except subprocess.CalledProcessError:
            print(f"  ffmpeg couldn't make this clip (see the message above); skipping it.")
            entry["file"] = None

    (out_dir / "clips.json").write_text(json.dumps(report, indent=2))
    with open(out_dir / "clips.txt", "w", encoding="utf-8") as f:
        for e in report:
            if not e["file"] and not args.dry_run:
                continue
            f.write(f"{e['file']}\n  Title: {e['title']}\n  Score: {e['score']}"
                    f"  ({_mmss(e['start'])}-{_mmss(e['end'])} in the original)\n"
                    f"  Says: {e['transcript']}\n\n")
    verb = "Picked" if args.dry_run else "Made"
    made = len(report) if args.dry_run else sum(1 for e in report if e["file"])
    print(f"\n{verb} {made} clips in {(time.time() - t0) / 60:.1f} min -> {out_dir.resolve()}")


def _mmss(t: float) -> str:
    return f"{int(t // 60)}:{int(t % 60):02d}"


if __name__ == "__main__":
    main()
