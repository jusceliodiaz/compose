"""Atualiza as opções de material (e o leque rápido) de um catálogo já importado, a partir da biblioteca —
sem reimportar os renders. Use depois de editar tools/material_library.json e rodar fetch_textures.py.

Uso:
  python tools/update_catalog_materials.py web/public/assets/catalog/sala_estar.json
  python tools/update_catalog_materials.py <catalogo.json> --kind piso=floor --kind sofa=fabric   # catálogos antigos

O tipo de cada superfície vem de "material_kind" (gravado pelo import_corona.py) ou de --kind.
A opção "Original do render" e as escolhas que ainda existirem são mantidas.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import import_corona
import validate_catalog

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("catalog", type=Path)
    ap.add_argument("--kind", action="append", default=[], help="slot=tipo (floor/stone/paint/fabric/rug/cabinet)")
    ap.add_argument("--web-root", type=Path, default=ROOT / "web" / "public")
    args = ap.parse_args(argv)

    kinds = dict(k.split("=", 1) for k in args.kind)
    cat = json.loads(args.catalog.read_text(encoding="utf-8"))
    for slot in cat["configurable_slots"]:
        kind = kinds.get(slot["id"]) or slot.get("material_kind")
        if kind not in import_corona.KINDS:
            print(f"ERRO: slot {slot['id']} sem tipo de material — use --kind {slot['id']}=<tipo>", file=sys.stderr)
            return 1
        original = [o for o in slot["options"] if o.get("keep_original")]
        opts = [*original, *import_corona.library(kind, args.web_root)]
        ids = {o["id"] for o in opts}
        if slot.get("default_texture") not in ids:
            slot["default_texture"] = opts[0]["id"]
        slot["material_kind"] = kind
        slot["options"] = opts
        slot["quick_options"] = import_corona.quick_options(kind, opts)
        slot["gloss_keep"] = import_corona.GLOSS_KEEP[kind]
        trio = ", ".join(q["option"] + (f"/{q['variant']}" if "variant" in q else "") for q in slot["quick_options"])
        print(f"   {slot['id']:<9} {kind:<8} {len(opts):2d} opções · leque: {trio}")

    chk = validate_catalog.validate(cat, args.web_root)
    for e in chk.errors:
        print(f"ERRO: {e}", file=sys.stderr)
    if chk.errors:
        return 1
    args.catalog.write_text(json.dumps(cat, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"ok  {args.catalog}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
