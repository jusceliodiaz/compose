"""Gera a textura de teste (checker numerado): 1 tile = 1 m, 1 célula = 10 cm.

Uso: python tools/make_checker.py [saida.png] [--px 1024]

A origem da UV (0,0) fica no canto **inferior esquerdo** da imagem (convenção do WebGL com
flipY=true). As setas "U" (direita) e "V" (cima) ali mostram a orientação: se aparecerem
espelhadas ou invertidas na cena, há problema de flipY ou de rotação.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

import exr_io

CELLS = 10  # 10 × 10 células de 10 cm


def make_checker(px: int = 1024) -> np.ndarray:
    """Devolve o checker em sRGB uint8 RGB, px × px."""
    y, x = np.mgrid[0:px, 0:px]
    # linha 0 da imagem = topo = v próximo de 1; célula contada de baixo para cima
    cx = (x * CELLS) // px
    cy = ((px - 1 - y) * CELLS) // px
    even = (cx + cy) % 2 == 0
    img = np.where(even[..., None], np.array([232, 228, 220]), np.array([196, 205, 214])).astype(np.uint8)
    img = np.ascontiguousarray(img)

    bgr = img[..., ::-1].copy()  # desenho com OpenCV em BGR
    step = px / CELLS
    for i in range(CELLS + 1):
        p = int(round(i * step))
        cv2.line(bgr, (p, 0), (p, px), (150, 150, 150), 1)
        cv2.line(bgr, (0, p), (px, p), (150, 150, 150), 1)
    # borda do tile (1 m) bem marcada
    cv2.rectangle(bgr, (0, 0), (px - 1, px - 1), (40, 40, 200), max(2, px // 256))

    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = px / 1024 * 0.9
    for cy_ in range(CELLS):
        for cx_ in range(CELLS):
            n = cy_ * CELLS + cx_
            org = (int(cx_ * step + step * 0.22), int(px - cy_ * step - step * 0.35))
            cv2.putText(bgr, f"{n:02d}", org, font, scale, (60, 60, 60), max(1, px // 512), cv2.LINE_AA)

    # setas de orientação na origem (canto inferior esquerdo)
    o = (int(step * 0.15), int(px - step * 0.15))
    L = int(step * 1.6)
    th = max(2, px // 300)
    cv2.arrowedLine(bgr, o, (o[0] + L, o[1]), (30, 30, 220), th, cv2.LINE_AA, tipLength=0.15)  # U (vermelho)
    cv2.arrowedLine(bgr, o, (o[0], o[1] - L), (40, 160, 40), th, cv2.LINE_AA, tipLength=0.15)  # V (verde)
    cv2.putText(bgr, "U", (o[0] + L + 4, o[1] + 6), font, scale, (30, 30, 220), th, cv2.LINE_AA)
    cv2.putText(bgr, "V", (o[0] - 4, o[1] - L - 8), font, scale, (40, 160, 40), th, cv2.LINE_AA)
    return bgr[..., ::-1].copy()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", nargs="?", default="web/public/assets/materials/checker/albedo.png")
    ap.add_argument("--px", type=int, default=1024)
    args = ap.parse_args()
    img = make_checker(args.px)
    out = Path(args.out)
    exr_io.write_png(out, img)
    exr_io.write_webp(out.with_name("thumb.webp"), exr_io.resize_area(img, (256, 256)), 88)
    print(f"checker: {out}")


if __name__ == "__main__":
    main()
