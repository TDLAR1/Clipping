"""Turning a wide video into a vertical one that follows the speaker.

Faces are detected a few times per second, then turned into a steady "camera":
it holds still while the face stays in frame, re-centres only when the person
really moves, and cuts instantly on scene changes or when the shot jumps to
someone else. That holds-then-cuts style is what the paid AI clippers do and
looks far better than a camera that wobbles after every head movement.
"""

from dataclasses import dataclass

import cv2
import numpy as np

SAMPLE_FPS = 5
DETECT_WIDTH = 480


@dataclass
class Track:
    layout: str                 # "crop" (follow the face), "fit" (blurred background) or "split"
    crop_w: int = 0
    keyframes: list = None      # [(time_in_clip, x_pixels)]
    face_ratio: float = 0.0
    cam: tuple = None           # split: facecam box (x, y, w, h) in source pixels
    game: tuple = None          # split: gameplay box (x, y, w, h) in source pixels
    webcam_shots: list = None   # split: [(t0, t1, crop_x)] where the whole frame is the webcam


def _detectors():
    base = cv2.data.haarcascades
    front = cv2.CascadeClassifier(base + "haarcascade_frontalface_default.xml")
    profile = cv2.CascadeClassifier(base + "haarcascade_profileface.xml")
    return front, profile


def _faces(gray, front, profile, min_size):
    found = []
    for det, flip in ((front, False), (profile, False), (profile, True)):
        img = cv2.flip(gray, 1) if flip else gray
        boxes = det.detectMultiScale(img, scaleFactor=1.1, minNeighbors=6,
                                     minSize=(min_size, min_size))
        for (x, y, w, h) in boxes:
            if flip:
                x = gray.shape[1] - x - w
            found.append((x + w / 2, w))
        if found and det is front:
            break  # frontal hits are the most reliable; skip profile search
    return found


def _sample(video_path, start, end):
    """Yield (time_in_clip, small_gray_frame) about SAMPLE_FPS times a second."""
    cap = cv2.VideoCapture(str(video_path))
    cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    step = max(1, round(fps / SAMPLE_FPS))
    i = 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
        if t > end:
            break
        if True:  # every frame, so the layout switches exactly on the cut
            ok, frame = cap.retrieve()
            if ok:
                h, w = frame.shape[:2]
                scale = DETECT_WIDTH / w
                small = cv2.resize(frame, (DETECT_WIDTH, int(h * scale)))
                yield max(0.0, t - start), cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), scale
        i += 1
    cap.release()


def _pick_targets(samples, frame_w):
    """One face x-position (or None) per sample, preferring to stay on the same person."""
    targets, prev = [], None
    for faces in samples:
        if not faces:
            targets.append(None)
            continue
        biggest = max(f[1] for f in faces)
        choice = max(faces, key=lambda f: f[1])
        if prev is not None:
            near = [f for f in faces if abs(f[0] - prev) < frame_w * 0.12 and f[1] > 0.6 * biggest]
            if near:
                choice = near[0]
        prev = choice[0]
        targets.append(prev)
    # Fill short detection dropouts (<1.2 s) with the last known position.
    last, gap = None, 0
    for i, t in enumerate(targets):
        if t is None:
            gap += 1
            if last is not None and gap <= SAMPLE_FPS * 1.2:
                targets[i] = last
        else:
            last, gap = t, 0
    return targets


def split_boxes(cam, frame_w, frame_h, out_w=1080, out_h=1920):
    """Facecam on top, gameplay below: pick the gameplay crop that fills the rest.

    The gameplay crop is full height and kept clear of the facecam when it sits
    at a side, so the streamer doesn't appear twice."""
    cx, cy, cw, ch = cam
    top_h = int(round(out_w * ch / cw / 2) * 2)
    game_w = min(frame_w, int(round(frame_h * out_w / (out_h - top_h) / 2) * 2))
    game_x = (frame_w - game_w) // 2
    if cx + cw / 2 > frame_w / 2:
        game_x = min(game_x, cx - game_w)
    else:
        game_x = max(game_x, cx + cw)
    game_x = int(np.clip(game_x, 0, frame_w - game_w))
    return top_h, (game_x, 0, game_w, frame_h)


