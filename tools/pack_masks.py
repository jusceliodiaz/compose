"""Junta até 3 máscaras P/B num único PNG RGB (3 slots por arquivo).

Uso:
  python tools/pack_masks.py -o masks_a.png --r floor=piso.png --g wall=parede.exr [--b sofa=sofa.png]

Cada máscara pode ser PNG/WebP 8-bit ou EXR (usa o primeiro canal, recortado em [0, 1]).
Grava também <saida>.json com o mapeamento: {"channels": {"r": "floor", "g": "wall"}}.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

import exr_io


def load_mask(path: Path) -> np.ndarray:
    """Devolve a máscara em float [0, 1], 2D."""
    if path.suffix.lower() == ".exr":
        m = exr_io.read_exr(path)[..., 0]
    else:
        img = exr_io.read_png(path)
        if img.dtype != np.uint8:
            raise ValueError(f"{path}: esperado 8-bit, veio {img.dtype}")
        m = img[..., 0].astype(np.float32) / 255.0
    return np.clip(m, 0.0, 1.0)


def pack_masks(masks: dict[str, np.ndarray]) -> np.ndarray:
    """masks: {'r'|'g'|'b': float 2D}. Devolve uint8 RGB."""
    if not masks:
        raise ValueError("informe ao menos uma máscara (--r/--g/--b)")
    shapes = {m.shape for m in masks.values()}
    if len(shapes) != 1:
        raise ValueError(f"as máscaras têm resoluções diferentes: {sorted(shapes)}")
    h, w = shapes.pop()
    out = np.zeros((h, w, 3), np.uint8)
    for ch, m in masks.items():
        out[..., "rgb".index(ch)] = exr_io.to_u8(m)
    return out


def parse_spec(spec: str) -> tuple[str, Path]:
    if "=" not in spec:
        raise argparse.ArgumentTypeError(f"use slot=arquivo, recebi '{spec}'")
    slot, path = spec.split("=", 1)
    return slot.strip(), Path(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", type=Path, required=True)
    for ch in "rgb":
        ap.add_argument(f"--{ch}", type=parse_spec, metavar="SLOT=ARQUIVO")
    args = ap.parse_args(argv)

    specs = {ch: getattr(args, ch) for ch in "rgb" if getattr(args, ch)}
    names = [s[0] for s in specs.values()]
    if len(set(names)) != len(names):
        print("ERRO pack_masks: o mesmo slot aparece em dois canais", file=sys.stderr)
        return 1
    try:
        masks = {ch: load_mask(p) for ch, (_, p) in specs.items()}
        rgb = pack_masks(masks)
    except (OSError, ValueError) as e:
        print(f"ERRO pack_masks: {e}", file=sys.stderr)
        return 1

    exr_io.write_png(args.out, rgb)
    mapping = {"channels": {ch: s[0] for ch, s in specs.items()}}
    args.out.with_suffix(".json").write_text(json.dumps(mapping, indent=2), encoding="utf-8")
    print(f"ok  {args.out}  {mapping['channels']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
