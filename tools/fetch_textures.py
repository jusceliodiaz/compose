"""Baixa as texturas da biblioteca (tools/material_library.json) da Poly Haven e da ambientCG (CC0) e prepara para a web.

Uso: python tools/fetch_textures.py [--res auto|1k|2k|4k] [--only id1,id2] [--force]

Para cada material com "polyhaven" (ou "ambientcg"):
  1. lê a medida física (Poly Haven: dimensions, em mm; ambientCG: "size_m" da biblioteca) e os autores;
  2. baixa o mapa Diffuse (albedo) em JPG — 2K, ou 4K quando a textura cobre ≥ 2,5 m (auto);
  3. "tintable": tira a cor da foto (luminância, média 0,5 linear) para as variações de cor funcionarem;
  4. grava web/public/assets/materials/lib/<id>/albedo.webp + thumb.webp, o manifest.json e CREDITS.md.

Os JPGs originais ficam em cache em tools/.cache/polyhaven (fora do git).
"""

from __future__ import annotations

import argparse
import io
import json
import shutil
import sys
import zipfile
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np

import exr_io

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "tools" / "material_library.json"
OUT = ROOT / "web" / "public" / "assets" / "materials" / "lib"
CACHE = ROOT / "tools" / ".cache" / "polyhaven"
API = "https://api.polyhaven.com"
UA = {"User-Agent": "compose-configurador/0.1 (texture fetch)"}
NEUTRAL_MEAN = 0.5  # luminância linear média das texturas neutralizadas (as cores do catálogo = tint × 0,5)


def get_json(url: str) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def download(url: str, dest: Path) -> Path:
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    tmp.replace(dest)
    return dest


def hex_to_linear(hx: str) -> np.ndarray:
    return exr_io.srgb_to_linear(np.array([int(hx[i:i + 2], 16) for i in (1, 3, 5)]) / 255.0)


def neutralize(srgb_u8: np.ndarray) -> np.ndarray:
    """Remove a cor mantendo trama/relevo: luminância linear normalizada para média NEUTRAL_MEAN."""
    lin = exr_io.srgb_to_linear(srgb_u8.astype(np.float32) / 255.0)
    y = exr_io.luminance(lin)
    y = y * (NEUTRAL_MEAN / max(float(y.mean()), 1e-4))
    return exr_io.to_u8(exr_io.linear_to_srgb(np.clip(np.repeat(y[..., None], 3, -1), 0, 1)))


