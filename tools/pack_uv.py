"""Empacota um UV pass (EXR, R = U, G = V em metros) em dois PNGs 8-bit (codificação u16_hilo).

Uso:
  python tools/pack_uv.py <uv.exr> <prefixo> [--mask mascara.png --mask-channel r]

Saída:
  <prefixo>_uv_hi.png   R = U byte alto, G = V byte alto, B = validade (255 = pixel com UV)
  <prefixo>_uv_lo.png   R = U byte baixo, G = V byte baixo, B = 0
  <prefixo>_uv_meta.json {"uv_encoding": "u16_hilo", "uv_range": [umin, vmin, umax, vmax]}

Se <prefixo> for uma pasta (ou terminar em / ou \\), os arquivos se chamam uv_hi.png etc.

Validade de cada pixel, em ordem de prioridade: --mask; canal alfa do EXR; senão, todos.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

import exr_io

CHANNELS = {"r": 0, "g": 1, "b": 2}


def output_paths(prefix: str | Path) -> dict[str, Path]:
    s = str(prefix)
    if s.endswith(("/", "\\")) or Path(s).is_dir():
        base = Path(s)
        return {k: base / f"uv_{k}.{ext}" for k, ext in [("hi", "png"), ("lo", "png"), ("meta", "json")]}
    return {k: Path(f"{s}_uv_{k}.{ext}") for k, ext in [("hi", "png"), ("lo", "png"), ("meta", "json")]}


def quantize(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    q = np.clip((x - lo) / max(hi - lo, 1e-9), 0.0, 1.0)
    return np.round(q * 65535).astype(np.uint16)


def pack_uv(uv: np.ndarray, valid: np.ndarray) -> tuple[np.ndarray, np.ndarray, list[float]]:
    """uv: (h, w, >=2) float; valid: (h, w) bool. Devolve (hi RGB u8, lo RGB u8, uv_range)."""
    u, v = uv[..., 0].astype(np.float64), uv[..., 1].astype(np.float64)
    if not valid.any():
        raise ValueError("nenhum pixel válido no UV (máscara/alfa vazios)")
    uu, vv = u[valid], v[valid]
    if not (np.isfinite(uu).all() and np.isfinite(vv).all()):
        raise ValueError("o UV tem NaN/Inf em pixels válidos")
    rng = [float(uu.min()), float(vv.min()), float(uu.max()), float(vv.max())]
    if rng[2] - rng[0] < 1e-6 or rng[3] - rng[1] < 1e-6:
        raise ValueError(f"uv_range degenerado {rng}: o UV pass está constante? confira o map channel")

    qu, qv = quantize(u, rng[0], rng[2]), quantize(v, rng[1], rng[3])
    qu[~valid] = 0
    qv[~valid] = 0
    hi = np.zeros(u.shape + (3,), np.uint8)
    lo = np.zeros(u.shape + (3,), np.uint8)
    hi[..., 0], hi[..., 1], hi[..., 2] = qu >> 8, qv >> 8, valid * 255
    lo[..., 0], lo[..., 1] = qu & 255, qv & 255
    return hi, lo, rng


def decode_uv(hi: np.ndarray, lo: np.ndarray, rng: list[float]) -> np.ndarray:
    """Espelho em numpy do decodeUV do shader (para testes)."""
    q = (hi[..., :2].astype(np.float64) * 256 + lo[..., :2]) / 65535.0
    mn, mx = np.array(rng[:2]), np.array(rng[2:])
    return mn + (mx - mn) * q


def load_valid(uv: np.ndarray, mask: Path | None, channel: str) -> np.ndarray:
    if mask is not None:
        m = exr_io.read_png(mask)
        if m.shape[:2] != uv.shape[:2]:
            raise ValueError(f"máscara {m.shape[:2]} e UV {uv.shape[:2]} têm resoluções diferentes")
        idx = CHANNELS[channel] if m.shape[2] >= 3 else 0
        return m[..., idx] > 127
    if uv.shape[2] == 4:
        return uv[..., 3] > 0.5
    return np.ones(uv.shape[:2], bool)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("uv_exr", type=Path)
    ap.add_argument("prefix")
    ap.add_argument("--mask", type=Path, help="PNG que define os pixels válidos")
    ap.add_argument("--mask-channel", choices=list(CHANNELS), default="r")
    args = ap.parse_args(argv)

    try:
        uv = exr_io.read_exr(args.uv_exr)
        if uv.shape[2] < 2:
            raise ValueError(f"{args.uv_exr} tem {uv.shape[2]} canal(is); o UV precisa de R = U e G = V")
        valid = load_valid(uv, args.mask, args.mask_channel)
        hi, lo, rng = pack_uv(uv, valid)
    except (OSError, ValueError) as e:
        print(f"ERRO pack_uv: {e}", file=sys.stderr)
        return 1

    out = output_paths(args.prefix)
    exr_io.write_png(out["hi"], hi)
    exr_io.write_png(out["lo"], lo)
    out["meta"].write_text(json.dumps({"uv_encoding": "u16_hilo", "uv_range": rng}, indent=2), encoding="utf-8")
    step_mm = max(rng[2] - rng[0], rng[3] - rng[1]) / 65535 * 1000
    print(f"ok  uv_range = [{rng[0]:.4f}, {rng[1]:.4f}, {rng[2]:.4f}, {rng[3]:.4f}]  (degrau ≈ {step_mm:.3f} mm)")
    print(f"    {out['hi']}\n    {out['lo']}\n    {out['meta']}")
    if max(rng[2], rng[3]) <= 1.0001 and min(rng[0], rng[1]) >= -1e-4:
        print("AVISO: o UV está entre 0 e 1 — ele não parece estar em metros (CLAUDE.md §2).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
