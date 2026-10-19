# Free AI Clipper

Turns a long video (podcast, stream, interview) into ready-to-post **vertical
clips** for TikTok, YouTube Shorts and Instagram Reels — the same job as
OpusClip / Vugola, but free, with no watermark and no monthly limit. It all
runs on your own computer.

What it does to every video:

1. **Downloads** it from a link (YouTube, Twitch, Kick, X and
   [many more](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md)) or uses a file you have.
2. **Transcribes** the speech with Whisper (word-by-word timing).
3. **Finds the best moments.** Every 20–60 s stretch of whole sentences is
   scored on what makes clips go viral: a strong hook in the first seconds,
   vocal energy and emphasis, pace, emotional/curiosity words, a complete
   thought with a payoff, and few "um"s or dead air.
   Optionally a free AI model re-ranks the best ones and writes titles.
4. **Reframes to 9:16** following the speaker's face, holding steady and
   cutting cleanly when the shot changes. Videos with no faces (gameplay,
   screen recordings) get a blurred-background layout instead.
5. **Burns in animated captions**: bold, word-by-word, with the spoken word
   highlighted.
6. **Exports** 1080×1920 MP4s with loudness evened out, plus `clips.txt`
   listing each clip's title, score and transcript.

---

## Easiest way on a Mac

1. Install **Homebrew**: open the *Terminal* app, paste the one line shown on
   <https://brew.sh> and press Enter (it asks for your Mac password; typing it
   shows nothing, that's normal). When it finishes, copy and run the
   "Next steps" lines it prints, if any.
2. Download this project (**Code** → **Download ZIP**) and unzip it.
3. **Right-click `Clipper.command` → Open → Open.** (Right-click only the first
   time, because macOS blocks files downloaded from the internet. After that, a
   normal double-click works.)

The first run installs ffmpeg, its own Python 3.12 and everything else by itself. Then it asks for
a link (or drag a video file into the window) and how many clips, and opens
the `clips` folder when it's done. If [Ollama](https://ollama.com) is
installed, it's used automatically for smarter picks and titles.

## Setup (one time, ~10 minutes)

You need a computer (Windows, Mac or Linux). A phone won't work.

### 1. Install Python
Download Python 3.10–3.13 from <https://www.python.org/downloads/>.
On Windows, **tick "Add Python to PATH"** on the first installer screen.

### 2. Install ffmpeg
- **Windows:** open *Command Prompt* and run `winget install ffmpeg`, then close and reopen it.
- **Mac:** install [Homebrew](https://brew.sh), then run `brew install ffmpeg`.
- **Linux:** `sudo apt install ffmpeg`

### 3. Download this project and install its parts
Download the project (green **Code** button → **Download ZIP** on GitHub, then
unzip it), open a terminal / Command Prompt **in that folder**, and run:

```
pip install -r requirements.txt
```

(On Mac/Linux use `pip3` if `pip` isn't found.)

---

## Making clips

```
python -m clipper "https://www.youtube.com/watch?v=VIDEO_ID"
```

Or just run `python -m clipper` and paste the link when it asks.
Your clips appear in the `clips` folder. The first run downloads the
speech model (~500 MB), so it takes longer.

Useful options:

| Option | What it does |
|---|---|
| `-n 10` | make 10 clips (default 6) |
| `--min 15 --max 45` | clip length range in seconds (default 20–60) |
| `--model medium` | more accurate captions (slower). `base` is faster |
| `--language en` | skip language detection |
| `--caption-color green` | `yellow` (default), `green`, `red`, `white` |
| `--title-seconds 3` | show the clip's title at the top for the first 3 s |
| `--layout blur` | always use the blurred-background layout (`center` = plain centre crop) |
| `--no-captions` | no captions (if the campaign gives its own) |
| `--quality fast` | quicker export, slightly bigger files |
| `--dry-run` | just list the moments it would pick |

Example: `python -m clipper podcast.mp4 -n 10 --min 15 --max 45 --title-seconds 3`

**Speed:** a 1-hour video usually takes 10–40 minutes on a normal laptop,
mostly transcription. With an NVIDIA graphics card it's much faster
automatically. Re-running on the same video reuses the transcript.

### Nicer caption font
Captions use *Arial Black* by default. For the classic clipping look,
download a font such as [Montserrat](https://fonts.google.com/specimen/Montserrat)
or [Komika Axis](https://www.dafont.com/komika-axis.font), put the `.ttf`
files in a `fonts` folder inside this project, and pass the font's name,
e.g. `--font "Montserrat Black"`.

---

## Make it smarter with a free AI (recommended)

The built-in scoring works on its own. Adding an AI model makes it pick
moments the way a human editor would (does this make sense on its own? is it
funny? is the ending satisfying?) and write catchy titles. Both options are
free:

**Option A — Ollama (runs on your computer, unlimited, offline)**
1. Install from <https://ollama.com>.
2. Run `ollama pull llama3.1:8b` once.
3. Add `--llm ollama` to your command:
   `python -m clipper "LINK" --llm ollama`

Needs about 8 GB of RAM. Use `--llm-model` to pick a different model.

**Option B — a free online AI API (works on weaker computers)**
Get a free API key from a provider with an OpenAI-compatible API, e.g.
[Groq](https://console.groq.com) or [Google AI Studio](https://aistudio.google.com),
then set these before running (Windows: `set NAME=value`, Mac/Linux: `export NAME=value`):

```
CLIPPER_LLM_BASE_URL=https://api.groq.com/openai/v1
CLIPPER_LLM_API_KEY=your-key-here
```

and run `python -m clipper "LINK" --llm api --llm-model MODEL_NAME`, using a
model name from the provider's docs. For Google use
`https://generativelanguage.googleapis.com/v1beta/openai` as the base URL.
Free-tier limits change, so check the provider's site.

If the AI can't be reached, the clipper says so and carries on with the
built-in scoring.

---

## Tips for Content Rewards campaigns
- **Watch every clip before posting.** Swap in a stronger clip if one needs
  context to make sense. `clips.txt` shows the transcript of each.
- **Read the campaign rules**: required tags, links, or banned edits.
- Long videos give the clipper more to choose from; ask for more clips
  (`-n 15`) and post only the best.
