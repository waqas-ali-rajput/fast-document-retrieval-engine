"""Motion-graphics explainer for the CS-251 PBL (renders frames with Pillow, encodes with ffmpeg).

  python make_video.py frames <scene> <t1> [t2 ...]   save preview PNGs to build/preview/
  python make_video.py render [scene ...]             render silent scene clips to build/clips/
  python make_video.py final                          build audio track, join clips -> PBL_video_v2.mp4

Voice-over and timings come from build/audio_eleven (eleven_audio.py); set VOICE_DIR=audio for narration.py clips.
"""
import json
import math
import os
import random
import re
import subprocess
import sys
import wave
from functools import lru_cache
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent.parent
BUILD = ROOT / "build"
# voice-over clips: build/audio_eleven (ElevenLabs, cut by eleven_audio.py) or build/audio (narration.py)
AUDIO = BUILD / os.environ.get("VOICE_DIR", "audio_eleven")
CLIPS = BUILD / "clips"
SHOTS = PROJECT / "Screenshots"

W, H, FPS = 1920, 1080, 30
LEAD, TAIL = 0.6, 0.9

BG = (11, 11, 14)
CARD = (23, 23, 28)
CARD2 = (32, 32, 39)
LINE = (54, 54, 64)
TEXT = (238, 238, 242)
MUTED = (138, 141, 154)
DIM = (80, 82, 94)
ORANGE = (234, 118, 60)
GREEN = (46, 190, 116)
RED = (230, 76, 76)
BLUE = (96, 152, 255)

FONTS = Path(r"C:\Windows\Fonts")
FONT_FILES = {"reg": "segoeui.ttf", "semi": "seguisb.ttf", "bold": "segoeuib.ttf", "light": "segoeuil.ttf",
              "mono": "consola.ttf", "monob": "consolab.ttf", "sym": "seguisym.ttf"}


# ----------------------------------------------------------------------------- helpers
@lru_cache(None)
def font(kind, size):
    f = FONTS / FONT_FILES[kind]
    if not f.exists():
        f = FONTS / "segoeuib.ttf"
    return ImageFont.truetype(str(f), size)


def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def prog(t, t0, d):
    return clamp((t - t0) / d) if d > 0 else float(t >= t0)


def eo(x):
    return 1 - (1 - x) ** 3


def eio(x):
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def back(x):
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def lerp(a, b, x):
    return a + (b - a) * x


def mix(c1, c2, x):
    return tuple(int(lerp(a, b, x)) for a, b in zip(c1, c2))


def rgba(c, a=1.0):
    return (c[0], c[1], c[2], int(255 * clamp(a)))