def thumb(img: np.ndarray, tint_hex: str | None) -> np.ndarray:
    h, w = img.shape[:2]
    s = min(h, w)
    t = exr_io.resize_area(img[(h - s) // 2:(h + s) // 2, (w - s) // 2:(w + s) // 2], (256, 256))
    if tint_hex:  # miniatura já na primeira cor da paleta
        lin = exr_io.srgb_to_linear(t.astype(np.float32) / 255.0) * (hex_to_linear(tint_hex) / NEUTRAL_MEAN)
        t = exr_io.to_u8(exr_io.linear_to_srgb(np.clip(lin, 0, 1)))
    return t


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--res", default="auto", choices=["auto", "1k", "2k", "4k"])
    ap.add_argument("--only", help="ids da biblioteca, separados por vírgula")
    ap.add_argument("--force", action="store_true", help="reprocessa mesmo se já existir")
    args = ap.parse_args(argv)

    lib = json.loads(LIB.read_text(encoding="utf-8"))
    mats = {k: v for k, v in lib["materials"].items() if "polyhaven" in v or "ambientcg" in v}
    if args.only:
        wanted = set(args.only.split(","))
        mats = {k: v for k, v in mats.items() if k in wanted}
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    if not args.only:  # remove o que saiu da biblioteca
        for d in OUT.glob("*/"):
            if d.name not in mats:
                shutil.rmtree(d)
                manifest.pop(d.name, None)
                print(f"  - {d.name:22} removido (não está mais na biblioteca)")

    ok = 0
    for mid, m in mats.items():
        dest = OUT / mid
        src_id = m.get("polyhaven") or m.get("ambientcg")
        if not args.force and (dest / "albedo.webp").is_file() and manifest.get(mid, {}).get("id") == src_id:
            print(f"  = {mid:22} já existe")
            ok += 1
            continue
        pid = m.get("polyhaven") or m["ambientcg"]
        try:
            if "polyhaven" in m:
                info = get_json(f"{API}/info/{pid}")
                files = get_json(f"{API}/files/{pid}")
                dims_mm = info.get("dimensions") or [1000, 1000]
                size_m = m.get("size_m") or [round(dims_mm[0] / 1000, 4), round(dims_mm[1] / 1000, 4)]
                res = args.res if args.res != "auto" else ("4k" if max(size_m) >= 2.5 else "2k")
                diff = files["Diffuse"]
                if res not in diff:
                    res = sorted(diff, key=lambda r: abs(int(r[:-1]) - int(res[:-1])))[0]
                src = download(diff[res]["jpg"]["url"], CACHE / f"{pid}_{res}.jpg")
                img = cv2.imread(str(src), cv2.IMREAD_COLOR)
                authors = list((info.get("authors") or {}).keys())
                name, page = info.get("name", pid), f"https://polyhaven.com/a/{pid}"
            else:
                size_m = m["size_m"]
                res = args.res if args.res != "auto" else ("4k" if max(size_m) >= 2.5 else "2k")
                z = download(f"https://ambientcg.com/get?file={pid}_{res.upper()}-JPG.zip",
                             ROOT / "tools" / ".cache" / "ambientcg" / f"{pid}_{res}.zip")
                with zipfile.ZipFile(z) as zf:
                    color = [n for n in zf.namelist() if n.endswith("_Color.jpg")]
                    if not color:
                        raise IOError(f"zip sem *_Color.jpg: {zf.namelist()}")
                    buf = np.frombuffer(zf.read(color[0]), np.uint8)
                img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
                authors = ["ambientCG"]
                name, page = pid, f"https://ambientcg.com/view?id={pid}"
            if img is None:
                raise IOError(f"não consegui ler a imagem de {pid}")
            img = img[..., ::-1].copy()  # BGR → RGB
            palette = lib["palettes"].get(m["tintable"]) if m.get("tintable") else None
            if palette:
                img = neutralize(img)
            dest.mkdir(parents=True, exist_ok=True)
            exr_io.write_webp(dest / "albedo.webp", img, 90)
            exr_io.write_webp(dest / "thumb.webp", thumb(img, palette[0][2] if palette else None), 88)
            manifest[mid] = {
                "source": "polyhaven" if "polyhaven" in m else "ambientcg", "id": pid, "name": name,
                "size_m": size_m, "res": res, "pixels": [int(img.shape[1]), int(img.shape[0])],
                "neutralized": bool(palette), "authors": authors, "license": "CC0", "url": page,
            }
            kb = (dest / "albedo.webp").stat().st_size // 1024
            print(f"  ✓ {mid:22} {pid:28} {res}  {size_m[0]:.2f}×{size_m[1]:.2f} m  {kb} KB{'  (neutralizada)' if palette else ''}")
            ok += 1
            time.sleep(0.2)
        except Exception as e:  # noqa: BLE001 — segue para os próximos e relata no fim
            print(f"  ✗ {mid:22} {pid}: {e}", file=sys.stderr)

    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    credits = ["# Créditos das texturas", "",
               "[Poly Haven](https://polyhaven.com) e [ambientCG](https://ambientcg.com), licença CC0.", ""]
    for mid, e in sorted(manifest.items()):
        credits.append(f"- **{e['name']}** ({mid}) — {', '.join(e['authors']) or '—'} — {e['url']}")
    (OUT / "CREDITS.md").write_text("\n".join(credits) + "\n", encoding="utf-8")
    print(f"{ok}/{len(mats)} materiais prontos em {OUT}")
    return 0 if ok == len(mats) else 1


if __name__ == "__main__":
    sys.exit(main())
