"""Cut an ElevenLabs voice-over into per-scene clips for make_video.py.

Usage: python eleven_audio.py <voice.wav> <words.json> <script.md> <out_dir>
  voice.wav   the full ElevenLabs narration (48 kHz mono)
  words.json  word timings from faster-whisper: [[start, end, word], ...]
  script.md   ELEVENLABS_SCRIPT.md (13 "## n." sections, narration lines start with **[m:ss.s]**)
For every scene NN it writes scene_NN.wav and scene_NN.json in the same format as narration.py.
The recognised words are aligned to the script, so captions and word keys use the script's spelling.
"""
import json
import re
import sys
import wave
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np


def norm(word):
    return re.sub(r"[^a-z0-9]", "", word.lower())


def script_scenes(md):
    scenes = []
    for line in md.splitlines():
        if line.startswith("## "):
            scenes.append([])
        m = re.match(r"\*\*\[[\d:.]+\]\*\*\s*(.+)", line.strip())
        if m:
            scenes[-1].append(m.group(1).strip())
    return scenes


def align(tokens, heard):
    """Give every script token a (start, end) taken from the recognised words."""
    a, b = [norm(t) for t in tokens], [norm(w[2]) for w in heard]
    times = [None] * len(tokens)
    for op, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                times[i1 + k] = tuple(heard[j1 + k][:2])
        elif op == "replace":  # spread the script tokens over the heard span
            s, e = heard[j1][0], heard[j2 - 1][1]
            n = i2 - i1
            for k in range(n):
                times[i1 + k] = (s + (e - s) * k / n, s + (e - s) * (k + 1) / n)
    for k in range(len(times)):  # tokens the voice skipped: borrow a neighbour's time
        if times[k] is None:
            prev = next((times[j] for j in range(k - 1, -1, -1) if times[j]), (0.0, 0.0))
            times[k] = (prev[1], prev[1])
    return times


def main(voice, words_json, script, out):
    out.mkdir(parents=True, exist_ok=True)
    with wave.open(str(voice)) as wv:
        sr = wv.getframerate()
        pcm = np.frombuffer(wv.readframes(wv.getnframes()), np.int16)
    heard = [w for w in json.loads(words_json.read_text(encoding="utf-8")) if norm(w[2])]
    scenes = script_scenes(script.read_text(encoding="utf-8"))

    tokens, owner = [], []  # owner = (scene, line) of each token
    for n, lines in enumerate(scenes):
        for k, line in enumerate(lines):
            for t in line.split():
                if norm(t):
                    tokens.append(t)
                    owner.append((n, k))
    times = align(tokens, heard)

    firsts = [min(times[i][0] for i, o in enumerate(owner) if o[0] == n) for n in range(len(scenes))]
    lasts = [max(times[i][1] for i, o in enumerate(owner) if o[0] == n) for n in range(len(scenes))]
    total = len(pcm) / sr
    for n, lines in enumerate(scenes):
        a = max(lasts[n - 1] + 0.05 if n else 0.0, firsts[n] - 0.12)
        b = min(firsts[n + 1] - 0.1 if n + 1 < len(scenes) else total, lasts[n] + 0.35)
        clip = pcm[int(a * sr):int(b * sr)].astype(np.float32)
        f = min(len(clip), int(0.012 * sr))  # short fades so the cuts don't click
        clip[:f] *= np.linspace(0, 1, f)
        clip[len(clip) - f:] *= np.linspace(1, 0, f)
        with wave.open(str(out / f"scene_{n + 1:02d}.wav"), "wb") as wv:
            wv.setnchannels(1)
            wv.setsampwidth(2)
            wv.setframerate(sr)
            wv.writeframes(clip.astype(np.int16).tobytes())
        idx = [i for i, o in enumerate(owner) if o[0] == n]
        words = [[round(times[i][0] - a, 3), round(times[i][1] - a, 3), tokens[i].strip(".,!?:;—“”\"")]
                 for i in idx]
        sentences = []
        for k, line in enumerate(lines):
            li = [i for i in idx if owner[i][1] == k]
            sentences.append({"start": round(times[li[0]][0] - a, 3), "end": round(times[li[-1]][1] - a, 3),
                              "text": line})
        (out / f"scene_{n + 1:02d}.json").write_text(
            json.dumps({"duration": round(b - a, 3), "sentences": sentences, "words": words}), encoding="utf-8")
        print(f"scene {n + 1:02d}: {a:6.2f}-{b:6.2f}s  ({b - a:4.1f}s, {len(lines)} lines)")


main(*(Path(p) for p in sys.argv[1:5]))
