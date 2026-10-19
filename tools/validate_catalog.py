"""Valida um catálogo JSON (schema v2, docs Seção 6.2).

Uso: python tools/validate_catalog.py web/public/assets/catalog/test_room.json [--root web/public]

Confere: schema_version, campos obrigatórios, arquivos existentes (caminhos relativos a --root),
canais de máscara únicos, uv_range coerente com o *_uv_meta.json, light groups e opções.
Sai com código 1 se houver erro (avisos não falham).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TONE_OPS = {"standard", "aces", "agx", "lut"}


class Checker:
    def __init__(self, root: Path):
        self.root = root
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def file(self, rel: object, where: str) -> Path | None:
        if not isinstance(rel, str) or not rel:
            self.err(f"{where}: caminho ausente ou inválido")
            return None
        p = self.root / rel
        if not p.is_file():
            self.err(f"{where}: arquivo não existe → {rel}")
            return None
        return p


def uv_meta_path(uv_hi: str) -> str:
    if uv_hi.endswith("uv_hi.png"):
        return uv_hi[: -len("uv_hi.png")] + "uv_meta.json"
    return uv_hi.rsplit(".", 1)[0] + "_meta.json"


def validate(cat: dict, root: Path) -> Checker:
    c = Checker(root)
    if cat.get("schema_version") != 2:
        c.err(f"schema_version deve ser 2 (veio {cat.get('schema_version')!r})")
    for key in ("project_id", "camera", "base_passes", "configurable_slots"):
        if key not in cat:
            c.err(f"campo obrigatório ausente: {key}")
    tm = cat.get("tone_mapping", {})
    if tm and tm.get("operator") not in TONE_OPS:
        c.err(f"tone_mapping.operator deve ser um de {sorted(TONE_OPS)}")
    if tm.get("operator") == "lut":
        lut = tm.get("lut") or {}
        vals = lut.get("values", [])
        if not (2 <= len(vals) <= 256 and all(b >= a for a, b in zip(vals, vals[1:]))):
            c.err("tone_mapping.lut.values deve ter 2–256 valores crescentes")
        if not lut.get("log2_max", 0) > lut.get("log2_min", 0):
            c.err("tone_mapping.lut: log2_max deve ser maior que log2_min")

    bp = cat.get("base_passes", {})
    c.file(bp.get("beauty"), "base_passes.beauty")
    for opt in ("beauty_linear", "diffuse_light", "glossy", "shadow_ao", "uv_map"):
        if opt in bp:
            c.file(bp[opt], f"base_passes.{opt}")
    has_hilo = "uv_hi" in bp or "uv_lo" in bp
    if has_hilo:
        c.file(bp.get("uv_hi"), "base_passes.uv_hi")
        c.file(bp.get("uv_lo"), "base_passes.uv_lo")
        if bp.get("uv_encoding") != "u16_hilo":
            c.err("uv_encoding deve ser 'u16_hilo' quando há uv_hi/uv_lo")
        rng = bp.get("uv_range")
        if not (isinstance(rng, list) and len(rng) == 4 and rng[2] > rng[0] and rng[3] > rng[1]):
            c.err(f"uv_range inválido: {rng!r} (esperado [umin, vmin, umax, vmax])")
        elif isinstance(bp.get("uv_hi"), str):
            meta = root / uv_meta_path(bp["uv_hi"])
            if not meta.is_file():
                c.warn(f"uv_meta.json não encontrado ao lado do uv_hi ({meta.name}); uv_range não conferido")
            else:
                mr = json.loads(meta.read_text(encoding="utf-8")).get("uv_range")
                if mr is None or any(abs(a - b) > 1e-4 for a, b in zip(rng, mr)):
                    c.err(f"uv_range do catálogo {rng} difere do meta {mr} — rode o pack_uv de novo e atualize")
    elif "uv_map" not in bp:
        c.err("sem UV: informe uv_hi/uv_lo (preferido) ou uv_map")
    if "diffuse_light" not in bp:
        c.warn("sem diffuse_light: o motor vai usar o modo simplificado (shadow_ao)")
        if "shadow_ao" not in bp:
            c.err("sem diffuse_light e sem shadow_ao: não há como reiluminar o material")

    # máscaras: arquivo + canal únicos
    packed = bp.get("masks_packed", [])
    used: dict[tuple[int, str], str] = {}
    for i, mp in enumerate(packed):
        c.file(mp.get("file"), f"masks_packed[{i}].file")
        for ch in mp.get("channels", {}):
            if ch not in ("r", "g", "b"):
                c.err(f"masks_packed[{i}]: canal '{ch}' inválido (use r, g ou b)")

    slots = cat.get("configurable_slots", [])
    slot_ids = [s.get("id") for s in slots]
    if len(set(slot_ids)) != len(slot_ids):
        c.err(f"ids de slot repetidos: {slot_ids}")
    for s in slots:
        sid = s.get("id", "?")
        ref = s.get("mask_ref")
        if ref:
            key = (ref.get("file"), ref.get("channel"))
            if not isinstance(key[0], int) or key[0] >= len(packed):
                c.err(f"slot {sid}: mask_ref.file {key[0]!r} não existe em masks_packed")
            elif key[1] not in ("r", "g", "b"):
                c.err(f"slot {sid}: mask_ref.channel {key[1]!r} inválido")
            elif key in used:
                c.err(f"slot {sid}: canal {key} já usado pelo slot {used[key]}")
            else:
                used[key] = sid
                declared = packed[key[0]].get("channels", {}).get(key[1])
                if declared not in (None, sid):
                    c.err(f"slot {sid}: masks_packed[{key[0]}].{key[1]} está declarado como '{declared}'")
        elif "mask" in s:
            c.file(s["mask"], f"slot {sid}.mask")
        else:
            c.err(f"slot {sid}: sem mask_ref nem mask")

        gk = s.get("gloss_keep", 0.6)
        if not 0 <= gk <= 1:
            c.err(f"slot {sid}: gloss_keep fora de [0, 1]")
        aut = s.get("allow_user_transform", {})
        sc = aut.get("scale") if isinstance(aut, dict) else None
        if sc is not None and not (isinstance(sc, list) and len(sc) == 2 and 0 < sc[0] <= 1 <= sc[1]):
            c.err(f"slot {sid}: allow_user_transform.scale deve ser [min<=1, max>=1]")

        opts = s.get("options", [])
        oids = [o.get("id") for o in opts]
        if not opts:
            c.err(f"slot {sid}: sem opções")
        if len(set(oids)) != len(oids):
            c.err(f"slot {sid}: ids de opção repetidos")
        if s.get("default_texture") not in oids:
            c.err(f"slot {sid}: default_texture '{s.get('default_texture')}' não está nas opções")
        for o in opts:
            oid = f"{sid}/{o.get('id')}"
            if "diffuse_map" in o:
                c.file(o["diffuse_map"], f"{oid}.diffuse_map")
            elif "albedo_color" not in o and not o.get("keep_original"):
                c.err(f"{oid}: precisa de diffuse_map ou albedo_color")
            if "thumbnail" in o:
                c.file(o["thumbnail"], f"{oid}.thumbnail")
            ts = o.get("texture_size_m")
            if ts is not None and not (len(ts) == 2 and min(ts) > 0):
                c.err(f"{oid}: texture_size_m deve ter 2 valores > 0")
            if ts is None and "default_tiling" not in o and "diffuse_map" in o:
                c.warn(f"{oid}: sem texture_size_m nem default_tiling (tiling = 1)")
            tv = [t.get("id") for t in o.get("tint_variants", [])]
            if len(set(tv)) != len(tv):
                c.err(f"{oid}: tint_variants com ids repetidos")
            price = o.get("price")
            if price and (price.get("unit") != "m2" or price.get("value", -1) < 0):
                c.warn(f"{oid}: preço com unidade diferente de m2 ou valor negativo")

    lgs = cat.get("light_groups", [])
    if len(lgs) > 4:
        c.err(f"no máximo 4 light groups (vieram {len(lgs)})")
    for g in lgs:
        gid = g.get("id", "?")
        c.file(g.get("pass"), f"light_group {gid}.pass")
        r = g.get("range", [0, 2])
        if not (len(r) == 2 and 0 <= r[0] <= g.get("intensity", 1) <= r[1]):
            c.err(f"light_group {gid}: intensity fora do range {r}")
        k = g.get("kelvin", 6500)
        if not 1000 <= k <= 40000:
            c.err(f"light_group {gid}: kelvin {k} fora de 1000–40000")
    return c


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("catalog", type=Path)
    ap.add_argument("--root", type=Path, default=ROOT / "web" / "public")
    args = ap.parse_args(argv)
    try:
        cat = json.loads(args.catalog.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERRO: não consegui ler {args.catalog}: {e}", file=sys.stderr)
        return 1
    c = validate(cat, args.root)
    for w in c.warnings:
        print(f"aviso: {w}")
    for e in c.errors:
        print(f"ERRO: {e}", file=sys.stderr)
    if c.errors:
        print(f"{len(c.errors)} erro(s) em {args.catalog}", file=sys.stderr)
        return 1
    print(f"ok  {args.catalog}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
