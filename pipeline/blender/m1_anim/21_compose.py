"""P6 step 3: compose contact sheets from the rendered strips (plain Python + PIL).

  ~/ml-env/bin/python -I pipeline/blender/m1_anim/21_compose.py

docs/bakeoff/P6/<clip>.jpg            winner: front + side rows, frame/time labels, key metrics
docs/bakeoff/P6/compare_<clip>.jpg    every source for that clip, front + side rows each
(JPEG: Cycles-denoised renders compress ~10x better than PNG; the PNG set was 35 MB)
"""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
FR = os.path.join(HERE, "_work", "frames")
OUT = os.path.join(REPO, "docs", "bakeoff", "P6")
sys.path.insert(0, HERE)
os.makedirs(OUT, exist_ok=True)

import jobs  # noqa: E402  (plain data, no Blender imports)

manifest = json.load(open(os.path.join(FR, "manifest.json")))
metrics = json.load(open(os.path.join(HERE, "_work", "metrics.json")))


def font(size):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


F_T, F_S = font(26), font(16)
BG = (255, 255, 255)
INK = (25, 25, 30)
DIM = (95, 95, 105)


def summary(key):
    m = metrics[key]
    parts = ["%d frames @30 fps = %.2f s" % (m["frames"], m["duration_s"]), m["kind"]]
    if m["kind"] == "loop":
        parts.append("loop residual spread %.1f deg (%s)" % (m.get("loop_fix_max_deg", 0), m.get("loop_fix_worst_bone")))
    f = m["feet"]
    parts.append("planted slide L/R %.1f/%.1f cm" % (f["slide_l"] * 100, f["slide_r"] * 100) if "walk" not in key and "run" not in key
                 else "stride %.2f m/cycle, %.2f m/s" % (m.get("stride_per_cycle_m", 0), m.get("speed_mps", 0)))
    parts.append("max step %.1f deg (%s)" % (m["max_step_deg"], m["max_step_bone"]))
    if "seat" in m:
        parts.append("seat %.3f m" % m["seat"]["seat_height_m"])
    return " | ".join(parts)


def block(key, title, width):
    """Title line + front strip + side strip, scaled to `width`."""
    ims = []
    for v in ("front", "side"):
        p = os.path.join(FR, "%s_%s.png" % (key, v))
        im = Image.open(p).convert("RGB")
        ims.append(im.resize((width, int(im.height * width / im.width)), Image.LANCZOS))
    mf = manifest[key]
    head_h = 64
    lab_h = 22
    h = head_h + sum(i.height for i in ims) + lab_h
    c = Image.new("RGB", (width, h), BG)
    d = ImageDraw.Draw(c)
    d.text((14, 6), title, font=F_T, fill=INK)
    d.text((14, 38), "%s   [%s]" % (summary(key), metrics[key]["source_label"]), font=F_S, fill=DIM)
    y = head_h
    for im, v in zip(ims, ("front", "side")):
        c.paste(im, (0, y))
        d.text((8, y + 6), v, font=F_S, fill=DIM)
        y += im.height
    n = len(mf["frames"])
    for k, (f, t) in enumerate(zip(mf["frames"], mf["times"])):
        x = int((k + 0.5) * width / n)
        s = "f%d  %.2fs" % (f, t)
        tw = d.textlength(s, font=F_S)
        d.text((x - tw / 2, y + 2), s, font=F_S, fill=DIM)
    return c


def stack(blocks, path):
    w = max(b.width for b in blocks)
    h = sum(b.height for b in blocks) + 12 * (len(blocks) - 1)
    c = Image.new("RGB", (w, h), (225, 225, 230))
    y = 0
    for b in blocks:
        c.paste(b, (0, y))
        y += b.height + 12
    c.save(path, quality=84, optimize=True, progressive=True)
    print("wrote", os.path.relpath(path, REPO), c.size)


W = 1800
by_clip = {}
for j in jobs.JOBS:
    by_clip.setdefault(j["clip"], []).append(j["source"])
for clip, sources in by_clip.items():
    win = jobs.WINNERS.get(clip)
    keys = ["%s__%s" % (clip, s) for s in sources if "%s__%s" % (clip, s) in manifest]
    if win and "%s__%s" % (clip, win) in manifest:
        k = "%s__%s" % (clip, win)
        stack([block(k, "%s  (winner: %s)" % (clip, win), W)], os.path.join(OUT, "%s.jpg" % clip))
    if len(keys) > 1:
        order = sorted(keys, key=lambda k: (k.split("__")[1] != win, k))
        stack([block(k, "%s  -  %s%s" % (clip, k.split("__")[1], "  (winner)" if k.split("__")[1] == win else ""), W)
               for k in order], os.path.join(OUT, "compare_%s.jpg" % clip))


def labelled_rows(items, path, width=1800, head=40):
    """items: [(title, [image paths side by side])] -> one sheet, a titled row per item."""
    rows = []
    for title, paths in items:
        ims = [Image.open(p).convert("RGB") for p in paths if os.path.exists(p)]
        if not ims:
            continue
        h = max(i.height for i in ims)
        strip = Image.new("RGB", (sum(i.width for i in ims), h), BG)
        x = 0
        for i in ims:
            strip.paste(i, (x, 0))
            x += i.width
        strip = strip.resize((width, int(h * width / strip.width)), Image.LANCZOS)
        c = Image.new("RGB", (width, strip.height + head), BG)
        ImageDraw.Draw(c).text((14, 8), title, font=F_T, fill=INK)
        c.paste(strip, (0, head))
        rows.append(c)
    if rows:
        stack(rows, path)


# hands / feet close-ups (22_closeups.py): right hand front + side, left foot side, body 3/4
labelled_rows([("%s  frame %s  -  right hand front / side, left foot side, body 3/4" % tuple(f[8:-4].rsplit("_", 1)),
                [os.path.join(FR, f)])
               for f in sorted(os.listdir(FR)) if f.startswith("closeup_")],
              os.path.join(OUT, "closeups.jpg"))
# rest alignment (preview.py refpose:*): our A-pose rig posed into each source's rest pose
labelled_rows([("%s rest -> our rig (front, side)" % s,
                [os.path.join(FR, "refpose_%s_front.png" % s), os.path.join(FR, "refpose_%s_side.png" % s)])
               for s in ("m2m", "kaykit", "cmu")],
              os.path.join(OUT, "alignment.jpg"), width=900)

# metrics next to the sheets (PLAN 3.4 evidence); drop the wall-clock field (not reproducible)
pub = {k: {kk: vv for kk, vv in v.items() if kk != "seconds"} for k, v in metrics.items()}
with open(os.path.join(OUT, "metrics.json"), "w") as f:
    json.dump(pub, f, indent=1, sort_keys=True)
print("wrote", os.path.relpath(os.path.join(OUT, "metrics.json"), REPO))