@lru_cache(None)
def txt(s, size, color=TEXT, kind="reg"):
    f = font(kind, size)
    l, t, r, b = f.getbbox(s)
    asc, desc = f.getmetrics()
    im = Image.new("RGBA", (max(1, r - l + 4), asc + desc + 4), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((2 - l, 2), s, font=f, fill=rgba(color))
    return im


@lru_cache(None)
def rrect(w, h, r, fill, outline=None, ow=2, fill_a=1.0, out_a=1.0):
    k = 3
    im = Image.new("RGBA", (w * k, h * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w * k - 1, h * k - 1), r * k, fill=rgba(fill, fill_a) if fill else None,
                        outline=rgba(outline, out_a) if outline else None, width=ow * k if outline else 0)
    return im.resize((w, h), Image.LANCZOS)


@lru_cache(None)
def disc(d, fill, outline=None, ow=2):
    k = 3
    im = Image.new("RGBA", (d * k, d * k), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse((0, 0, d * k - 1, d * k - 1), fill=rgba(fill),
                               outline=rgba(outline) if outline else None, width=ow * k if outline else 0)
    return im.resize((d, d), Image.LANCZOS)


def fade(sp, a):
    if a >= 0.999:
        return sp
    sp = sp.copy()
    sp.putalpha(sp.getchannel("A").point(lambda v: int(v * a)))
    return sp


def blit(cv, sp, x, y, a=1.0, s=1.0, anchor="c"):
    if a <= 0.01 or s <= 0.01:
        return
    if abs(s - 1) > 0.002:
        sp = sp.resize((max(1, int(sp.width * s)), max(1, int(sp.height * s))), Image.BILINEAR)
    sp = fade(sp, a)
    w, h = sp.size
    if anchor == "c":
        x0, y0 = x - w / 2, y - h / 2
    elif anchor == "lc":
        x0, y0 = x, y - h / 2
    elif anchor == "rc":
        x0, y0 = x - w, y - h / 2
    else:
        x0, y0 = x, y
    x0, y0 = int(round(x0)), int(round(y0))
    cx0, cy0, cx1, cy1 = max(0, x0), max(0, y0), min(W, x0 + w), min(H, y0 + h)
    if cx1 <= cx0 or cy1 <= cy0:
        return
    cv.alpha_composite(sp.crop((cx0 - x0, cy0 - y0, cx1 - x0, cy1 - y0)), (cx0, cy0))


def draw(cv):
    return ImageDraw.Draw(cv, "RGBA")


def chip(s, size=26, color=TEXT, fill=CARD2, outline=LINE, kind="semi", padx=18, h=None):
    t = txt(s, size, color, kind)
    hh = h or int(size * 1.9)
    w = t.width + 2 * padx
    base = rrect(w, hh, hh // 2, fill, outline, 2).copy()
    base.alpha_composite(t, ((w - t.width) // 2, (hh - t.height) // 2))
    return base


@lru_cache(None)
def chip_c(s, size=26, color=TEXT, fill=CARD2, outline=LINE, kind="semi", padx=18, h=None):
    return chip(s, size, color, fill, outline, kind, padx, h)


def arrow(cv, x1, y1, x2, y2, color=MUTED, a=1.0, width=3, head=12, p=1.0):
    if p <= 0:
        return
    x2, y2 = lerp(x1, x2, p), lerp(y1, y2, p)
    d = draw(cv)
    d.line((x1, y1, x2, y2), fill=rgba(color, a), width=width)
    ang = math.atan2(y2 - y1, x2 - x1)
    pts = [(x2, y2), (x2 - head * math.cos(ang - 0.45), y2 - head * math.sin(ang - 0.45)),
           (x2 - head * math.cos(ang + 0.45), y2 - head * math.sin(ang + 0.45))]
    d.polygon(pts, fill=rgba(color, a))


def wrap(s, f, maxw):
    lines, cur = [], ""
    for w in s.split():
        test = (cur + " " + w).strip()
        if f.getlength(test) <= maxw or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


@lru_cache(None)
def para(s, size, color, kind, maxw, spacing=1.25):
    f = font(kind, size)
    lines = wrap(s, f, maxw)
    lh = int(size * spacing)
    w = int(max(f.getlength(l) for l in lines)) + 6
    im = Image.new("RGBA", (w, lh * len(lines) + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for i, l in enumerate(lines):
        d.text((3, i * lh), l, font=f, fill=rgba(color))
    return im


# ----------------------------------------------------------------------------- background / timing
@lru_cache(None)
def background():
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((x - W * 0.5) / W) ** 2 + ((y - H * 0.42) / H) ** 2)
    g = np.clip(1 - r * 1.25, 0, 1) ** 1.6
    img = np.zeros((H, W, 3), np.float32)
    for i, (b, c) in enumerate(zip(BG, (24, 22, 26))):
        img[..., i] = b + (c - b) * g
    dots = ((x % 40 == 0) & (y % 40 == 0))
    img[dots] += 16
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    return im


class Meta:
    def __init__(self, n):
        m = json.loads((AUDIO / f"scene_{n:02d}.json").read_text(encoding="utf-8"))
        self.audio = m["duration"]
        self.sent = m["sentences"]
        self.words = m["words"]
        extra = 2.2 if n == 13 else 0.0
        self.frames = int(round((LEAD + self.audio + TAIL + extra) * FPS))
        self.dur = self.frames / FPS

    def w(self, word, nth=1, default=None):
        k = 0
        for s, e, x in self.words:
            if re.sub(r"[^a-z0-9]", "", x.lower()).startswith(word.lower()):
                k += 1
                if k == nth:
                    return LEAD + s
        if default is None:
            raise KeyError(word)
        return default

    def s(self, i):
        return LEAD + self.sent[i]["start"]

    def e(self, i):
        return LEAD + self.sent[i]["end"]


def header(cv, n):
    blit(cv, disc(12, ORANGE), 64, 52)
    blit(cv, txt("FAST DOCUMENT RETRIEVAL ENGINE", 20, MUTED, "semi"), 82, 52, anchor="lc")
    blit(cv, txt(f"CS-251 PBL  ·  MUET CSE  ·  {n:02d}/13", 20, DIM, "semi"), W - 64, 52, anchor="rc")


@lru_cache(None)
def caption_text(s, size=40, stroke=4):
    """Big bold white subtitle with a black outline, lines centred, no box."""
    f = font("bold", size)
    lines = wrap(s, f, 1720)
    lh = int(size * 1.2)
    w = int(max(f.getlength(l) for l in lines)) + 2 * stroke + 8
    im = Image.new("RGBA", (w, lh * len(lines) + 2 * stroke + 12), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for i, l in enumerate(lines):
        d.text((w / 2, stroke + 2 + i * lh), l, font=f, fill=rgba(TEXT), anchor="ma", stroke_width=stroke,
               stroke_fill=(0, 0, 0, 255))
    return im


def captions(cv, t, m):
    for i, s in enumerate(m.sent):
        t0, t1 = LEAD + s["start"] - 0.05, LEAD + s["end"] + 0.18
        if t0 <= t <= t1:
            a = min(prog(t, t0, 0.15), 1 - prog(t, t1 - 0.12, 0.12))
            p = caption_text(s["text"])
            blit(cv, p, W / 2, 1040 - p.height / 2, a)


# ----------------------------------------------------------------------------- scene 1: hook
@lru_cache(None)
def dot_text(segments, size, step):
    """segments: tuple of (text, color). Returns list of (x, y, color) dot centres, width, height."""
    f = font("bold", size)
    total = sum(f.getlength(s) for s, _ in segments)
    mask_h = int(size * 1.3)
    dots, x = [], 0
    for s, color in segments:
        w = int(f.getlength(s)) + 4
        m = Image.new("L", (w, mask_h), 0)
        ImageDraw.Draw(m).text((0, 0), s, font=f, fill=255)
        a = np.array(m)
        for yy in range(step // 2, mask_h, step):
            for xx in range(step // 2, w, step):
                if a[yy, xx] > 120:
                    dots.append((x + xx, yy, color))
        x += f.getlength(s)
    return dots, total, mask_h


def draw_dots(cv, segs, cx, cy, t, t_in, t_out, seed, size=150, step=10):
    dots, tw, th = dot_text(segs, size, step)
    rnd = random.Random(seed)
    d = draw(cv)
    for (x, y, color) in dots:
        delay = rnd.random() * 0.55
        ox, oy = rnd.uniform(-40, 40), rnd.uniform(-40, 40)
        ang = rnd.uniform(0, 2 * math.pi)
        p = eo(prog(t, t_in + delay, 0.5))
        q = eio(prog(t, t_out + delay * 0.6, 0.7))
        if p <= 0 or q >= 1:
            continue
        px = cx - tw / 2 + x + ox * (1 - p) + math.cos(ang) * 260 * q
        py = cy - th / 2 + y + oy * (1 - p) + math.sin(ang) * 260 * q
        r = 3.3 * p * (1 - q)
        d.ellipse((px - r, py - r, px + r, py + r), fill=rgba(color, p * (1 - q)))


def scene1(cv, t, m):
    t_q = m.w("question") - 0.2
    t_n = m.w("155") - 0.3
    t_out = m.s(2) - 0.2
    draw_dots(cv, (("1", ORANGE), (" question.", TEXT)), W / 2, 330, t, t_q, t_out, 1)
    draw_dots(cv, (("155", ORANGE), (" notices.", TEXT)), W / 2, 560, t, t_n, t_out, 2)
    p = eo(prog(t, t_out + 0.35, 0.8))
    if p > 0:
        blit(cv, txt("Fast Document Retrieval Engine", 92, TEXT, "bold"), W / 2, 400 + 30 * (1 - p), p)
        blit(cv, txt("for a University RAG Assistant", 44, MUTED, "reg"), W / 2, 500 + 30 * (1 - p), p)
        u = eio(prog(t, t_out + 0.7, 0.7))
        draw(cv).rounded_rectangle((W / 2 - 330, 560, W / 2 - 330 + 660 * u, 566), 3, fill=rgba(ORANGE))
    for i, (word, label) in enumerate((("quickly", "find it quickly"), ("show", "show where it came from"))):
        q = back(prog(t, m.w(word) - 0.1, 0.45))
        if q > 0:
            blit(cv, chip_c(label, 28, ORANGE, CARD, ORANGE), W / 2 + (i * 2 - 1) * 230, 660, clamp(q), 0.6 + 0.4 * q)


# ----------------------------------------------------------------------------- scene 2: team
TEAM = [("WA", "Waqas Ali", "25CS061", "Lead · integration · tests"),
        ("MA", "Mehran Ali", "25CS009", "Hash table · inverted index"),
        ("GA", "Gaffar", "25CS067", "Ranking · heap · merge sort"),
        ("BA", "Basit Azam", "25CS113", "Dataset · queries · tokenizer")]


@lru_cache(None)
def member_card(i):
    ini, name, roll, role = TEAM[i]
    c = rrect(400, 270, 26, CARD, LINE, 2).copy()
    av = disc(104, ORANGE)
    c.alpha_composite(av, (148, 26))
    it = txt(ini, 40, (255, 255, 255), "bold")
    c.alpha_composite(it, (200 - it.width // 2, 78 - it.height // 2))
    for s, y in ((txt(name, 34, TEXT, "bold"), 150), (txt(roll, 27, ORANGE, "monob"), 196),
                 (txt(role, 22, MUTED, "reg"), 234)):
        c.alpha_composite(s, (200 - s.width // 2, y - s.height // 2))
    return c


def scene2(cv, t, m):
    rows = [(m.s(0) + 0.05, txt("CS-251 · Data Structures and Algorithms", 56, TEXT, "bold"), 170),
            (m.w("project") - 0.1, chip_c("Project-Based Learning (PBL)", 26, ORANGE, CARD, ORANGE), 248),
            (m.w("department"), txt("Department of Computer Systems Engineering", 40, TEXT, "semi"), 322),
            (m.w("muet"), txt("Mehran University of Engineering and Technology, Jamshoro", 32, MUTED, "reg"), 372),
            (m.w("dr"), None, 430)]
    for t0, sp, y in rows:
        p = eo(prog(t, t0, 0.5))
        if p <= 0:
            continue
        if sp is None:
            a = txt("Subject teacher:  ", 32, MUTED, "reg")
            b = txt("Dr. Ali Asghar Manjotho", 32, ORANGE, "semi")
            x0 = W / 2 - (a.width + b.width) / 2
            blit(cv, a, x0, y + 20 * (1 - p), p, anchor="lc")
            blit(cv, b, x0 + a.width, y + 20 * (1 - p), p, anchor="lc")
        else:
            blit(cv, sp, W / 2, y + 20 * (1 - p), p)
    starts = [m.w("waqas"), m.w("mehran"), m.w("gaffar"), m.w("basit")]
    for i, t0 in enumerate(starts):
        t0 -= 0.15
        p = prog(t, t0, 0.38)
        if p <= 0:
            continue
        x = 300 + i * 440
        blit(cv, member_card(i), x, 680, clamp(p * 2), 1.25 - 0.25 * back(p))
        f = 1 - prog(t, t0 + 0.05, 0.3)
        if 0 < f < 1:
            blit(cv, rrect(400, 270, 26, (255, 255, 255)), x, 680, 0.55 * f)


# ----------------------------------------------------------------------------- scene 3: RAG
def scene3(cv, t, m):
    t_exp = m.w("retrieval") - 0.15
    a1 = prog(t, 0.2, 0.5) * (1 - prog(t, t_exp, 0.35))
    blit(cv, txt("RAG", 170, TEXT, "bold"), W / 2, 230, a1, 1 + 0.15 * prog(t, t_exp, 0.35))
    p = eo(prog(t, t_exp + 0.2, 0.6))
    if p > 0:
        r = txt("Retrieval", 64, (20, 14, 10), "bold")
        rest = txt("-Augmented Generation", 64, TEXT, "bold")
        total = r.width + 24 + rest.width
        x0 = W / 2 - total / 2
        blit(cv, rrect(r.width + 24, 92, 16, ORANGE), x0, 220, p, anchor="lc")
        blit(cv, r, x0 + 12, 222, p, anchor="lc")
        blit(cv, rest, x0 + r.width + 24, 222, p, anchor="lc")
    # flow: question -> retrieval (ours) -> answer
    t_flow = m.w("finds")
    boxes = [("Question", TEXT, LINE, 520), ("Retrieval  (our project)", ORANGE, ORANGE, 960),
             ("LLM writes answer", DIM, LINE, 1400)]
    for i, (label, col, out, x) in enumerate(boxes):
        q = back(prog(t, t_flow + i * 0.35, 0.45))
        if q > 0:
            blit(cv, chip_c(label, 28, col, CARD, out, padx=28, h=70), x, 370, clamp(q), 0.7 + 0.3 * q)
        if i:
            arrow(cv, boxes[i - 1][3] + 150, 370, x - 175, 370, MUTED, 1, 3, 12, eo(prog(t, t_flow + i * 0.35, 0.4)))
    # evidence card
    t_card = m.s(2) - 0.1
    shift = eio(prog(t, m.s(3) - 0.1, 0.6))
    cx = lerp(960, 620, shift)
    p = eo(prog(t, t_card, 0.5))
    if p > 0:
        blit(cv, rrect(900, 380, 26, CARD, LINE, 2), cx, 700 + 30 * (1 - p), p)
        top = 700 - 190 + 30 * (1 - p)
        blit(cv, txt("#1   D09-P1", 34, ORANGE, "monob"), cx - 410, top + 48, p, anchor="lc")
        blit(cv, txt("score 5.8266", 26, MUTED, "mono"), cx + 410, top + 48, p, anchor="rc")
        rows = [("passage", "Passage ID", "D09-P1"), ("document", "Document", "D09 · Attendance Policy Notice 2026"),
                ("version", "Version", "v2026"), ("date", "Date", "2026-01-08"), ("status", "Status", None)]
        for k, (word, key, val) in enumerate(rows):
            q = eo(prog(t, m.w(word, 2 if word in ("passage", "document") else 1) - 0.1, 0.4))
            if q <= 0:
                continue
            y = top + 110 + k * 54
            blit(cv, txt(key, 26, MUTED, "reg"), cx - 410 + 16 * (1 - q), y, p * q, anchor="lc")
            if val:
                blit(cv, txt(val, 28, TEXT, "semi"), cx - 190 + 16 * (1 - q), y, p * q, anchor="lc")
            else:
                blit(cv, chip_c("CURRENT", 22, (255, 255, 255), GREEN, None, "bold", 14, 38), cx - 190, y, p * q,
                     anchor="lc")
    q = back(prog(t, m.s(3) + 0.3, 0.5))
    if q > 0:
        blit(cv, rrect(520, 200, 26, CARD, ORANGE, 3), 1440, 700, clamp(q), 0.8 + 0.2 * q)
        blit(cv, txt("No supported", 38, ORANGE, "bold"), 1440, 668, clamp(q))
        blit(cv, txt("evidence found.", 38, ORANGE, "bold"), 1440, 718, clamp(q))


# ----------------------------------------------------------------------------- scene 4: linear scan
def grid_pos(i, x0=158, y0=300, cell=52):
    col, row = i // 5, i % 5  # document-major: 31 docs x 5 passages
    return x0 + col * cell, y0 + row * cell


def scene4(cv, t, m):
    p = eo(prog(t, 0.2, 0.5))
    blit(cv, txt("Linear scan", 58, TEXT, "bold"), 158, 190, p, anchor="lc")
    blit(cv, chip_c("O(T × q)", 28, ORANGE, CARD, ORANGE, "monob"), 560, 192, p)
    blit(cv, txt("31 documents × 5 passages = 155 passages", 24, MUTED, "reg"), W - 158, 192, p, anchor="rc")
    t0, t1 = m.w("checks") - 0.2, m.s(2) + 0.6
    sweep = prog(t, t0, t1 - t0)
    cur = int(sweep * 155)
    d = draw(cv)
    for i in range(155):
        x, y = grid_pos(i)
        a = prog(t, 0.3 + (i // 5) * 0.02, 0.3)
        if a <= 0:
            continue
        col = CARD2
        if sweep > 0 and i < cur:
            col = (58, 44, 38)
        d.rounded_rectangle((x, y, x + 44, y + 44), 8, fill=rgba(col, a), outline=rgba(LINE, a), width=1)
        if 0 < sweep < 1 and i == cur:
            d.rounded_rectangle((x - 3, y - 3, x + 47, y + 47), 10, outline=rgba(ORANGE), width=4)
    if 0 < sweep < 1:
        x, _ = grid_pos(cur)
        d.line((x + 22, 284, x + 22, 576), fill=rgba(ORANGE, 0.5), width=2)
    if t > t0 - 0.3:
        a = prog(t, t0 - 0.3, 0.4)
        blit(cv, txt(f"Passages checked:  {cur} / 155", 32, TEXT, "semi"), 158, 640, a, anchor="lc")
        blit(cv, txt(f"Tokens read:  {int(sweep * 1557):,} / 1,557", 32, ORANGE, "semi"), 1000, 640, a,
             anchor="lc")
    # small chart: scan time grows with corpus size
    q = prog(t, m.s(2), 1.6)
    if q > 0:
        x0, y0, w, h = 520, 900, 880, 170
        a = prog(t, m.s(2), 0.3)
        d.line((x0, y0, x0 + w, y0), fill=rgba(LINE, a), width=2)
        pts = [(25, 3.3), (50, 5.6), (100, 11.2), (155, 17.7)]
        xy = [(x0 + n / 155 * w, y0 - v / 17.7 * h) for n, v in pts]
        k = q * (len(xy) - 1)
        seg = [xy[0]]
        for j in range(1, len(xy)):
            if k >= j:
                seg.append(xy[j])
            elif k > j - 1:
                f = k - (j - 1)
                seg.append((lerp(xy[j - 1][0], xy[j][0], f), lerp(xy[j - 1][1], xy[j][1], f)))
        d.line(seg, fill=rgba(ORANGE), width=4)
        for j, (xx, yy) in enumerate(xy):
            if k >= j:
                d.ellipse((xx - 6, yy - 6, xx + 6, yy + 6), fill=rgba(ORANGE))
                blit(cv, txt(f"{pts[j][1]} µs", 20, MUTED, "semi"), xx, yy - 22)
                blit(cv, txt(f"N={pts[j][0]}", 18, DIM, "reg"), xx, y0 + 18)
        blit(cv, txt("scan time per question", 22, MUTED, "reg"), x0 - 20, y0 - h / 2, a, anchor="rc")


# ----------------------------------------------------------------------------- scene 5: pipeline + tokenizer
STAGES = ["Question", "Tokenizer", "Hash table", "Postings", "Ranking", "Top-k", "Evidence"]


def scene5(cv, t, m):
    t_tok = m.w("tokenizer") - 0.2
    xs = [123 + 105 + i * 244 for i in range(7)]
    for i, s in enumerate(STAGES):
        q = back(prog(t, 0.3 + i * 0.3, 0.45))
        if q <= 0:
            continue
        hot = (i == 1 and t > t_tok)
        blit(cv, chip_c(s, 27, ORANGE if hot else TEXT, CARD, ORANGE if hot else LINE, "semi", 20, 76), xs[i], 240,
             clamp(q), 0.7 + 0.3 * q)
        if i:
            arrow(cv, xs[i - 1] + 102, 240, xs[i] - 104, 240, MUTED, 1, 3, 10, eo(prog(t, 0.3 + i * 0.3, 0.3)))
    if t > 2.6:  # pulse travelling along the pipeline
        u = ((t - 2.6) / 2.4) % 1
        x = lerp(xs[0], xs[-1], u)
        draw(cv).ellipse((x - 7, 290, x + 7, 304), fill=rgba(ORANGE, 0.9))
    # tokenizer demo
    p = eo(prog(t, t_tok, 0.5))
    if p > 0:
        blit(cv, txt("input", 22, DIM, "semi"), 260, 400, p, anchor="lc")
        blit(cv, chip_c('"Minimum Attendance required for the Final Examination?"', 30, TEXT, CARD, LINE, "mono",
                        26, 66), W / 2, 450, p)
    toks = ["minimum", "attendance", "required", "for", "the", "final", "examination"]
    t_split, t_stop = m.w("splits") - 0.1, m.w("stop") - 0.1
    t_norm = m.w("normalises", default=m.w("normalis", default=m.s(1) + 4))
    widths = [chip_c(x, 28, TEXT, CARD2, LINE, "mono").width for x in toks]
    gap = 22
    keep = [x not in ("for", "the") for x in toks]
    tot_all = sum(widths) + gap * (len(toks) - 1)
    tot_keep = sum(w for w, k in zip(widths, keep) if k) + gap * (sum(keep) - 1)
    collapse = eio(prog(t, t_stop + 0.8, 0.6))
    x_all, x_keep = W / 2 - tot_all / 2, W / 2 - tot_keep / 2
    for i, (tok, w) in enumerate(zip(toks, widths)):
        q = back(prog(t, t_split + i * 0.12, 0.4))
        if q <= 0:
            continue
        xa = x_all + sum(widths[:i]) + gap * i + w / 2
        kept_before = [j for j in range(i) if keep[j]]
        xk = x_keep + sum(widths[j] for j in kept_before) + gap * len(kept_before) + w / 2
        y = 580
        if keep[i]:
            blit(cv, chip_c(tok, 28, TEXT, CARD2, LINE, "mono"), lerp(xa, xk, collapse), y, clamp(q))
        else:
            r = prog(t, t_stop, 0.3)
            fall = eio(prog(t, t_stop + 0.4, 0.6))
            sp = chip_c(tok, 28, RED, CARD2, RED, "mono") if r > 0 else chip_c(tok, 28, TEXT, CARD2, LINE, "mono")
            blit(cv, sp, xa, y + 90 * fall, clamp(q) * (1 - fall))
            if r > 0 and fall < 1:
                draw(cv).line((xa - w / 2 + 10, y, xa - w / 2 + 10 + (w - 20) * r, y), fill=rgba(RED, 1 - fall),
                              width=3)
    if t > t_stop:
        blit(cv, txt("stop words removed: for, the", 22, RED, "semi"), W / 2, 650, prog(t, t_stop + 0.3, 0.4))
    for k, (a, b) in enumerate((("students", "student"), ("policies", "policy"))):
        q = eo(prog(t, t_norm + k * 0.4, 0.45))
        if q > 0:
            x = W / 2 + (k * 2 - 1) * 280
            blit(cv, chip_c(a, 28, MUTED, CARD, LINE, "mono"), x - 110, 740, q)
            arrow(cv, x - 30, 740, x + 30, 740, ORANGE, q, 3, 10)
            blit(cv, chip_c(b, 28, ORANGE, CARD, ORANGE, "mono"), x + 110, 740, q)
    q = back(prog(t, m.s(2), 0.5))
    if q > 0:
        blit(cv, chip_c("Same tokenizer for linear scan and inverted index", 28, GREEN, CARD, GREEN, "semi", 26, 64),
             W / 2, 850, clamp(q), 0.8 + 0.2 * q)


# ----------------------------------------------------------------------------- scene 6: hash table
def fnv1a(s):
    h = 1469598103934665603
    for c in s.encode():
        h ^= c
        h = (h * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return h


HWORDS = ["attendance", "exam", "fee", "hostel", "lab", "viva", "library"]  # "hostel" collides with "attendance"


def layout(nb, words):
    """Bucket -> chain order for the given words and bucket count."""
    chains = {}
    pos = {}
    for w in words:
        b = fnv1a(w) % nb
        chains.setdefault(b, []).append(w)
        pos[w] = (b, len(chains[b]) - 1)
    return pos


def bucket_xy(nb, b):
    if nb == 8:
        return 240, 215 + b * 76, 66
    return 240, 205 + b * 39, 34


def scene6(cv, t, m):
    t_fnv = m.s(1)
    t_col = m.w("collision")
    t_link = m.w("linked")
    t_load = m.s(4)
    t_resize = m.w("doubles") - 0.2
    times = [t_fnv + 0.3, t_fnv + 1.3, t_fnv + 2.3, t_col - 0.85, t_link + 0.6, t_link + 1.5, t_resize + 1.3]
    rs = eio(prog(t, t_resize, 0.9))
    p0 = eo(prog(t, 0.2, 0.5))
    blit(cv, txt("Hash table  ·  separate chaining", 40, TEXT, "bold"), 160, 140, p0, anchor="lc")
    blit(cv, txt("example with 8 buckets", 22, DIM, "reg"), 160, 180, p0, anchor="lc")
    d = draw(cv)
    for nb, a in ((8, p0 * (1 - rs)), (16, rs)):
        for b in range(nb):
            x, y, h = bucket_xy(nb, b)
            if a > 0.01:
                d.rounded_rectangle((x - 40, y, x + 40, y + h - 8), 8, fill=rgba(CARD2, a), outline=rgba(LINE, a),
                                    width=2)
                blit(cv, txt(f"[{b}]", 20 if nb == 8 else 16, MUTED, "mono"), x - 52, y + (h - 8) / 2, a,
                     anchor="rc")
    pos8 = layout(8, HWORDS[:6])
    pos16 = layout(16, HWORDS)
    for i, wd in enumerate(HWORDS):
        ti = times[i]
        if t < ti:
            continue
        b8 = fnv1a(wd) % 8
        fly = eio(prog(t, ti + 0.55, 0.55))
        appear = eo(prog(t, ti, 0.3))
        # panel on the right shows the word being hashed
        if fly < 1:
            pa = appear * (1 - fly)
            blit(cv, chip_c(wd, 34, TEXT, CARD, ORANGE, "monob", 24, 70), 1460, 300, pa)
            nb = 16 if i == 6 else 8
            blit(cv, txt(f'FNV-1a("{wd}") mod {nb} = {fnv1a(wd) % nb}', 28, ORANGE, "mono"), 1460, 380, pa)
        if i < 6:
            b, k = pos8[wd]
            x8, y8, h8 = bucket_xy(8, b)
            tx8, ty8 = x8 + 130 + k * 200, y8 + (h8 - 8) / 2
        b16, k16 = pos16[wd]
        x16, y16, h16 = bucket_xy(16, b16)
        tx16, ty16 = x16 + 130 + k16 * 200, y16 + (h16 - 8) / 2
        if i < 6:
            tx, ty = lerp(tx8, tx16, rs), lerp(ty8, ty16, rs)
        else:
            tx, ty = tx16, ty16
        x = lerp(1460, tx, fly)
        y = lerp(300, ty, fly)
        if fly > 0:
            small = rs > 0.5 or i == 6
            sp = chip_c(wd, 20 if small else 24, TEXT, CARD, LINE, "mono", 12, 30 if small else 48)
            if wd == "hostel" and t_col - 0.3 < t < t_col + 2.2:
                sp = chip_c(wd, 24 if not small else 20, ORANGE, CARD, ORANGE, "monob", 12, 30 if small else 48)
            blit(cv, sp, x, y, clamp(fly * 3))
    # arrows bucket -> chain and between chain nodes
    for nb, pos, a in ((8, pos8, 1 - rs), (16, pos16, rs)):
        if a < 0.05:
            continue
        for wd, (b, k) in pos.items():
            idx = HWORDS.index(wd)
            if t < times[idx] + 1.1:
                continue
            x, y, h = bucket_xy(nb, b)
            yy = y + (h - 8) / 2
            x_from = x + 40 if k == 0 else x + 130 + (k - 1) * 200 + 70
            arrow(cv, x_from + 4, yy, x + 130 + k * 200 - 72, yy, MUTED, a, 2, 8)
    if t_col - 0.1 < t < t_col + 2.6:
        a = prog(t, t_col - 0.1, 0.3) * (1 - prog(t, t_col + 2.2, 0.4))
        b, _ = pos8["hostel"]
        x, y, h = bucket_xy(8, b)
        blit(cv, chip_c("collision → linked list", 24, ORANGE, CARD, ORANGE), 1000, y + (h - 8) / 2, a)
    q = eo(prog(t, m.w("separate") - 0.1, 0.4))
    if q > 0:
        blit(cv, para("Each bucket keeps a linked list (chain) of entries", 26, MUTED, "reg", 460), 1460, 470, q)
    # load factor meter
    q = eo(prog(t, t_load, 0.4))
    if q > 0:
        n_ent = sum(1 for k in range(7) if t >= times[k] + 1.1)
        nb = 16 if rs > 0.5 else 8
        lf = n_ent / nb
        x0, y0 = 1230, 640
        blit(cv, txt(f"load factor = entries / buckets = {n_ent}/{nb} = {lf:.2f}", 24, TEXT, "semi"), x0, y0 - 40,
             q, anchor="lc")
        d.rounded_rectangle((x0, y0, x0 + 460, y0 + 22), 11, fill=rgba(CARD2, q))
        col = ORANGE if lf >= 0.75 else GREEN
        d.rounded_rectangle((x0, y0, x0 + 460 * min(lf, 1), y0 + 22), 11, fill=rgba(col, q))
        mk = x0 + 460 * 0.75
        d.line((mk, y0 - 8, mk, y0 + 30), fill=rgba(TEXT, q), width=2)
        blit(cv, txt("0.75", 18, MUTED, "semi"), mk, y0 + 44, q)
        r = back(prog(t, t_resize - 0.3, 0.4)) * (1 - prog(t, t_resize + 2.4, 0.4))
        if r > 0:
            blit(cv, chip_c("next insert would exceed 0.75  →  resize ×2 (8 → 16 buckets)", 22, (20, 14, 10), ORANGE,
                            None, "bold", 18, 50), 1460, 760, clamp(r))


# ----------------------------------------------------------------------------- scene 7: inverted index
ATT_POSTINGS = [("D04-P1", 1), ("D04-P2", 1), ("D04-P3", 1), ("D04-P4", 1), ("D09-P1", 2)]
QWORDS = ["minimum", "attendance", "required", "final", "examination"]


@lru_cache(None)
def postings():
    """Real postings (passage index list) of the query words, using the engine's tokenizer rules."""
    stop = set("a an the is are am was were be been to of in on at by for from with and or not no i me my we you your "
               "it its this that these those as if can could do does did what when where which who how why will would "
               "should must may there their they them he she his her all any each after before about into than then "
               "so such only also up per other".split())

    def norm(w):
        if len(w) > 4 and w.endswith("ies"):
            return w[:-3] + "y"
        if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
            return w[:-1]
        return w

    rows = []
    for line in (PROJECT / "data" / "passages.txt").read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        f = line.split("|")
        rows.append([norm(x) for x in re.findall(r"[a-z0-9]+", f[7].lower()) if x not in stop])
    return {q: [i for i, toks in enumerate(rows) if q in toks] for q in QWORDS}


def scene7(cv, t, m):
    p = eo(prog(t, 0.2, 0.5))
    blit(cv, chip_c("attendance", 32, ORANGE, CARD, ORANGE, "monob", 24, 70), 280, 230, p)
    for k, (pid, tf) in enumerate(ATT_POSTINGS):
        q = back(prog(t, m.w("postings") + k * 0.18, 0.4))
        if q <= 0:
            continue
        x = 560 + k * 230
        node = rrect(190, 84, 16, CARD, LINE, 2)
        blit(cv, node, x, 230, clamp(q), 0.8 + 0.2 * q)
        blit(cv, txt(pid, 26, TEXT, "monob"), x, 214, clamp(q))
        blit(cv, txt(f"tf = {tf}", 22, ORANGE if tf > 1 else MUTED, "semi"), x, 250, clamp(q))
        arrow(cv, (420 if k == 0 else x - 230 + 95) + 4, 230, x - 99, 230, MUTED, clamp(q), 2, 9)
    q = eo(prog(t, m.w("postings") + 1.2, 0.4))
    blit(cv, txt("… 11 postings in total", 24, MUTED, "semi"), 1730, 230, q)
    blit(cv, txt("postings list = passages containing the word + term frequency (tf)", 24, DIM, "reg"), 160, 310, q,
         anchor="lc")
    # query words and grid
    t_q = m.s(1)
    post = postings()
    x0, y0, cell = 402, 520, 36
    d = draw(cv)
    lit = {}
    for j, wq in enumerate(QWORDS):
        tq = t_q + 0.4 + j * 0.45
        q = back(prog(t, tq, 0.4))
        if q > 0:
            blit(cv, chip_c(wq, 26, TEXT if wq != "attendance" else ORANGE, CARD2, LINE, "mono"), 520 + j * 220, 440,
                 clamp(q))
        if t >= tq + 0.2:
            for i in post[wq]:
                lit[i] = max(lit.get(i, 0), prog(t, tq + 0.2, 0.4))
    if "attendance" in post and t >= m.w("postings") + 1.0:
        for i in post["attendance"]:
            lit[i] = max(lit.get(i, 0), 0.6 * prog(t, m.w("postings") + 1.0, 0.5))
    a = prog(t, t_q - 0.6, 0.5)
    for i in range(155):
        col, row = i // 5, i % 5
        x, y = x0 + col * cell, y0 + row * cell
        l = lit.get(i, 0)
        fill = mix(CARD2, ORANGE, l) if l > 0 else CARD2
        d.rounded_rectangle((x, y, x + 30, y + 30), 6, fill=rgba(fill, a), outline=rgba(LINE, a), width=1)
    if a > 0:
        n_vis = sum(len(post[w]) for j, w in enumerate(QWORDS) if t >= t_q + 0.6 + j * 0.45)
        blit(cv, txt(f"postings visited  P = {n_vis}", 30, ORANGE, "semi"), 402, 742, a, anchor="lc")
        blit(cv, txt("linear scan reads  T = 1,557 tokens", 30, MUTED, "semi"), 1518, 742, a, anchor="rc")
        q = back(prog(t, m.w("instead") - 0.2, 0.5))
        if q > 0:
            blit(cv, chip_c("Indexed lookup  ·  O(q + P)", 28, ORANGE, CARD, ORANGE, "monob", 24, 60), W / 2, 830,
                 clamp(q))


# ----------------------------------------------------------------------------- scene 8: ranking
@lru_cache(None)
def rank_card(which, superseded_badge):
    c = rrect(1100, 210, 24, CARD, LINE, 2).copy()
    if which == "A":
        title, ex, ver = ("D04-P3  ·  Attendance Policy Notice 2025", '"Students with attendance below the required '
                          'limit are not allowed to appear in the final examination…"', "v2025 · 2025-01-05")
    else:
        title, ex, ver = ("D09-P1  ·  Attendance Policy Notice 2026 (Revised)", '"…students must maintain at least 75 '
                          'percent attendance in each course to be eligible for the final examination."',
                          "v2026 · 2026-01-08")
    c.alpha_composite(txt(title, 30, TEXT, "bold"), (36, 22))
    c.alpha_composite(para(ex, 23, MUTED, "reg", 760), (36, 76))
    c.alpha_composite(txt(ver, 22, DIM, "semi"), (36, 160))
    if superseded_badge is not None:
        b = chip(superseded_badge, 20, (255, 255, 255), GREEN if superseded_badge == "CURRENT" else RED, None, "bold",
                 14, 36)
        c.alpha_composite(b, (36 + txt(ver, 22).width + 30, 156))
    return c


def scene8(cv, t, m):
    p = eo(prog(t, 0.2, 0.5))
    blit(cv, txt("BM25  =  Σ  idf · tf·(k1+1) / ( tf + k1·(1 − b + b·len/avglen) )", 32, TEXT, "mono"), W / 2,
         165, p)
    blit(cv, txt("k1 = 1.2   ·   b = 0.75   ·   then × 0.5 if the passage is superseded", 24, MUTED, "reg"), W / 2,
         215, p)
    for k, (word, label) in enumerate((("rare", "rare word → higher idf"), ("length", "long passage → normalised"))):
        q = back(prog(t, m.w(word) - 0.1, 0.4))
        if q > 0:
            blit(cv, chip_c(label, 24, ORANGE, CARD, ORANGE), W / 2 + (k * 2 - 1) * 250, 275, clamp(q))
    t_fresh = m.s(2)
    t_swap = m.s(3) - 0.2
    slots = (470, 735)
    sw = eio(prog(t, t_swap, 0.9))
    yA = lerp(slots[0], slots[1], sw)
    yB = lerp(slots[1], slots[0], sw)
    xA = 960 - 60 * math.sin(sw * math.pi)
    xB = 960 + 60 * math.sin(sw * math.pi)
    q = eo(prog(t, 0.6, 0.5))
    for i, y in enumerate(slots):
        blit(cv, txt(f"#{i + 1}", 44, ORANGE if i == 0 else MUTED, "bold"), 330, y, q, anchor="rc")
    stamp = prog(t, t_fresh + 0.3, 0.35)
    blit(cv, rank_card("A", "SUPERSEDED" if stamp > 0 else None), xA, yA, q)
    blit(cv, rank_card("B", "CURRENT" if sw > 0.5 else None), xB, yB, q)
    sA = lerp(10.593, 5.296, eio(prog(t, t_fresh + 0.7, 0.9)))
    blit(cv, txt(f"{sA:.3f}", 40, RED if stamp > 0 else TEXT, "monob"), xA + 520, yA - 30, q, anchor="rc")
    blit(cv, txt("score", 20, MUTED, "reg"), xA + 520, yA + 12, q, anchor="rc")
    blit(cv, txt("5.827", 40, GREEN if sw > 0.5 else TEXT, "monob"), xB + 520, yB - 30, q, anchor="rc")
    blit(cv, txt("score", 20, MUTED, "reg"), xB + 520, yB + 12, q, anchor="rc")
    if stamp > 0:
        a = 1 - prog(t, t_swap - 0.2, 0.4)
        s = lerp(2.2, 1.0, eo(stamp))
        st = chip_c("SUPERSEDED  × 0.5", 34, RED, (40, 18, 18), RED, "bold", 22, 70)
        blit(cv, st.rotate(-8, expand=True, resample=Image.BICUBIC), xA + 250, yA - 10, clamp(stamp * 2) * a, s)


# ----------------------------------------------------------------------------- scene 9: evidence rule
def scene9(cv, t, m):
    p = eo(prog(t, 0.2, 0.5))
    words = ["parking", "permit", "student", "car"]
    for i, wq in enumerate(words):
        blit(cv, chip_c(wq, 30, ORANGE if wq == "student" else TEXT, CARD2, LINE, "mono", 22, 64), 600 + i * 240,
             200, prog(t, 0.2 + i * 0.12, 0.4))
    blit(cv, txt("Evidence rule: a passage must match ≥ 50 % of the concepts  (here ≥ 2 of 4)", 28, TEXT, "semi"),
         W / 2, 290, p)
    d = draw(cv)
    d.rounded_rectangle((560, 330, 1360, 346), 8, fill=rgba(CARD2, p))
    d.rounded_rectangle((560, 330, 560 + 800 * 0.25, 346), 8, fill=rgba(RED, p))
    d.line((960, 320, 960, 356), fill=rgba(TEXT, p), width=3)
    blit(cv, txt("best match 1/4 = 25 %", 20, RED, "semi"), 560, 372, p, anchor="lc")
    blit(cv, txt("50 % threshold", 20, MUTED, "semi"), 960, 372, p)
    t_spawn = m.w("46") - 0.2
    t_break = m.w("none") - 0.1
    rnd = random.Random(9)
    for i in range(46):
        col, row = i % 12, i // 12
        x, y = 300 + col * 120, 470 + row * 70
        ts = t_spawn + i * 0.025
        q = back(prog(t, ts, 0.3))
        br = prog(t, t_break + rnd.random() * 0.4, 1.1)
        if q <= 0:
            continue
        if br <= 0:
            blit(cv, chip_c("1/4", 22, MUTED, CARD, LINE, "mono", 14, 48), x, y, clamp(q))
        else:
            for k in range(6):
                vx, vy = rnd.uniform(-90, 90), rnd.uniform(-160, -20)
                tt = br * 1.1
                px, py = x + vx * tt, y + vy * tt + 600 * tt * tt
                r = 4 * (1 - br)
                if r > 0.3:
                    d.ellipse((px - r, py - r, px + r, py + r), fill=rgba(ORANGE if k % 2 else MUTED, 1 - br))
    if t > t_spawn:
        blit(cv, txt("46 passages share a word (\"student\")", 24, MUTED, "semi"), W / 2, 430,
             prog(t, t_spawn, 0.3) * (1 - prog(t, t_break + 0.8, 0.4)))
    q = prog(t, m.s(2) - 0.2, 0.4)
    if q > 0:
        msg = "No supported evidence found."
        n = int(len(msg) * prog(t, m.s(2), 0.9))
        blit(cv, rrect(1000, 190, 28, CARD, ORANGE, 3), W / 2, 640, q)
        blit(cv, txt(msg[:n] if n else " ", 48, ORANGE, "bold"), W / 2 - 400, 610, q, anchor="lc")
        blit(cv, para("Reason: passages share some words with the query but none matches at least 50 % of the "
                      "query concepts.", 22, MUTED, "reg", 800), W / 2, 680, prog(t, m.s(2) + 1.0, 0.4))


# ----------------------------------------------------------------------------- scene 10: heap
STREAM = [4.2, 7.9, 1.3, 9.1, 5.5, 2.2, 8.4, 6.0, 3.1, 9.7, 4.8, 7.2]


def heap_states():
    """Bounded min-heap of size 3 (root = worst kept). Returns list of (heap array, accepted?) after each offer."""
    hp, out = [], []
    for v in STREAM:
        acc = True
        if len(hp) < 3:
            hp.append(v)
            hp.sort()
        elif v > hp[0]:
            hp[0] = v
            hp.sort()
        else:
            acc = False
        out.append((list(hp), acc))
    return out


def scene10(cv, t, m):
    p = eo(prog(t, 0.2, 0.5))
    blit(cv, txt("Bounded min-heap  (k = 3)", 40, TEXT, "bold"), 520, 150, p)
    blit(cv, txt("root = worst of the best k  ·  O(C log k)", 24, MUTED, "reg"), 520, 195, p)
    nodes = [(520, 470), (380, 640), (660, 640)]
    d = draw(cv)
    for a, b in ((0, 1), (0, 2)):
        d.line((*nodes[a], *nodes[b]), fill=rgba(LINE, p), width=3)
    states = heap_states()
    t0, t1 = 1.0, m.s(2) - 0.3
    step = (t1 - t0) / len(STREAM)
    k = int((t - t0) / step) if t > t0 else -1
    cur = states[min(k, len(STREAM) - 1)][0] if k >= 0 else []
    for i, (x, y) in enumerate(nodes):
        blit(cv, disc(120, CARD2, ORANGE if i == 0 else LINE, 3), x, y, p)
        if i < len(cur):
            blit(cv, txt(f"{cur[i]:.1f}", 34, ORANGE if i == 0 else TEXT, "monob"), x, y, p)
    blit(cv, txt("root", 20, ORANGE, "semi"), 520, 395, p)
    # candidate stream on the conveyor
    for i, v in enumerate(STREAM):
        ti = t0 + i * step
        u = prog(t, ti - 1.2, 1.2)
        if u <= 0 or t > ti + 0.7:
            continue
        x = lerp(160, 520, eo(u))
        y = 300
        acc = states[i][1]
        if t > ti:
            g = prog(t, ti, 0.6)
            if acc:
                y = lerp(300, 470, g)
                a = 1 - g
            else:
                y = 300 + 120 * g
                x += 120 * g
                a = 1 - g
            blit(cv, chip_c(f"{v:.1f}", 26, GREEN if acc else RED, CARD, GREEN if acc else RED, "monob", 14, 48), x,
                 y, a)
        else:
            blit(cv, chip_c(f"{v:.1f}", 26, TEXT, CARD, LINE, "monob", 14, 48), x, y, prog(t, ti - 1.2, 0.2))
    if k >= 0:
        blit(cv, txt("better than the root → replace it   ·   worse → discard", 22, MUTED, "reg"), 520, 770, p)
    # comparison bars
    q = eo(prog(t, m.s(1) - 0.2, 0.5))
    if q > 0:
        x0 = 1060
        blit(cv, txt("Top-k on 15,500 passages  ·  C = 9,700 candidates, k = 3", 26, TEXT, "semi"), x0, 330, q,
             anchor="lc")
        rows = [("Bounded heap", "O(C log k)", 679.3, ORANGE), ("Merge sort", "O(C log C)", 2536.4, MUTED)]
        for j, (name, cx, us, col) in enumerate(rows):
            y = 420 + j * 130
            g = eio(prog(t, m.s(1) + 0.2 + j * 0.3, 1.0))
            blit(cv, txt(name, 28, TEXT, "bold"), x0, y, q, anchor="lc")
            blit(cv, txt(cx, 24, col, "mono"), x0 + 260, y, q, anchor="lc")
            d.rounded_rectangle((x0, y + 30, x0 + 700, y + 62), 16, fill=rgba(CARD2, q))
            d.rounded_rectangle((x0, y + 30, x0 + 700 * us / 2536.4 * g, y + 62), 16, fill=rgba(col, q))
            blit(cv, txt(f"{us * g / 1000:.2f} ms", 24, TEXT, "monob"), x0 + 712, y + 46, q, anchor="lc")
        r = back(prog(t, m.w("four") - 0.1, 0.5))
        if r > 0:
            blit(cv, chip_c("≈ 3.7× faster  ·  identical top-k", 28, GREEN, CARD, GREEN, "semi", 24, 64), x0 + 380,
                 720, clamp(r))


# ----------------------------------------------------------------------------- scene 11: results (glass cards)
@lru_cache(None)
def glow_bg():
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for (x, y, r, c) in ((420, 520, 260, ORANGE), (1500, 420, 300, (120, 70, 200)), (960, 760, 220, (230, 90, 60))):
        d.ellipse((x - r, y - r, x + r, y + r), fill=rgba(c, 0.45))
    return im.filter(ImageFilter.GaussianBlur(120))


@lru_cache(None)
def glass(w, h):
    k = 2
    im = Image.new("RGBA", (w * k, h * k), (0, 0, 0, 0))
    grad = Image.new("RGBA", (w * k, h * k), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for y in range(h * k):
        a = int(lerp(46, 14, y / (h * k)))
        gd.line((0, y, w * k, y), fill=(255, 255, 255, a))
    mask = Image.new("L", (w * k, h * k), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w * k - 1, h * k - 1), 30 * k, fill=255)
    im.paste(grad, (0, 0), mask)
    ImageDraw.Draw(im).rounded_rectangle((1, 1, w * k - 2, h * k - 2), 30 * k, outline=(255, 255, 255, 70),
                                          width=2 * k)
    return im.resize((w, h), Image.LANCZOS)


def mini_line(cv, x0, y0, w, h, vals, vmin, vmax, p, col):
    d = draw(cv)
    pts = [(x0 + i / (len(vals) - 1) * w, y0 + h - (v - vmin) / (vmax - vmin) * h) for i, v in enumerate(vals)]
    k = p * (len(pts) - 1)
    seg = [pts[0]]
    for j in range(1, len(pts)):
        if k >= j:
            seg.append(pts[j])
        elif k > j - 1:
            f = k - (j - 1)
            seg.append((lerp(pts[j - 1][0], pts[j][0], f), lerp(pts[j - 1][1], pts[j][1], f)))
    poly = seg + [(seg[-1][0], y0 + h), (seg[0][0], y0 + h)]
    if len(seg) > 1:
        d.polygon(poly, fill=rgba(col, 0.18))
        d.line(seg, fill=rgba(col), width=4)
        d.ellipse((seg[-1][0] - 7, seg[-1][1] - 7, seg[-1][0] + 7, seg[-1][1] + 7), fill=rgba((255, 255, 255)))


def scene11(cv, t, m):
    a = prog(t, 0.1, 0.8)
    if a > 0:
        cv.alpha_composite(fade(glow_bg(), a))
    cards = [("Recall@3", m.w("recall") - 0.2), ("Speed-up", m.w("11") - 0.4),
             ("Index memory", m.w("11") + 0.3), ("Tests", m.w("24", default=m.s(3)) - 0.2)]
    for i, (name, t0) in enumerate(cards):
        q = eo(prog(t, t0, 0.6))
        if q <= 0:
            continue
        x = 115 + i * 430
        y = 230 + 40 * (1 - q)
        blit(cv, glass(400, 450), x, y, q, anchor="lt")
        blit(cv, txt(name, 28, MUTED, "semi"), x + 32, y + 46, q, anchor="lc")
        c = eio(prog(t, t0 + 0.2, 1.2))
        if name == "Recall@3":
            big, sub = f"{0.912 * c:.2f}", "17 answerable questions"
            mini_line(cv, x + 32, y + 270, 336, 120, [0.833, 0.800, 0.875, 0.912], 0.7, 0.95, c, ORANGE)
            foot = "25 → 50 → 100 → 155 passages"
        elif name == "Speed-up":
            big, sub = f"{lerp(1, 11, c):.0f}× → {lerp(1, 15, c):.0f}×", "index vs linear scan"
            mini_line(cv, x + 32, y + 270, 336, 120, [10.1, 12.7, 13.7, 14.6], 8, 15.5, c, GREEN)
            foot = "155 → 15,500 passages"
        elif name == "Index memory":
            big, sub = f"{64 * c:.0f} KB", "at 155 passages"
            dd = draw(cv)
            for j, v in enumerate((18.6, 27.8, 47.2, 64.0)):
                bh = 120 * v / 64 * c
                bx = x + 40 + j * 84
                dd.rounded_rectangle((bx, y + 390 - bh, bx + 56, y + 390), 8, fill=rgba(BLUE, 0.85 * q))
            foot = "25 / 50 / 100 / 155 passages"
        else:
            big, sub = f"{round(24 * c)}/24", "edge-case tests pass"
            dd = draw(cv)
            cx, cy, r = x + 200, y + 330, 62
            dd.arc((cx - r, cy - r, cx + r, cy + r), 0, 360, fill=rgba(CARD2, q), width=12)
            if c > 0:
                dd.arc((cx - r, cy - r, cx + r, cy + r), -90, -90 + 360 * c, fill=rgba(GREEN, q), width=12)
            blit(cv, txt("✓", 50, GREEN, "sym"), cx, cy, q * c)
            foot = "scan = index on 40/40 runs"
        blit(cv, txt(big, 56 if name == "Speed-up" else 64, TEXT, "bold"), x + 32, y + 128, q, anchor="lc")
        blit(cv, txt(sub, 22, MUTED, "reg"), x + 32, y + 186, q, anchor="lc")
        blit(cv, txt(foot, 20, DIM, "semi"), x + 32, y + 420, q, anchor="lc")
    q = back(prog(t, m.w("unanswerable") - 0.1, 0.5))
    if q > 0:
        blit(cv, chip_c("Unanswerable questions refused: 3 / 3", 26, GREEN, CARD, GREEN, "semi", 22, 58), 620, 790,
             clamp(q))
    q = back(prog(t, m.w("same") - 0.1, 0.5))
    if q > 0:
        blit(cv, chip_c("Scan and index: identical answers", 26, ORANGE, CARD, ORANGE, "semi", 22, 58), 1300, 790,
             clamp(q))


# ----------------------------------------------------------------------------- scene 12: real screenshots
SHOT_FILES = [("Screenshot 2026-10-26 212706.png", "Command line: a search with full provenance"),
              ("Screenshot 2026-10-26 212952.png", "Test suite: 24/24 passed"),
              ("Screenshot 2026-10-26 213357.png", "Desktop GUI: scan vs index, same answers")]


@lru_cache(None)
def shot(i):
    im = Image.open(SHOTS / SHOT_FILES[i][0]).convert("RGBA")
    s = min(1380 / im.width, 640 / im.height)
    im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, im.width - 1, im.height - 1), 18, fill=255)
    out = Image.new("RGBA", (im.width + 80, im.height + 80), (0, 0, 0, 0))
    sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((40, 50, 40 + im.width, 50 + im.height), 18, fill=(0, 0, 0, 160))
    out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(18)))
    out.paste(im, (40, 40), mask)
    ImageDraw.Draw(out).rounded_rectangle((40, 40, 40 + im.width - 1, 40 + im.height - 1), 18,
                                          outline=(255, 255, 255, 50), width=2)
    return out


def scene12(cv, t, m):
    starts = [0.3, m.w("test") - 0.3, m.w("desktop") - 0.3]
    for i, t0 in enumerate(starts):
        nxt = starts[i + 1] if i + 1 < len(starts) else 1e9
        pin = eio(prog(t, t0, 0.7))
        pout = eio(prog(t, nxt, 0.7))
        if pin <= 0 or pout >= 1:
            continue
        x = lerp(2500, 960, pin) - 1500 * pout
        s = 1 - 0.12 * pout
        blit(cv, shot(i), x, 480, 1 - 0.6 * pout, s)
        blit(cv, chip_c(SHOT_FILES[i][1], 26, TEXT, CARD, ORANGE, "semi", 22, 56), x, 120, 1 - pout)
    q = back(prog(t, m.s(1) - 0.1, 0.5))
    if q > 0:
        blit(cv, chip_c("All data is synthetic test data, not official MUET policy (except D24: the PBL brief)", 24,
                        ORANGE, CARD, ORANGE, "semi", 22, 52), W / 2, 880, clamp(q))


# ----------------------------------------------------------------------------- scene 13: end card
THUMB_T = {1: 9.0, 2: 21.0, 3: 22.0, 4: 11.0, 5: 13.0, 6: 21.0, 7: 13.0, 8: 16.0, 9: 13.0, 10: 13.0, 11: 22.0, 12: 9.0}


@lru_cache(None)
def thumb(n):
    m = Meta(n)
    im = frame(n, min(THUMB_T[n], m.dur - 1), m, captions_on=False)
    return im.resize((384, 216), Image.LANCZOS).convert("RGBA")


def scene13(cv, t, m):
    for i in range(12):
        col, row = i % 4, i // 4
        x, y = 280 + col * 454, 250 + row * 270
        q = eo(prog(t, 0.1 + i * 0.07, 0.6))
        blit(cv, thumb(i + 1), x, y + 30 * (1 - q), 0.28 * q)
    p = eo(prog(t, 0.9, 0.7))
    blit(cv, rrect(1040, 430, 30, (16, 16, 20), None, 0, 0.92), W / 2, 520, p)
    blit(cv, glass(1040, 430), W / 2, 520, p)
    blit(cv, txt("Fast Document Retrieval Engine", 64, TEXT, "bold"), W / 2, 395, p)
    blit(cv, txt("for a University RAG Assistant", 32, MUTED, "reg"), W / 2, 455, p)
    blit(cv, txt("Waqas Ali  ·  Mehran Ali  ·  Gaffar  ·  Basit Azam", 30, TEXT, "semi"), W / 2, 530, p)
    blit(cv, txt("CS-251 Data Structures and Algorithms  ·  Computer Systems Engineering, MUET Jamshoro", 24, MUTED,
                 "reg"), W / 2, 580, p)
    q = eo(prog(t, m.w("thank") - 0.1, 0.6))
    blit(cv, txt("Thank you, Dr. Ali Asghar Manjotho", 36, ORANGE, "bold"), W / 2, 655, q)


SCENES = {1: scene1, 2: scene2, 3: scene3, 4: scene4, 5: scene5, 6: scene6, 7: scene7, 8: scene8, 9: scene9,
          10: scene10, 11: scene11, 12: scene12, 13: scene13}


# ----------------------------------------------------------------------------- frame / render
def frame(n, t, m, captions_on=True):
    base = background()
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    SCENES[n](layer, t, m)
    a = min(prog(t, 0, 0.3), 1 - prog(t, m.dur - 0.3, 0.3))
    if n == 13:
        a = min(a, 1.0)
    cv = base.copy()
    cv.alpha_composite(fade(layer, a))
    header(cv, n)
    if captions_on:
        captions(cv, t, m)
    if n == 13:  # final fade to black
        b = prog(t, m.dur - 1.0, 1.0)
        if b > 0:
            cv.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, int(255 * b))))
    return cv.convert("RGB")


def render_scene(n):
    m = Meta(n)
    CLIPS.mkdir(parents=True, exist_ok=True)
    out = CLIPS / f"scene_{n:02d}.mp4"
    proc = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                             "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "17",
                             "-pix_fmt", "yuv420p", "-threads", "2", str(out)], stdin=subprocess.PIPE)
    for f in range(m.frames):
        proc.stdin.write(frame(n, f / FPS, m).tobytes())
    proc.stdin.close()
    proc.wait()
    return f"scene {n:02d}: {m.frames} frames ({m.dur:.1f}s)"


def build_audio():
    chunks = []
    for n in SCENES:
        m = Meta(n)
        with wave.open(str(AUDIO / f"scene_{n:02d}.wav")) as wv:
            sr = wv.getframerate()
            data = np.frombuffer(wv.readframes(wv.getnframes()), np.int16)
        total = int(round(m.dur * sr))
        buf = np.zeros(total, np.int16)
        s = int(LEAD * sr)
        e = min(total, s + len(data))
        buf[s:e] = data[:e - s]
        chunks.append(buf)
    out = BUILD / "voice.wav"
    with wave.open(str(out), "wb") as wv:
        wv.setnchannels(1)
        wv.setsampwidth(2)
        wv.setframerate(sr)
        wv.writeframes(np.concatenate(chunks).tobytes())
    return out


def final():
    voice = build_audio()
    lst = BUILD / "clips.txt"
    lst.write_text("\n".join(f"file '{(CLIPS / f'scene_{n:02d}.mp4').as_posix()}'" for n in SCENES), encoding="utf-8")
    joined = BUILD / "joined.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
                    str(joined)], check=True)
    out = ROOT / "PBL_video_v2.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(joined), "-i", str(voice), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-af", "highpass=f=70,loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a",
                    "192k", "-ar", "48000", "-shortest", "-movflags", "+faststart", str(out)], check=True)
    print(out)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "frames":
        n = int(sys.argv[2])
        m = Meta(n)
        pv = BUILD / "preview"
        pv.mkdir(parents=True, exist_ok=True)
        for ts in sys.argv[3:]:
            frame(n, float(ts), m).save(pv / f"s{n:02d}_{float(ts):05.1f}.png")
        print(f"scene {n}: dur {m.dur:.1f}s; words:", " ".join(f"{w[2]}@{LEAD + w[0]:.1f}" for w in m.words))
    elif cmd == "render":
        todo = [int(x) for x in sys.argv[2:]] or list(SCENES)
        with Pool(4) as pool:
            for r in pool.imap_unordered(render_scene, todo):
                print(r, flush=True)
    elif cmd == "final":
        final()
