# Prompt to rebuild the Free AI Clipper

Build me a free, local "AI clipper" in Python, like OpusClip but with no
watermark, no subscription and no limits. It turns a long video (podcast,
stream, interview) into ready-to-post vertical clips for TikTok, Instagram
Reels and YouTube Shorts. I'm a beginner on a Mac (Apple Silicon), so it must
be usable by double-clicking a file.

## What it does, step by step
1. **Input:** a video link (YouTube, Twitch, Kick, X, etc.) or a local file
   (including one dragged into the Terminal window). Download links with
   yt-dlp at up to 1080p, merged to MP4.
2. **Transcribe** the speech with faster-whisper (default model "small",
   int8 on CPU, CUDA automatically if available), with word-level timestamps
   and the VAD filter on. Cache the transcript as JSON so re-runs skip it.
3. **Find the best moments.** Split words into sentences (punctuation, pauses
   ≥0.8 s, or 40 words). Every window of whole sentences between --min (20 s)
   and --max (60 s) is a candidate. Score each one 0–100 on:
   - a hook in the first ~6 s (questions, hook phrases like "the truth is",
     "nobody", "here's why", numbers, "you", strong/emotional words)
   - loudness of the hook and of the whole clip compared with the speaker's
     normal level, plus loud peaks (laughs, emphasis)
   - speaking pace compared with the video's median
   - emotional/curiosity words, questions, story markers ("I remember")
   - structure: penalize starting on "and/but/so" or on words that need
     context ("it/this/they"), reward ending on . ! ?
   - penalties for filler words ("um", "like", "you know") and dead air
   - a preference for lengths near the middle of the range
   Pick the top N clips that don't overlap.
4. **Optional free AI re-ranking** (--llm): send the best ~3×N candidates'
   text to an LLM that rates each 0–100 for virality and writes a punchy title
   (max 8 words). Final score = 35% built-in + 65% AI. Support two free options
   using only urllib: Ollama on localhost (auto-pick an installed chat model if
   the requested one isn't downloaded; skip embedding models) and any
   OpenAI-compatible API (Groq, Google Gemini, OpenRouter) via environment
   variables CLIPPER_LLM_BASE_URL, CLIPPER_LLM_API_KEY and a model name. If the
   AI can't be reached, say so and continue with the built-in scores.
5. **Reframe to 9:16 (1080×1920).** Detect faces ~5 times a second with OpenCV
   Haar cascades (frontal + profile; pin opencv-python-headless <5 because
   OpenCV 5 removed CascadeClassifier). Turn detections into a steady
   "camera": hold still while the face stays inside a dead zone, re-center only
   after the face has been off-center for ~0.8 s, cut instantly on scene changes
   (histogram difference) or big jumps (another speaker), and ease smoothly
   for small moves. Stick with the same person when several faces are visible.
   Drive ffmpeg's crop filter with a sendcmd file. If faces appear in less than
   30% of samples (gameplay, screen recordings) or the source is already
   vertical, use a "fit" layout instead: the full frame centered over a
   blurred, darkened copy of itself.
6. **Animated captions:** generate an ASS subtitle file with bold, ALL-CAPS,
   word-by-word captions: 1–3 words at a time (max ~18 characters, break at
   punctuation and pauses), the spoken word highlighted in yellow (#FFE500) and
   slightly enlarged, with a black outline, a small pop animation, at ~70% of
   the screen height. Options: color (yellow/green/red/white), font, size,
   position, normal case, and an optional title shown at the top for the first
   few seconds. Support a `fonts/` folder via the ass filter's fontsdir.
7. **Export** each clip with ffmpeg: libx264 (CRF 20, yuv420p, faststart),
   AAC 160k, loudness normalized to -14 LUFS (loudnorm). Write named filter
   options (e.g. `ass=filename=captions.ass`) and reference filter input files
   relative to a work folder (avoids Windows drive-colon problems). If one clip
   fails, print a message and continue with the rest.
8. **Output:** a folder per video with `01_<title>.mp4`, …, plus `clips.json`
   and `clips.txt` listing each clip's title, score, timestamps and transcript.

## Command-line options
`python -m clipper [link-or-file] -n 6 --min 20 --max 60 --model small
--language en --llm ollama|api --llm-model NAME --layout auto|face|center|blur
--no-captions --caption-color yellow --font "Arial Black" --font-size 84
--caption-pos 0.70 --lowercase --title-seconds 0 --quality fast|good|best
--dry-run -o clips --work work`. If no source is given, ask for one.

## Style analyzer (second tool)
`python -m clipper.analyze LINK` downloads a reference Short and writes to
`style/<name>/`: a 4×3 grid of 12 frames from the first 6 s (the hook), a 4×4
grid of 16 frames across the whole video, and `report.txt` with length,
resolution, scene-cut times (ffmpeg scene detection), words per second, and a
timed transcript. These can be shared with an AI that can't watch video, so it
can copy the style.

## Mac double-click launchers (very important lessons)
Make `Clipper.command` and `Analyze Style.command` (executable bash scripts):
- Add /opt/homebrew/bin to PATH. If Homebrew is missing, open brew.sh and explain.
- Install with Homebrew if missing: **ffmpeg-full** (the plain `ffmpeg`
  formula has no libass, so captions fail; ffmpeg-full is keg-only, so add
  `$(brew --prefix)/opt/ffmpeg-full/bin` to PATH), **python@3.12** (a brand-new
  system Python has no prebuilt wheels and PyAV fails to build), and **deno**
  (yt-dlp needs a JavaScript runtime for YouTube).
- Create `.venv` with Python 3.12 and install requirements using prebuilt
  wheels only (`--only-binary=av,ctranslate2,numpy,opencv-python-headless`);
  write a `.venv/.installed` marker so setup runs once.
- On every run, update yt-dlp to the newest pre-release:
  `pip install -U --pre "yt-dlp[default]"`.
- Ask for a link or dragged file (strip quotes and unescape `\ ` spaces),
  ask how many clips, use `--llm ollama` automatically if Ollama is installed,
  then open the clips folder.

## Robustness lessons to build in
- **YouTube 403s:** retry the download with other YouTube player clients
  (default → web_embedded/web/tv → tv → web_safari/mweb), hide yt-dlp's raw
  errors, and finish with a friendly message suggesting trying later or
  dragging in a file downloaded another way.
- **PyAV:** don't let faster-whisper open the file through PyAV (newer PyAV
  removed an argument it passes). Decode the audio with the ffmpeg command
  line to 16 kHz mono float32 numpy and pass the array to Whisper.
- **Duplicate ffmpeg libraries:** PyAV and OpenCV each bundle ffmpeg dylibs that
  clash on macOS, so run Whisper in a separate subprocess
  (`python -m clipper.transcribe`) and never import faster-whisper in the main
  process.
- Read audio loudness in streaming chunks so 3-hour videos don't use lots of
  memory.
- Check at startup that ffmpeg/ffprobe exist and that ffmpeg has the `ass`
  filter (unless --no-captions), with clear instructions if not.

## Files
`requirements.txt` (faster-whisper, opencv-python-headless>=4.8,<5, numpy,
yt-dlp[default]), `clipper/` package (`__main__.py`, `media.py`,
`transcribe.py`, `highlights.py`, `llm.py`, `reframe.py`, `captions.py`,
`render.py`, `analyze.py`), the two `.command` launchers, a beginner-friendly
README with Mac setup steps, and a .gitignore for clips/, work/, style/,
.venv/ and video files.
