"""Deixa web/dist pronto para publicar: só os projetos do index.json, sem arquivos que o site não usa.

Rode depois do `npm run build`:
  python tools/prepare_dist.py

- mantém index.json, os catálogos listados nele e os arquivos que esses catálogos citam;
- apaga o resto de dist/assets (outras cenas, backups _beauty_anterior/_masks_originais, materiais fora do catálogo);
- regrava os EXR com compressão PIZ (sem perdas; costuma ser menor que ZIP em renders com ruído).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import Imath
import OpenEXR

ROOT = Path(__file__).resolve().parents[1]
KEEP_ALWAYS = {"assets/catalog/index.json", "assets/materials/lib/CREDITS.md"}


def referenced(dist: Path) -> set[str]:
    index = json.loads((dist / "assets/catalog/index.json").read_text(encoding="utf-8"))
    refs = set(KEEP_ALWAYS)
    for p in index["projects"]:
        cat_rel = p.get("catalog") or f"assets/catalog/{p['id']}.json"
        refs.add(cat_rel)
        text = (dist / cat_rel).read_text(encoding="utf-8")
        refs.update(re.findall(r"assets/[\w./-]+\.\w+", text))
    return refs


def to_piz(path: Path) -> int:
    src = OpenEXR.InputFile(str(path))
    h = src.header()
    if h["compression"] == Imath.Compression(Imath.Compression.PIZ_COMPRESSION):
        return 0
    data = {c: src.channel(c, h["channels"][c].type) for c in h["channels"]}
    src.close()
    before = path.stat().st_size
    h["compression"] = Imath.Compression(Imath.Compression.PIZ_COMPRESSION)
    tmp = path.with_suffix(".piz.tmp")
    out = OpenEXR.OutputFile(str(tmp), h)
    out.writePixels(data)
    out.close()
    tmp.replace(path)
    return before - path.stat().st_size


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dist", type=Path, default=ROOT / "web" / "dist")
    args = ap.parse_args(argv)
    dist = args.dist
    if not (dist / "assets/catalog/index.json").is_file():
        print(f"ERRO: {dist} não tem assets/catalog/index.json — rode o npm run build antes.", file=sys.stderr)
        return 1

    refs = referenced(dist)
    missing = sorted(r for r in refs if not (dist / r).is_file())
    if missing:
        print("ERRO: o catálogo cita arquivos que não existem:\n  " + "\n  ".join(missing), file=sys.stderr)
        return 1

    removed = 0
    for f in sorted((dist / "assets").rglob("*")):
        rel = f.relative_to(dist).as_posix()
        if f.is_file() and rel not in refs and f.suffix not in (".js", ".css"):
            removed += f.stat().st_size
            f.unlink()
    for d in sorted((dist / "assets").rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()

    saved = sum(to_piz(dist / r) for r in refs if r.endswith(".exr"))
    total = sum(f.stat().st_size for f in dist.rglob("*") if f.is_file() and ".vercel" not in f.parts)
    print(f"   removidos {removed / 1e6:.0f} MB sem uso · PIZ economizou {saved / 1e6:.0f} MB · dist = {total / 1e6:.0f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
