"""Optional AI re-ranking with a free LLM.

Two free ways to run it:
  * Ollama on your own computer (fully free, offline):  --llm ollama
  * Any OpenAI-compatible API with a free tier (Groq, Google Gemini,
    OpenRouter free models):  --llm api  with CLIPPER_LLM_BASE_URL,
    CLIPPER_LLM_API_KEY and --llm-model set.
"""

import json
import os
import re
import urllib.error
import urllib.request

PROMPT = """You are an expert short-form video editor who picks clips that go viral \
on TikTok, YouTube Shorts and Instagram Reels.

Below are candidate clips cut from one long video. Rate each from 0 to 100 on how \
likely it is to get views as a standalone vertical clip. Reward: a hook in the \
first sentence that stops scrolling, a single clear idea or story, emotion, \
humour, surprise, controversy or a useful insight, and a satisfying ending. \
Punish: clips that need earlier context to make sense, rambling, starting or \
ending mid-thought, and small talk.

For each clip also write a short, punchy title (max 8 words, no hashtags, no \
quotes) that would make someone watch.

Reply with JSON only, in exactly this shape:
{{"clips": [{{"id": 0, "score": 87, "title": "...", "reason": "one short sentence"}}]}}

Candidates:
{candidates}
"""


def _post(url: str, payload: dict, headers: dict, timeout: int = 600) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", **headers},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _ollama_host() -> str:
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    return host if host.startswith("http") else f"http://{host}"


def _ollama_model(wanted: str | None) -> str:
    """The requested model if it's downloaded, else the best one that is."""
    with urllib.request.urlopen(f"{_ollama_host()}/api/tags", timeout=10) as resp:
        installed = [m["name"] for m in json.loads(resp.read()).get("models", [])]
    if not installed:
        raise RuntimeError("Ollama has no models yet - run: ollama pull llama3.1:8b")
    wanted = wanted or "llama3.1:8b"
    for name in installed:
        if name == wanted or name.split(":")[0] == wanted.split(":")[0]:
            return name
    usable = [n for n in installed if "embed" not in n]
    if not usable:
        raise RuntimeError("Ollama has no chat models - run: ollama pull llama3.1:8b")
    print(f"  ('{wanted}' isn't downloaded in Ollama, using '{usable[0]}')")
    return usable[0]


def _ask(provider: str, model: str | None, prompt: str) -> str:
    if provider == "ollama":
        data = _post(f"{_ollama_host()}/api/chat", {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.2, "num_ctx": 16384},
        }, {})
        return data["message"]["content"]

    base = os.environ.get("CLIPPER_LLM_BASE_URL", "").rstrip("/")
    key = os.environ.get("CLIPPER_LLM_API_KEY", "")
    model = model or os.environ.get("CLIPPER_LLM_MODEL")
    if not (base and key and model):
        raise RuntimeError("set CLIPPER_LLM_BASE_URL, CLIPPER_LLM_API_KEY and --llm-model "
                           "(or CLIPPER_LLM_MODEL)")
    data = _post(f"{base}/chat/completions", {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }, {"Authorization": f"Bearer {key}"})
    return data["choices"][0]["message"]["content"]


def _parse(reply: str) -> list[dict]:
    match = re.search(r"\{.*\}", reply, re.S)
    if not match:
        raise ValueError("no JSON in reply")
    data = json.loads(match.group(0))
    return data.get("clips", data if isinstance(data, list) else [])


def rerank(clips, provider: str, model: str | None, batch: int = 10) -> bool:
    """Score clips in place with the LLM. Returns False if the LLM was unreachable."""
    if provider == "ollama":
        try:
            model = _ollama_model(model)
        except (urllib.error.URLError, RuntimeError, TimeoutError) as e:
            print(f"AI step skipped ({e}). Using the built-in scoring only.")
            return False
    print(f"Asking the AI ({model or provider}) to rate {len(clips)} candidate clips ...")
    for b in range(0, len(clips), batch):
        group = clips[b:b + batch]
        listing = "\n\n".join(
            f"[id {i}] ({c.duration:.0f}s) {c.text[:1500]}" for i, c in enumerate(group)
        )
        try:
            results = _parse(_ask(provider, model, PROMPT.format(candidates=listing)))
        except (urllib.error.URLError, RuntimeError, ValueError, KeyError,
                json.JSONDecodeError, TimeoutError) as e:
            print(f"  AI step skipped ({e}). Using the built-in scoring only.")
            return False
        for r in results:
            try:
                c = group[int(r["id"])]
                c.llm_score = float(r["score"])
            except (KeyError, ValueError, IndexError, TypeError):
                continue
            c.title = str(r.get("title", "")).strip().strip('"') or c.title
            c.reason = str(r.get("reason", "")).strip()
    for c in clips:
        if c.llm_score is not None:
            c.score = 0.35 * c.heuristic + 0.65 * c.llm_score
    return True
