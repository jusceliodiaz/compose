"""Tira as plantas de dentro das máscaras das superfícies e aplica anti-aliasing guiado (Guided Filter).

Elimina serrilhados e blocos duros nas bordas usando a luminância do beauty render como guia fotométrico
(He et al., Guided Image Filtering). Bordas de folhas, móveis e paredes ganham gradientes sub-pixel suaves,
impedindo artefatos em escada ou recortes de blocos quadrados no WebGL.

Uso:
  python tools/refine_plant_masks.py web/public/assets/catalog/sala_estar.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import exr_io  # antes do cv2: liga o OpenEXR
import cv2
import numpy as np

import import_corona

ROOT = Path(__file__).resolve().parents[1]


def ramp(x: np.ndarray, a: float, b: float) -> np.ndarray:
    return np.clip((x - a) / (b - a), 0.0, 1.0)


def guided_filter(I: np.ndarray, p: np.ndarray, r: int = 5, eps: float = 1e-3) -> np.ndarray:
    """Filtro guiado (Guided Filter): preserva e alinha bordas com o render real I em O(N)."""
    mean_I = cv2.boxFilter(I, cv2.CV_64F, (r, r))
    mean_p = cv2.boxFilter(p, cv2.CV_64F, (r, r))
    mean_Ip = cv2.boxFilter(I * p, cv2.CV_64F, (r, r))
    cov_Ip = mean_Ip - mean_I * mean_p

    mean_II = cv2.boxFilter(I * I, cv2.CV_64F, (r, r))
    var_I = mean_II - mean_I * mean_I

    a = cov_Ip / (var_I + eps)
    b = mean_p - a * mean_I

    mean_a = cv2.boxFilter(a, cv2.CV_64F, (r, r))
    mean_b = cv2.boxFilter(b, cv2.CV_64F, (r, r))

    q = mean_a * I + mean_b
    return np.clip(q, 0.0, 1.0).astype(np.float32)


def foliage_alpha(rgb_u8: np.ndarray, reach_px: int = 6) -> np.ndarray:
    """0..1: probabilidade contínua de ser folha/planta com transição suave."""
    hsv = cv2.cvtColor(rgb_u8, cv2.COLOR_RGB2HSV).astype(np.float32)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    g_minus_r = rgb_u8[..., 1].astype(np.float32) - rgb_u8[..., 0].astype(np.float32)

    raw_alpha = (
        ramp(h, 22, 32)
        * (1.0 - ramp(h, 92, 102))
        * ramp(s, 40, 85)
        * ramp(v, 30, 65)
        * ramp(g_minus_r, -10, 15)
    )

    core = ((h >= 28) & (h <= 95) & (s >= 75) & (v >= 50) & (g_minus_r >= 8)).astype(np.float32)
    core = cv2.morphologyEx(core, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    
    alpha = raw_alpha * np.clip(cv2.dilate(core, np.ones((reach_px * 2 + 1, reach_px * 2 + 1), np.uint8)), 0.0, 1.0)
    return cv2.GaussianBlur(alpha, (5, 5), 1.2)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("catalog", type=Path)
    ap.add_argument("--web-root", type=Path, default=ROOT / "web" / "public")
    args = ap.parse_args(argv)

    cat = json.loads(args.catalog.read_text(encoding="utf-8"))
    bp = cat["base_passes"]
    cam = args.web_root / Path(bp["beauty"]).parent
    beauty = exr_io.read_png(args.web_root / bp["beauty"])[..., :3]
    gray_beauty = cv2.cvtColor(beauty, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0

    print("Refinando máscaras com Guided Filter e proteção de folhagens...")
    alpha = foliage_alpha(beauty)
    alpha = guided_filter(gray_beauty, alpha, r=4, eps=1e-3)

    backup = cam / "_masks_originais"
    backup.mkdir(exist_ok=True)
    slot_masks = {}

    for i, mp in enumerate(bp["masks_packed"]):
        path = args.web_root / mp["file"]
        orig = backup / path.name
        if not orig.exists():
            shutil.copy2(path, orig)
        
        m = exr_io.read_png(orig)[..., :3].astype(np.float32) / 255.0
        before = (m > 0.5).sum(axis=(0, 1))

        # 1. Remove folhagem de paredes, sofás e pisos que estão atrás da planta
        m *= (1.0 - alpha)[..., None]

        # 2. Suavização guiada anti-serrilhado em cada canal da máscara
        for ch_idx in range(3):
            ch_data = m[..., ch_idx]
            if ch_data.max() > 0.01:
                # Guided filter ajusta a borda exatamente à silhueta visual do render
                m[..., ch_idx] = guided_filter(gray_beauty, ch_data, r=3, eps=1e-3)

        removed = before - (m > 0.5).sum(axis=(0, 1))
        exr_io.write_png(path, np.round(m * 255).astype(np.uint8))

        for ch, sid in mp["channels"].items():
            k = "rgb".index(ch)
            slot_masks[sid] = m[..., k]
            print(f"   {sid:<10} ajustado com sucesso (−{int(removed[k])} px de folhagem/artefatos)")

    for sid, m in slot_masks.items():
        import_corona.original_thumb(beauty, m, cam / f"thumb_original_{sid}.webp")

    print("\nMáscaras refinadas com Guided Filter e anti-aliasing sub-pixel aplicado!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
