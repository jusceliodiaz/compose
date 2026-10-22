"""Importa os passes renderizados da pasta 'renders/sala 2' com as 5 máscaras perfeitas do 3ds Max.
"""

from __future__ import annotations
import json
from pathlib import Path
import sys
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import exr_io
import pack_uv
import reconstruct_check
import validate_catalog
from catalog_index import update_index


def to_single_channel(arr: np.ndarray) -> np.ndarray:
    """Extrai canal binário/escala de cinza de uma máscara EXR."""
    if arr.ndim == 2:
        return arr
    # Pega o máximo dos canais RGB
    return np.clip(np.max(arr[..., :3], axis=-1), 0.0, 1.0)


def run_import():
    render_dir = ROOT / "renders" / "sala 2"
    public_dir = ROOT / "web" / "public"
    rel_cam = "assets/scenes/sala_estar/cam7"
    dest_dir = public_dir / rel_cam
    dest_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== IMPORTANDO SALA DE ESTAR (PASTA: {render_dir}) ===")
    print(f"Destino Web: {dest_dir}")

    # 1. Carrega passes obrigatórios
    beauty_path = render_dir / "cam7_.exr"
    uv_path = render_dir / "cam7__uv.exr"
    diff_light_path = render_dir / "cam7__diff_light.exr"
    diff_color_path = render_dir / "cam7__diff_color.exr"
    reflect_path = render_dir / "cam7__reflect.exr"

    if not beauty_path.is_file():
        print(f"ERRO: beauty não encontrado: {beauty_path}")
        return 1

    beauty = exr_io.read_exr(beauty_path)[..., :3]
    h, w = beauty.shape[:2]
    print(f"Resolução da cena: {w}x{h}")

    # 2. Carrega as 5 máscaras do Corona
    mask_files = {
        "sofa": render_dir / "cam7__masks_a.exr",
        "piso": render_dir / "cam7__masks_b.exr",
        "carpet": render_dir / "cam7__masks_c.exr",
        "parede": render_dir / "cam7__masks_d.exr",
        "armario_cima": render_dir / "cam7__masks_e.exr",
    }

    raw_masks = {}
    for name, p in mask_files.items():
        if p.is_file():
            raw_masks[name] = to_single_channel(exr_io.read_exr(p))
            cov = (raw_masks[name] > 0.5).mean() * 100
            print(f"  + Máscara '{name}': {cov:.2f}% de cobertura")
        else:
            print(f"  AVISO: Máscara '{name}' não encontrada em {p}, gerando vazia.")
            raw_masks[name] = np.zeros((h, w), dtype=np.float32)

    # 3. Empacota em 2 PNGs de 3 canais (RGB)
    # File 0 (masks_a.png): R=sofa, G=piso, B=carpet
    # File 1 (masks_b.png): R=parede, G=armario_cima, B=zeros
    mask_a_rgb = np.zeros((h, w, 3), dtype=np.uint8)
    mask_a_rgb[..., 0] = (np.clip(raw_masks["sofa"], 0, 1) * 255).astype(np.uint8)
    mask_a_rgb[..., 1] = (np.clip(raw_masks["piso"], 0, 1) * 255).astype(np.uint8)
    mask_a_rgb[..., 2] = (np.clip(raw_masks["carpet"], 0, 1) * 255).astype(np.uint8)

    mask_b_rgb = np.zeros((h, w, 3), dtype=np.uint8)
    mask_b_rgb[..., 0] = (np.clip(raw_masks["parede"], 0, 1) * 255).astype(np.uint8)
    mask_b_rgb[..., 1] = (np.clip(raw_masks["armario_cima"], 0, 1) * 255).astype(np.uint8)

    exr_io.write_png(dest_dir / "masks_a.png", mask_a_rgb)
    exr_io.write_png(dest_dir / "masks_b.png", mask_b_rgb)
    print("  + Máscaras empacotadas em masks_a.png e masks_b.png salvas com sucesso!")

    # 4. UV -> hi/lo (Canal 2)
    if uv_path.is_file():
        uv = exr_io.read_exr(uv_path)
        valid = (raw_masks["piso"] > 0.5) | (raw_masks["sofa"] > 0.5) | (raw_masks["carpet"] > 0.5) | (raw_masks["parede"] > 0.5) | (raw_masks["armario_cima"] > 0.5)
        hi, lo, uv_range = pack_uv.pack_uv(uv, valid)
        exr_io.write_png(dest_dir / "uv_hi.png", hi)
        exr_io.write_png(dest_dir / "uv_lo.png", lo)
        (dest_dir / "uv_meta.json").write_text(json.dumps({"uv_encoding": "u16_hilo", "uv_range": uv_range}, indent=2), encoding="utf-8")
        print(f"  + UV empacotado: uv_range = {uv_range}")
    else:
        print("ERRO: cam7__uv.exr não encontrado!")
        return 1

    # 5. Passes de luz (EXR half)
    exr_io.write_exr(dest_dir / "beauty.exr", beauty.astype(np.float32))
    ldr = exr_io.to_u8(exr_io.linear_to_srgb(np.clip(beauty, 0.0, 1.0)))
    exr_io.write_webp(dest_dir / "beauty.webp", ldr, 92)

    if diff_light_path.is_file():
        dl = exr_io.read_exr(diff_light_path)[..., :3]
        exr_io.write_exr(dest_dir / "diff_light.exr", dl.astype(np.float32))
    else:
        print("  AVISO: diff_light não encontrado, usando beauty como fallback")
        exr_io.write_exr(dest_dir / "diff_light.exr", beauty.astype(np.float32))

    if reflect_path.is_file():
        rf = exr_io.read_exr(reflect_path)[..., :3]
        exr_io.write_exr(dest_dir / "glossy.exr", rf.astype(np.float32))

    # Grupos de luz (Sol e Céu)
    for g in ["sol", "sky"]:
        lg_p = render_dir / f"cam7__lg_{g}.exr"
        if lg_p.is_file():
            exr_io.write_exr(dest_dir / f"lg_{g}.exr", exr_io.read_exr(lg_p)[..., :3].astype(np.float32))
            print(f"  + LightGroup lg_{g}.exr exportado")

    # 6. Thumbnails originais
    for sid, m_arr in raw_masks.items():
        ys, xs = np.nonzero(m_arr > 0.5)
        if ys.size > 0:
            cy, cx = int(np.median(ys)), int(np.median(xs))
            side = int(min(max(np.percentile(ys, 90) - np.percentile(ys, 10), np.percentile(xs, 90) - np.percentile(xs, 10), 64), min(h, w)))
            y0 = int(np.clip(cy - side // 2, 0, h - side))
            x0 = int(np.clip(cx - side // 2, 0, w - side))
            crop = ldr[y0:y0+side, x0:x0+side]
            exr_io.write_webp(dest_dir / f"thumb_original_{sid}.webp", exr_io.resize_area(crop, (256, 256)), 88)

    # 7. Biblioteca de materiais para cada um dos 5 slots
    from import_corona import library, PAINTS

    slots_config = [
        {
            "id": "piso",
            "name": "Piso",
            "mask_ref": {"file": 0, "channel": "g"},
            "default_texture": "original",
            "allow_user_transform": {"scale": [0.5, 2.0], "rotation": True, "offset": True},
            "gloss_keep": 0.6,
            "area_m2": 42.0,
            "options": [
                {"id": "original", "name": "Original do render", "keep_original": True, "thumbnail": f"{rel_cam}/thumb_original_piso.webp", "finish": "Madeira original do render"},
                *library("floor")
            ]
        },
        {
            "id": "sofa",
            "name": "Sofá",
            "mask_ref": {"file": 0, "channel": "r"},
            "default_texture": "original",
            "allow_user_transform": {"scale": [0.5, 2.0], "rotation": False, "offset": False},
            "gloss_keep": 0.2,
            "area_m2": 12.0,
            "options": [
                {"id": "original", "name": "Original do render", "keep_original": True, "thumbnail": f"{rel_cam}/thumb_original_sofa.webp", "finish": "Estofado original do render"},
                {"id": "linho_cru", "name": "Linho Cru", "albedo_color": [0.78, 0.74, 0.68], "finish": "Tecido natural"},
                {"id": "veludo_cinza", "name": "Veludo Cinza", "albedo_color": [0.35, 0.35, 0.36], "finish": "Veludo toque suave"},
                {"id": "couro_caramelo", "name": "Couro Caramelo", "albedo_color": [0.55, 0.28, 0.12], "finish": "Couro legítimo"},
                {"id": "verde_musgo", "name": "Verde Musgo", "albedo_color": [0.22, 0.30, 0.18], "finish": "Linho misto"},
                {"id": "azul_marinho", "name": "Azul Marinho", "albedo_color": [0.08, 0.12, 0.22], "finish": "Brim peletizado"}
            ]
        },
        {
            "id": "carpet",
            "name": "Tapete",
            "mask_ref": {"file": 0, "channel": "b"},
            "default_texture": "original",
            "allow_user_transform": {"scale": [0.5, 2.0], "rotation": False, "offset": False},
            "gloss_keep": 0.1,
            "area_m2": 15.0,
            "options": [
                {"id": "original", "name": "Original do render", "keep_original": True, "thumbnail": f"{rel_cam}/thumb_original_carpet.webp", "finish": "Tapete original do render"},
                {"id": "off_white", "name": "Off White Bouclê", "albedo_color": [0.85, 0.84, 0.82], "finish": "Bouclê macio"},
                {"id": "cinza_claro", "name": "Cinza Mescla", "albedo_color": [0.55, 0.55, 0.55], "finish": "Fio de lã"},
                {"id": "terracota_tapete", "name": "Terracota", "albedo_color": [0.46, 0.16, 0.08], "finish": "Algodão tingido"},
                {"id": "areia_fio", "name": "Areia", "albedo_color": [0.68, 0.61, 0.48], "finish": "Fibra natural"}
            ]
        },
        {
            "id": "parede",
            "name": "Paredes",
            "mask_ref": {"file": 1, "channel": "r"},
            "default_texture": "original",
            "allow_user_transform": {"scale": [0.5, 2.0], "rotation": False, "offset": False},
            "gloss_keep": 0.15,
            "area_m2": 65.0,
            "options": [
                {"id": "original", "name": "Original do render", "keep_original": True, "thumbnail": f"{rel_cam}/thumb_original_parede.webp", "finish": "Tinta original do render"},
                *library("paint")
            ]
        },
        {
            "id": "armario_cima",
            "name": "Armário Superior",
            "mask_ref": {"file": 1, "channel": "g"},
            "default_texture": "original",
            "allow_user_transform": {"scale": [0.5, 2.0], "rotation": False, "offset": False},
            "gloss_keep": 0.4,
            "area_m2": 8.0,
            "options": [
                {"id": "original", "name": "Original do render", "keep_original": True, "thumbnail": f"{rel_cam}/thumb_original_armario_cima.webp", "finish": "Acabamento original do render"},
                {"id": "verde_salvia", "name": "Verde Sálvia Original", "albedo_color": [0.36, 0.42, 0.31], "finish": "Laca fosca"},
                {"id": "branco_acetinado", "name": "Branco Acetinado", "albedo_color": [0.88, 0.88, 0.87], "finish": "Laca acetinada"},
                {"id": "nogueira", "name": "Nogueira Escura", "albedo_color": [0.25, 0.18, 0.12], "finish": "Lâmina de madeira natural"},
                {"id": "grafite", "name": "Grafite Profundo", "albedo_color": [0.07, 0.07, 0.06], "finish": "Laca fosca texturizada"},
                {"id": "areia_quente", "name": "Areia Quente", "albedo_color": [0.69, 0.60, 0.45], "finish": "Microtextura"}
            ]
        }
    ]

    catalog = {
        "schema_version": 2,
        "project_id": "sala_estar",
        "project_name": "Sala de Estar",
        "camera": "cam7",
        "camera_name": "CoronaCamera007",
        "resolution": {"view": [w, h], "export": [w, h]},
        "tone_mapping": {"operator": "standard", "exposure": 1.0},
        "base_passes": {
            "beauty": f"{rel_cam}/beauty.webp",
            "beauty_linear": f"{rel_cam}/beauty.exr",
            "uv_hi": f"{rel_cam}/uv_hi.png",
            "uv_lo": f"{rel_cam}/uv_lo.png",
            "uv_encoding": "u16_hilo",
            "uv_range": uv_range,
            "diffuse_light": f"{rel_cam}/diff_light.exr",
            "glossy": f"{rel_cam}/glossy.exr",
            "masks_packed": [
                {
                    "file": f"{rel_cam}/masks_a.png",
                    "channels": {"r": "sofa", "g": "piso", "b": "carpet"}
                },
                {
                    "file": f"{rel_cam}/masks_b.png",
                    "channels": {"r": "parede", "g": "armario_cima"}
                }
            ]
        },
        "light_groups": [
            {"id": "sky", "name": "Céu (Sky)", "pass": f"{rel_cam}/lg_sky.exr", "intensity": 1.0, "kelvin": 6500, "range": [0, 3]},
            {"id": "sol", "name": "Sol", "pass": f"{rel_cam}/lg_sol.exr", "intensity": 1.0, "kelvin": 6500, "range": [0, 3]}
        ],
        "configurable_slots": slots_config
    }

    cat_dir = public_dir / "assets" / "catalog"
    cat_dir.mkdir(parents=True, exist_ok=True)
    cat_path = cat_dir / "sala_estar.json"
    cat_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Catálogo salvo em {cat_path}")

    update_index(cat_dir, "sala_estar", "Sala de Estar", make_default=True)
    print("index.json atualizado com sala_estar como default!")

    chk = validate_catalog.validate(catalog, public_dir)
    for wm in chk.warnings:
        print(f"  aviso: {wm}")
    for err in chk.errors:
        print(f"  ERRO: {err}", file=sys.stderr)
    if chk.errors:
        return 1

    print("\n>>> SUCESSO: SALA DE ESTAR IMPORTADA COM 5 SLOTS! <<<")
    return 0


if __name__ == "__main__":
    sys.exit(run_import())
