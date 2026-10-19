"""Empacota o UV da sala de teste e escreve web/public/assets/catalog/test_room.json.

Chamado no fim do make_test_assets.py; pode rodar sozinho:
  python tools/build_test_catalog.py [--out web/public/assets]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import exr_io
import make_test_assets as mta
import pack_uv

ROOT = Path(__file__).resolve().parents[1]
CAM = "assets/scenes/test_room/cam_main"
MAT = "assets/materials"


def material(mid: str, name: str, size: tuple[float, float] | None, price: float | None, **extra) -> dict:
    o: dict = {"id": mid, "name": name}
    ext = "png" if mid == "checker" else "webp"
    o["thumbnail"] = f"{MAT}/{mid}/thumb.webp"
    o["diffuse_map"] = f"{MAT}/{mid}/albedo.{ext}"
    if size:
        o["texture_size_m"] = list(size)
    o["default_tiling"] = [1.0, 1.0]
    if price is not None:
        o["price"] = {"value": price, "unit": "m2", "currency": "BRL"}
    o.update(extra)
    return o


def catalog(uv_range: list[float], w: int, h: int) -> dict:
    sizes = {k: v[1] for k, v in mta.MATERIALS.items()}
    area = round((mta.X1 - mta.X0) * (mta.Z1 - mta.Z0), 2)
    return {
        "schema_version": 2,
        "project_id": "test_room",
        "project_name": "Sala de teste",
        "camera": "cam_main",
        "camera_name": "Vista principal",
        "resolution": {"view": [w, h], "export": [w * 2, h * 2]},
        "tone_mapping": dict(mta.TONE),
        "base_passes": {
            "beauty": f"{CAM}/beauty.webp",
            "beauty_linear": f"{CAM}/beauty.exr",
            "uv_hi": f"{CAM}/uv_hi.png",
            "uv_lo": f"{CAM}/uv_lo.png",
            "uv_encoding": "u16_hilo",
            "uv_range": uv_range,
            "shadow_ao": f"{CAM}/shadow_ao.png",
            "diffuse_light": f"{CAM}/diff_light.exr",
            "glossy": f"{CAM}/glossy.exr",
            "masks_packed": [{"file": f"{CAM}/masks_a.png", "channels": {"r": "floor"}}],
        },
        "light_groups": [
            {"id": "sun", "name": "Sol da janela", "pass": f"{CAM}/lg_sun.exr",
             "intensity": 1.0, "kelvin": 5600, "range": [0, 3]},
            {"id": "ceiling", "name": "Luz ambiente", "pass": f"{CAM}/lg_ceiling.exr",
             "intensity": 1.0, "kelvin": 4000, "range": [0, 3]},
        ],
        "configurable_slots": [
            {
                "id": "floor",
                "name": "Piso",
                "mask_ref": {"file": 0, "channel": "r"},
                "default_texture": "oak",
                "allow_user_transform": {"scale": [0.5, 2.0], "rotation": True, "offset": True},
                "gloss_keep": 0.6,
                "area_m2": area,
                "options": [
                    material("oak", "Carvalho em régua", sizes["oak"], 189.9, sku="PISO-CARV-001",
                             finish="Madeira · réguas 1,20 × 0,20 m",
                             tint_variants=[
                                 {"id": "natural", "name": "Natural", "tint": [1.0, 1.0, 1.0]},
                                 {"id": "mel", "name": "Mel", "tint": [1.05, 0.88, 0.70]},
                                 {"id": "fume", "name": "Fumê", "tint": [0.55, 0.52, 0.50]},
                             ]),
                    material("marble", "Mármore Carrara", sizes["marble"], 890.0, sku="PEDRA-CARR-120",
                             finish="Pedra natural · placa 1,20 × 1,20 m", gloss_keep=0.85),
                    material("concrete", "Cimento queimado", sizes["concrete"], 120.0, sku="CIM-QUEI-100",
                             finish="Revestimento contínuo",
                             tint_variants=[
                                 {"id": "cinza", "name": "Cinza", "tint": [1.0, 1.0, 1.0]},
                                 {"id": "areia", "name": "Areia", "tint": [1.25, 1.12, 0.92]},
                             ]),
                    {"id": "original", "name": "Original do render", "albedo_color": [mta.FLOOR_ALBEDO] * 3,
                     "finish": "Cor do render, sem textura", "gloss_keep": 1.0},
                    material("checker", "Grade de teste", (1.0, 1.0), None, is_test=True,
                             finish="1 tile = 1 m · célula = 10 cm"),
                ],
            }
        ],
    }


def build_all(assets: Path) -> Path:
    cam_dir = assets / "scenes" / "test_room" / "cam_main"
    uv = exr_io.read_exr(cam_dir / "uv.exr")
    hi, lo, rng = pack_uv.pack_uv(uv, uv[..., 3] > 0.5)
    out = pack_uv.output_paths(str(cam_dir) + "/")
    exr_io.write_png(out["hi"], hi)
    exr_io.write_png(out["lo"], lo)
    out["meta"].write_text(json.dumps({"uv_encoding": "u16_hilo", "uv_range": rng}, indent=2), encoding="utf-8")

    h, w = uv.shape[:2]
    cat_path = assets / "catalog" / "test_room.json"
    cat_path.parent.mkdir(parents=True, exist_ok=True)
    cat_path.write_text(json.dumps(catalog(rng, w, h), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"catálogo: {cat_path}  uv_range = {[round(v, 4) for v in rng]}")
    return cat_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT / "web" / "public" / "assets")
    build_all(ap.parse_args().out)