def webcam_shots(video_path, start, end, frame_w, frame_h, crop_w, sat_limit=90):
    """Find the stretches where a gaming video cuts to the streamer's webcam full screen.

    Gameplay is far more colourful than a room, so each frame's saturation away
    from the facecam corner tells the two apart. Returns [(t0, t1, crop_x)] in
    clip time, with crop_x centred on the streamer's face."""
    front, profile = _detectors()
    cap = cv2.VideoCapture(str(video_path))
    cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    times, is_cam, frames = [], [], {}
    while True:
        # Every frame, so the layout switches exactly on the cut.
        ok, frame = cap.read()
        if not ok:
            break
        t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
        if t > end:
            break
        small = cv2.resize(frame, (192, 108), interpolation=cv2.INTER_AREA)
        sat = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)[30:, :120, 1].mean()
        times.append(t - start)
        is_cam.append(sat < sat_limit)
        if len(times) % round(fps / 2) == 0:  # a face sample about twice a second
            frames[len(times) - 1] = cv2.cvtColor(
                cv2.resize(frame, (DETECT_WIDTH, DETECT_WIDTH * frame_h // frame_w)),
                cv2.COLOR_BGR2GRAY)
    cap.release()
    if not times:
        return []
    # Smooth single-frame blips (a white flash in the game, a colourful shirt).
    flags = np.array(is_cam, dtype=float)
    k = 7
    padded = np.pad(flags, k // 2, mode="edge")
    flags = np.array([np.median(padded[j:j + k]) for j in range(len(flags))]) > 0.5

    runs, j = [], 0
    while j < len(flags):
        if not flags[j]:
            j += 1
            continue
        a = j
        while j < len(flags) and flags[j]:
            j += 1
        runs.append((a, j))
    if not runs:
        return []
    # The streamer sits still, and single detections are noisy, so one steady
    # crop for the whole clip (the median face position) looks best.
    scale = frame_w / DETECT_WIDTH
    xs = []
    for a, b in runs:
        for idx in range(a, b):
            if idx in frames:
                found = _faces(frames[idx], front, profile, 24)
                if found:
                    xs.append(max(found, key=lambda f: f[1])[0] * scale)
    face_x = float(np.median(xs)) if xs else frame_w / 2
    crop_x = int(np.clip(face_x - crop_w / 2, 0, frame_w - crop_w))
    # Switch halfway between the last frame of one shot and the first of the next.
    edge = lambda k: round((times[k - 1] + times[k]) / 2, 3)
    return [(edge(a) if a > 0 else 0.0, edge(b) if b < len(times) else round(end - start + 1, 3),
             crop_x) for a, b in runs]


def track(video_path, start, end, frame_w, frame_h, layout="auto", cam=None) -> Track:
    out_ratio = 9 / 16
    if frame_w / frame_h <= out_ratio + 0.01 or layout == "blur":
        return Track("fit")
    crop_w = int(round(frame_h * out_ratio / 2) * 2)
    if layout == "split":
        return Track("split", crop_w, cam=cam, game=split_boxes(cam, frame_w, frame_h)[1],
                     webcam_shots=webcam_shots(video_path, start, end, frame_w, frame_h, crop_w))
    center_x = (frame_w - crop_w) // 2
    if layout == "center":
        return Track("crop", crop_w, [(0.0, center_x, "cut")], 0.0)

    front, profile = _detectors()
    times, faces, cuts, prev_hist = [], [], [], None
    for t, gray, scale in _sample(video_path, start, end):
        min_size = max(24, int(gray.shape[0] * 0.08))
        faces.append([(x / scale, w / scale) for x, w in _faces(gray, front, profile, min_size)])
        hist = cv2.calcHist([gray], [0], None, [32], [0, 256])
        cv2.normalize(hist, hist)
        cuts.append(prev_hist is not None and
                    cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL) < 0.6)
        prev_hist = hist
        times.append(t)

    if not times:
        return Track("crop", crop_w, [(0.0, center_x, "cut")], 0.0)
    face_ratio = sum(bool(f) for f in faces) / len(faces)
    if layout == "auto" and face_ratio < 0.3:
        return Track("fit", face_ratio=face_ratio)

    targets = _pick_targets(faces, frame_w)
    max_x = frame_w - crop_w

    def to_x(face_center):
        return int(np.clip(face_center - crop_w / 2, 0, max_x))

    def settle(i):
        """Where to put the camera from sample i: median face position over the next ~1 s."""
        window = [t for t in targets[i:i + SAMPLE_FPS] if t is not None]
        return to_x(float(np.median(window))) if window else None

    keyframes = []
    cam = next((settle(i) for i in range(len(targets)) if settle(i) is not None), center_x)
    keyframes.append((0.0, cam, "cut"))
    dead_zone = crop_w * 0.22        # face may drift this far from centre before we move
    patience = int(SAMPLE_FPS * 0.8)  # ...for this many samples in a row
    drift = 0
    for i in range(1, len(times)):
        if cuts[i]:
            new = settle(i)
            if new is not None and new != cam:
                cam = new
                keyframes.append((times[i], cam, "cut"))
            drift = 0
            continue
        t = targets[i]
        if t is None or abs(to_x(t) - cam) <= dead_zone:
            drift = 0
            continue
        drift += 1
        if drift >= patience:
            new = settle(i - patience + 1) or to_x(t)
            jump = abs(new - cam)
            kind = "cut" if jump > crop_w * 0.6 else "ease"
            cam = new
            keyframes.append((times[i - patience + 1], cam, kind))
            drift = 0
    return Track("crop", crop_w, keyframes, face_ratio)


def sendcmd_script(tr: Track, ease_time: float = 0.45, step: float = 0.04) -> str:
    """ffmpeg sendcmd lines that move the crop window along the camera path."""
    lines = []
    cam = tr.keyframes[0][1]
    lines.append(f"0.0 crop x {cam};")
    for kf in tr.keyframes[1:]:
        t, x, kind = kf
        if kind == "cut":
            lines.append(f"{t:.3f} crop x {x};")
        else:
            n = max(1, int(ease_time / step))
            for k in range(1, n + 1):
                p = k / n
                p = p * p * (3 - 2 * p)  # smoothstep
                lines.append(f"{t + k * step:.3f} crop x {int(cam + (x - cam) * p)};")
        cam = x
    return "\n".join(lines) + "\n"
