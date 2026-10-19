"""Máscara PROVISÓRIA derivada dos passes, para quando o masks_a do render veio vazio.

Não substitui a máscara do Corona (CMasking_Mask): é uma heurística para conseguir testar a cena.
  parede (B) = pixels com UV válido e albedo (diff_color) igual à cor mais comum — reboco liso
  piso   (R) = pixels com UV válido, que não são parede, abaixo de --floor-min-y e dentro de --floor-uv

Uso:
  python tools/derive_masks.py renders/cam1 renders/cam1_derivado/masks_a.png [--prefix cam1_]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

import exr_io


def derive(dc: np.ndarray, uv: np.ndarray, floor_min_y: float, floor_uv: tuple[float, float], tol: float) -> tuple[np.ndarray, np.ndarray]:
    u, v = uv[..., 0], uv[..., 1]
    valid = (np.abs(u) + np.abs(v) > 1e-5) & (u > -0.01) & (v > -0.01) & np.isfinite(u) & np.isfinite(v)
    q = np.round(dc[valid] * 200).astype(int)
    keys, counts = np.unique(q, axis=0, return_counts=True)
    wall_color = keys[np.argmax(counts)] / 200
    wall = valid & (np.abs(dc - wall_color).max(-1) < tol)
    h = u.shape[0]
    rows = np.arange(h)[:, None] >= int(floor_min_y * h)
    floor = valid & ~wall & rows & (u <= floor_uv[0]) & (v <= floor_uv[1])
    return floor, wall


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("render_dir", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--prefix", default="cam1_")
    ap.add_argument("--floor-min-y", type=float, default=0.6, help="fração da altura da imagem onde o piso pode começar")
    ap.add_argument("--floor-uv", type=float, nargs=2, default=[8.42, 6.15], metavar=("UMAX", "VMAX"))
    ap.add_argument("--tol", type=float, default=0.01)
    a = ap.parse_args(argv)
    try:
        dc = exr_io.read_exr(a.render_dir / f"{a.prefix}diff_color.exr")[..., :3]
        uv = exr_io.read_exr(a.render_dir / f"{a.prefix}uv.exr")
    except OSError as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 1
    floor, wall = derive(dc, uv, a.floor_min_y, tuple(a.floor_uv), a.tol)
    m = np.zeros(floor.shape + (3,), np.uint8)
    m[..., 0] = floor * 255
    m[..., 2] = wall * 255
    exr_io.write_png(a.out, m)
    print(f"ok  {a.out}  piso {floor.mean() * 100:.1f}%  parede {wall.mean() * 100:.1f}%  (máscara PROVISÓRIA)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
