"""Compose the M0 style-frame contact sheet (called by tools/style-sheet.sh)."""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

S, out, ref = sys.argv[1], sys.argv[2], sys.argv[3]


def kb(k):
    return round(int(os.environ[k]) / 1024)


def font(sz, bold=False):
    f = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    return ImageFont.truetype(f, sz) if os.path.exists(f) else ImageFont.load_default()


W, H = 300, 450
rows = [("S1", ["All vertex color"], ["features = geometry", "0 textures", f"GLB {kb('B1')} KB"]),
        ("S2", ["Geometry +", "painted face"], ["face decal + iris", "2 textures", f"GLB {kb('B2')} KB"]),
        ("S3", ["Texture detail", "throughout"], ["+ cloth / hair detail", "6 textures", f"GLB {kb('B3')} KB"])]
cols = [("flat", "body"), ("flat", "face"), ("smooth", "body"), ("smooth", "face")]
LW, TH, REFW = 300, 60, 520
sheet = Image.new("RGB", (LW + W * 4 + REFW + 20, TH + H * 3 + 50), (236, 236, 238))
d = ImageDraw.Draw(sheet)
for ci, (sh, v) in enumerate(cols):
    d.text((LW + ci * W + 12, 18), f"{sh} facets · {v}", font=font(20, True), fill=(40, 40, 40))
for ri, (sid, name, info) in enumerate(rows):
    y = TH + ri * H
    d.text((18, y + 20), sid, font=font(52, True), fill=(47, 95, 208))
    for k, line in enumerate(name):
        d.text((18, y + 90 + k * 36), line, font=font(28, True), fill=(20, 20, 20))
    for k, line in enumerate(info):
        d.text((18, y + 100 + len(name) * 36 + k * 28), line, font=font(20), fill=(80, 80, 80))
    for ci, (sh, v) in enumerate(cols):
        sheet.paste(Image.open(os.path.join(S, f"{sid}_{sh}_{v}.png")).convert("RGB").resize((W, H)), (LW + ci * W, y))
r = Image.open(ref).convert("RGB")
r = r.resize((REFW, int(r.height * REFW / r.width)))
sheet.paste(r.crop((0, 0, REFW, min(r.height, H * 3))), (LW + W * 4 + 20, TH))
d.text((LW + W * 4 + 32, 18), "approved reference (2D)", font=font(20, True), fill=(40, 40, 40))
d.text((18, TH + H * 3 + 14), "One test character (MakeHuman CC0 anatomy -> 3.5k-tri low-poly), Babylon.js 9 on the Intel UHD 770, "
       "shared lighting rig. Same geometry in every row; only the surface treatment differs.", font=font(18), fill=(70, 70, 70))
sheet.save(out, optimize=True)
print(sheet.size, os.path.getsize(out))
