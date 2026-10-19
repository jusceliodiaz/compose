"""Confere se os passes reconstroem o beauty (Combined).

Uso:
  python tools/reconstruct_check.py beauty.exr --mul diff_color.exr diff_light.exr --add glossy.exr [--add ...]
  python tools/reconstruct_check.py beauty.exr --add lg_sun.exr --add lg_ceiling.exr   # LightMix

reconstrução = Σ (produtos de --mul) + Σ (--add)
Imprime erro máximo, erro médio e PSNR (pico = 1.0, branco da tela, em linear).
Sai com código 1 se o PSNR ficar abaixo de --min-psnr (40 dB por padrão).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import exr_io


@dataclass
class Report:
    max_err: float
    mean_err: float
    psnr: float

    def __str__(self) -> str:
        return f"erro máx = {self.max_err:.6f}   erro médio = {self.mean_err:.6f}   PSNR = {self.psnr:.2f} dB"


def compare(beauty: np.ndarray, recon: np.ndarray) -> Report:
    if beauty.shape[:2] != recon.shape[:2]:
        raise ValueError(f"resoluções diferentes: beauty {beauty.shape[:2]} vs reconstrução {recon.shape[:2]}")
    d = recon[..., :3].astype(np.float64) - beauty[..., :3].astype(np.float64)
    mse = float(np.mean(d ** 2))
    psnr = float("inf") if mse == 0 else 10 * np.log10(1.0 / mse)
    return Report(float(np.abs(d).max()), float(np.abs(d).mean()), psnr)


def reconstruct(products: list[list[np.ndarray]], adds: list[np.ndarray]) -> np.ndarray:
    terms = [np.prod(np.stack([t[..., :3] for t in grp]), axis=0) for grp in products]
    terms += [a[..., :3] for a in adds]
    if not terms:
        raise ValueError("nenhum termo para reconstruir (use --mul e/ou --add)")
    return np.sum(np.stack(terms), axis=0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("beauty", type=Path)
    ap.add_argument("--mul", nargs="+", action="append", type=Path, default=[], metavar="EXR")
    ap.add_argument("--add", action="append", type=Path, default=[], metavar="EXR")
    ap.add_argument("--min-psnr", type=float, default=40.0)
    args = ap.parse_args(argv)

    try:
        beauty = exr_io.read_exr(args.beauty)
        recon = reconstruct([[exr_io.read_exr(p) for p in grp] for grp in args.mul],
                            [exr_io.read_exr(p) for p in args.add])
        rep = compare(beauty, recon)
    except (OSError, ValueError) as e:
        print(f"ERRO reconstruct_check: {e}", file=sys.stderr)
        return 2

    print(rep)
    if rep.psnr < args.min_psnr:
        print(f"FALHOU: PSNR abaixo de {args.min_psnr} dB — falta algum passe (emissão, refração, volume)?",
              file=sys.stderr)
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
