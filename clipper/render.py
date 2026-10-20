"""Cutting, reframing, captioning and exporting each clip with ffmpeg."""

import os
import subprocess
from pathlib import Path

from .reframe import Track, sendcmd_script

OUT_W, OUT_H = 1080, 1920


def render(video: Path, out_file: Path, start: float, end: float, tr: Track,
           ass_text: str | None, work: Path, fps: float, fonts_dir: Path | None = None,
           crf: int = 20, preset: str = "medium", logo: Path | None = None,
           logo_seconds: float = 4.0):
    work.mkdir(parents=True, exist_ok=True)
    # ffmpeg filter paths are awkward on Windows (drive colons), so filter
    # input files are written to `work` and referenced relative to it.
    if tr.layout == "crop":
        (work / "camera.txt").write_text(sendcmd_script(tr))
        x0 = tr.keyframes[0][1]
        video_chain = (f"[0:v]sendcmd=f=camera.txt,crop=w={tr.crop_w}:h=ih:x={x0}:y=0,"
                       f"scale={OUT_W}:{OUT_H}:flags=lanczos,setsar=1")
    else:
        video_chain = (
            f"[0:v]split=2[bg][fg];"
            f"[bg]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,"
            f"crop={OUT_W}:{OUT_H},boxblur=28:4,eq=brightness=-0.08[bgb];"
            f"[fg]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease:flags=lanczos[fgs];"
            f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1"
        )
    if logo:
        # Logo at the top for the first seconds, fading out.
        fade_at = max(0.0, min(logo_seconds, end - start) - 0.5)
        video_chain += (f"[base];[1:v]format=rgba,fade=t=out:st={fade_at:.2f}:d=0.5:alpha=1[lg];"
                        f"[base][lg]overlay=x=(W-w)/2:y=150:eof_action=pass")
    if ass_text:
        (work / "captions.ass").write_text(ass_text, encoding="utf-8")
        fonts = ""
        if fonts_dir and fonts_dir.is_dir():
            try:
                rel = os.path.relpath(fonts_dir.resolve(), work.resolve())
            except ValueError:  # different drive on Windows
                rel = str(fonts_dir.resolve())
            fonts = f":fontsdir='{Path(rel).as_posix()}'"
        video_chain += f",ass=filename=captions.ass{fonts}"
    video_chain += "[v]"

    cmd = [
        "ffmpeg", "-y", "-v", "error", "-stats",
        "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", str(video.resolve()),
        *(["-loop", "1", "-t", f"{min(logo_seconds, end - start):.2f}", "-i",
           str(logo.resolve())] if logo else []),
        "-filter_complex", video_chain,
        "-map", "[v]", "-map", "0:a?",
        "-r", f"{min(fps, 60):.3f}",
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
        "-movflags", "+faststart",
        str(out_file.resolve()),
    ]
    subprocess.run(cmd, cwd=work, check=True)
