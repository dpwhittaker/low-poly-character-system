"""P6 step 0: download the animation sources (pinned revisions, sha256-checked).

  ~/ml-env/bin/python -I pipeline/blender/m1_anim/fetch_sources.py

Everything lands in pipeline/blender/m1_anim/_downloads/<source>/ (git-ignored), one new
directory per source. Downloads are DATA: they are parsed by lib_anim.py's own readers and never
executed. Licence texts are fetched next to the data for the record (see README "Sources").
"""
import hashlib
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DL = os.path.join(HERE, "_downloads")

M2M = "https://raw.githubusercontent.com/Mesh2Motion/mesh2motion-app/653a9698f5f315523072f1c3ff3496100401317b/"
KK = ("https://raw.githubusercontent.com/KayKit-Game-Assets/KayKit-Character-Pack-Adventures-1.0/"
      "672074b73ba276876a19e8816ecdc5241817ab47/")
CMU = "http://mocap.cs.cmu.edu/subjects/"

FILES = [  # (subdir, url, sha256 or None for licence/readme texts)
    ("m2m", M2M + "static/animations/human-base-animations.glb",
     "406eb0a8dc4ab366e623b79b6e3005a4951392e1bda78ae39c1099d31147733c"),
    ("m2m", M2M + "static/animations/human-addon-animations.glb",
     "a0d64d555e0d492026b72d58bf8e16c5e86779295f9093e376dcc001915c2c95"),
    ("m2m_text", M2M + "LICENSE-CC0.MD", None),
    ("m2m_text", M2M + "LICENSE-MIT.MD", None),
    ("m2m_text", M2M + "README.md", None),
    ("kaykit", KK + "addons/kaykit_character_pack_adventures/Characters/gltf/Rogue.glb",
     "e825437cd4d2ee9c1960b517a74a69101e33eb409ae7fa8cedc7134a998fbb7d"),
    ("kaykit_text", KK + "LICENSE.txt", None),
    ("cmu", CMU + "113/113.asf", "7787c299639b95360a6469542d6543002b0b2d2d1cb6866c20bc11651ea74d63"),
    ("cmu", CMU + "113/113_07.amc", "bf40bb42b5548312703ffce5cf443dd16d8da5ad2cf94af9dca7c49bf0129c98"),
    ("cmu", CMU + "113/113_15.amc", "b79c8ca94eb6b42c457780aac0bc13355144a2c56d2f3bec13ce666db9e3effa"),
    ("cmu", CMU + "113/113_21.amc", "44fcfef5adbb5f6497c7878576aa9f3b4ad085ec3e9e797cff695d63a839acfc"),
    ("cmu", CMU + "113/113_23.amc", "ef41267a6fe1c0df5ce58bc2e26acd7e445db6b0042f63cdb8823e147f5c91a2"),
    ("cmu", CMU + "113/113_25.amc", "e304c7c1d993a75415dfb383a04ddfe83720e18ff94f89e9b76e83ffb520fbe4"),
    ("cmu", CMU + "113/113_27.amc", "0ac3e7b7f56d368fe894c0fe73fdf16cb1734adc7b3bb0365523ea3a8511ea70"),
    ("cmu_text", "http://mocap.cs.cmu.edu/", None),  # licence paragraph is on the home page
]


def main():
    bad = 0
    for sub, url, want in FILES:
        d = os.path.join(DL, sub)
        os.makedirs(d, exist_ok=True)
        name = url.rstrip("/").split("/")[-1] if not url.endswith("/") else "home.html"
        dst = os.path.join(d, name)
        if not os.path.exists(dst):
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (P6 fetch)"})
            with urllib.request.urlopen(req, timeout=120) as r, open(dst, "wb") as f:
                f.write(r.read())
        got = hashlib.sha256(open(dst, "rb").read()).hexdigest()
        ok = want is None or got == want
        bad += not ok
        print("%-4s %s %s" % ("ok" if ok else "BAD", got[:12], os.path.relpath(dst, HERE)))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
