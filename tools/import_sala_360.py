"""Importa os passes 360 panorâmicos renderizados da pasta 'renders/sala_360'.
Empacota UVs em u16_hilo, máscaras em masks_0.png e masks_1.png, gera thumbnails e atualiza o catálogo.
"""

from __future__ import annotations
import os
os.environ["OPENCV_IO_ENABLE_OPENEXR"] = "1"
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import cv2
import exr_io
import pack_uv
import validate_catalog
from catalog_index import update_index


def matte_edges(img: np.ndarray, raw: np.ndarray, core: int = 2, win: int = 9,
                min_contrast: float = 0.004, gain: float = 2.0,
                spill_px: int = 0, spill_gain: float = 2.5) -> np.ndarray:
    """Refina a borda da máscara pela cor do próprio beauty (matting local).

    Para cada pixel da faixa de transição estima F (cor do objeto, por dentro) e
    B (cor do fundo, por fora) e calcula alpha = proj(I - B, F - B). Depois reforça
    a transição (gain) para que a cor original não vaze no material novo.
    Onde F e B são parecidos demais, mantém a máscara crua do Corona.
    """
    hard = (raw > 0.5).astype(np.uint8)
    k = np.ones((3, 3), np.uint8)
    inside = cv2.erode(hard, k, iterations=core).astype(np.float32)
    outside = cv2.erode(1 - hard, k, iterations=core).astype(np.float32)
    band = (inside == 0) & (outside == 0)
    if not band.any():
        return raw

    ys, xs = np.nonzero(band)
    pad = max(win, 6 * spill_px)
    y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad + 1, raw.shape[0])
    x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad + 1, raw.shape[1])
    I = img[y0:y1, x0:x1]
    fin, fout, b = inside[y0:y1, x0:x1], outside[y0:y1, x0:x1], band[y0:y1, x0:x1]

    box = lambda a: cv2.boxFilter(a, -1, (win, win), normalize=False)
    w_f, w_b = box(fin), box(fout)
    F = box(I * fin[..., None]) / np.maximum(w_f, 1e-6)[..., None]
    B = box(I * fout[..., None]) / np.maximum(w_b, 1e-6)[..., None]
    d = F - B
    dd = np.sum(d * d, axis=-1)
    alpha = np.clip(np.sum((I - B) * d, axis=-1) / np.maximum(dd, 1e-8), 0.0, 1.0)
    alpha = np.clip(alpha * gain, 0.0, 1.0)

    ok = b & (w_f > 0.5) & (w_b > 0.5) & (dd > min_contrast)
    out = raw.copy()
    sub = out[y0:y1, x0:x1]
    sub[ok] = alpha[ok]

    # Respingo de cor ("spill"): reflexo/GI da cor original nas bordas dos objetos
    # vizinhos (ex.: aro laranja nas coifas). Mede, só pela cromaticidade, quanto o
    # pixel puxa da cor do objeto (F) em relação ao fundo distante (B) e estende a
    # máscara parcialmente sobre ele, para o material novo substituir esse tom.
    if spill_px > 0:
        near = cv2.dilate(hard[y0:y1, x0:x1], k, iterations=spill_px).astype(bool) & (hard[y0:y1, x0:x1] == 0)
        far = (cv2.erode(1 - hard[y0:y1, x0:x1], k, iterations=spill_px) > 0).astype(np.float32)
        sw = 4 * spill_px + 1
        boxs = lambda a: cv2.boxFilter(a, -1, (sw, sw), normalize=False)
        w_far, w_in = boxs(far), boxs(fin)
        chroma = I / np.maximum(I.sum(axis=-1, keepdims=True), 1e-4)
        Fc = boxs(chroma * fin[..., None]) / np.maximum(w_in, 1e-6)[..., None]
        Bc = boxs(chroma * far[..., None]) / np.maximum(w_far, 1e-6)[..., None]
        Bc[w_far < 0.5] = 1.0 / 3.0  # objeto fino (ex.: haste) sem fundo à vista → assume neutro
        dc = Fc - Bc
        ddc = np.sum(dc * dc, axis=-1)
        s = np.clip(np.sum((chroma - Bc) * dc, axis=-1) / np.maximum(ddc, 1e-8), 0.0, 1.0)
        okc = near & (w_in > 0.5) & (ddc > 1e-3)
        sub[okc] = np.maximum(sub[okc], np.clip(s[okc] * spill_gain, 0.0, 1.0))
    return out


def to_single_channel(arr: np.ndarray) -> np.ndarray:
    if arr.ndim == 2:
        return arr
    return np.clip(np.max(arr[..., :3], axis=-1), 0.0, 1.0)


def run_import():
    render_dir = ROOT / "renders" / "sala_360"
    public_dir = ROOT / "web" / "public"
    rel_cam = "assets/scenes/sala_estar/cam360"
    dest_dir = public_dir / rel_cam
    dest_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== IMPORTANDO SALA DE ESTAR 360 (PASTA: {render_dir}) ===")
    print(f"Destino Web: {dest_dir}")

    beauty_path = render_dir / "cam360_beauty.exr"
    uv_path = render_dir / "cam360_uv.exr"
    diff_light_path = render_dir / "cam360_diff_light.exr"
    reflect_path = render_dir / "cam360_reflect.exr"

    if not beauty_path.is_file():
        print(f"ERRO: beauty não encontrado: {beauty_path}")
        return 1

    beauty = exr_io.read_exr(beauty_path)[..., :3]
    h, w = beauty.shape[:2]
    print(f"Resolução da cena 360: {w}x{h} (Aspecto {w/h:.2f}:1)")

    # 1. Carrega as 5 máscaras
    mask_files = {
        "sofa": render_dir / "cam360_masks_a.exr",
        "piso": render_dir / "cam360_masks_b.exr",
        "tapete": render_dir / "cam360_masks_c.exr",
        "parede": render_dir / "cam360_masks_d.exr",
        "armario": render_dir / "cam360_masks_e.exr",
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

    # 2. Borda das máscaras ajustada à cor do beauty (o filtro guiado em cinza
    #    erodia a máscara onde objeto e fundo têm brilho parecido) e empacotamento
    guide = exr_io.linear_to_srgb(np.clip(beauty, 0.0, 1.0)).astype(np.float32)
    for name in raw_masks:
        if raw_masks[name].max() > 0.01:
            # spill só onde a cor original é forte e reflete nos vizinhos (armário laranja)
            raw_masks[name] = matte_edges(guide, raw_masks[name], spill_px=8 if name == "armario" else 0)

    # masks_0: R=piso, G=tapete, B=sofa
    # masks_1: R=parede, G=armario, B=zeros
    mask_0_rgb = np.zeros((h, w, 3), dtype=np.uint8)
    mask_0_rgb[..., 0] = (np.clip(raw_masks["piso"], 0, 1) * 255).astype(np.uint8)
    mask_0_rgb[..., 1] = (np.clip(raw_masks["tapete"], 0, 1) * 255).astype(np.uint8)
    mask_0_rgb[..., 2] = (np.clip(raw_masks["sofa"], 0, 1) * 255).astype(np.uint8)

    mask_1_rgb = np.zeros((h, w, 3), dtype=np.uint8)
    mask_1_rgb[..., 0] = (np.clip(raw_masks["parede"], 0, 1) * 255).astype(np.uint8)
    mask_1_rgb[..., 1] = (np.clip(raw_masks["armario"], 0, 1) * 255).astype(np.uint8)

    exr_io.write_png(dest_dir / "masks_0.png", mask_0_rgb)
    exr_io.write_png(dest_dir / "masks_1.png", mask_1_rgb)
    print("  + Máscaras empacotadas em masks_0.png e masks_1.png salvas com sucesso!")

    # 3. UV -> u16_hilo
    if uv_path.is_file():
        uv = exr_io.read_exr(uv_path)
        valid = (raw_masks["piso"] > 0.5) | (raw_masks["sofa"] > 0.5) | (raw_masks["tapete"] > 0.5) | (raw_masks["parede"] > 0.5) | (raw_masks["armario"] > 0.5)
        hi, lo, uv_range = pack_uv.pack_uv(uv, valid)
        exr_io.write_png(dest_dir / "uv_hi.png", hi)
        exr_io.write_png(dest_dir / "uv_lo.png", lo)
        (dest_dir / "uv_meta.json").write_text(json.dumps({"uv_encoding": "u16_hilo", "uv_range": uv_range}, indent=2), encoding="utf-8")
        print(f"  + UV 360 empacotado: uv_range = {uv_range}")
    else:
        print("ERRO: cam360_uv.exr não encontrado!")
        return 1

    # 4. Passes de luz
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
        lg_p = render_dir / f"cam360_lg_{g}.exr"
        if lg_p.is_file():
            exr_io.write_exr(dest_dir / f"lg_{g}.exr", exr_io.read_exr(lg_p)[..., :3].astype(np.float32))
            print(f"  + LightGroup lg_{g}.exr exportado")

    # 5. Thumbnails originais
    for sid, m_arr in raw_masks.items():
        ys, xs = np.nonzero(m_arr > 0.5)
        if ys.size > 0:
            cy, cx = int(np.median(ys)), int(np.median(xs))
            side = int(min(max(np.percentile(ys, 90) - np.percentile(ys, 10), np.percentile(xs, 90) - np.percentile(xs, 10), 64), min(h, w)))
            y0 = int(np.clip(cy - side // 2, 0, h - side))
            x0 = int(np.clip(cx - side // 2, 0, w - side))
            crop = ldr[y0:y0+side, x0:x0+side]
            exr_io.write_webp(dest_dir / f"thumb_original_{sid}.webp", exr_io.resize_area(crop, (256, 256)), 88)

    # 6. Carrega catálogo base sala_estar.json para clonar materiais e slots
    base_cat_path = public_dir / "assets" / "catalog" / "sala_estar.json"
    base_cat = json.loads(base_cat_path.read_text(encoding="utf-8"))

    # Monta catálogo 360
    cat_360 = json.loads(json.dumps(base_cat))
    cat_360["project_id"] = "sala_estar_360"
    cat_360["project_name"] = "Living room - Panorama 360°"
    cat_360["camera"] = "cam360"
    cat_360["camera_name"] = "Panorama 360°"
    cat_360["resolution"] = {"view": [w, h], "export": [w, h]}
    cat_360["is_360"] = True
    
    # Atualiza base_passes para apontar para cam360
    cat_360["base_passes"]["beauty"] = f"{rel_cam}/beauty.webp"
    cat_360["base_passes"]["beauty_linear"] = f"{rel_cam}/beauty.exr"
    cat_360["base_passes"]["uv_hi"] = f"{rel_cam}/uv_hi.png"
    cat_360["base_passes"]["uv_lo"] = f"{rel_cam}/uv_lo.png"
    cat_360["base_passes"]["uv_range"] = uv_range
    cat_360["base_passes"]["diffuse_light"] = f"{rel_cam}/diff_light.exr"
    if (dest_dir / "glossy.exr").is_file():
        cat_360["base_passes"]["glossy"] = f"{rel_cam}/glossy.exr"
    
    cat_360["base_passes"]["masks_packed"] = [
        {"file": f"{rel_cam}/masks_0.png", "channels": {"r": "piso", "g": "tapete", "b": "sofa"}},
        {"file": f"{rel_cam}/masks_1.png", "channels": {"r": "parede", "g": "armario"}}
    ]

    # Atualiza thumbnails originais nos slots
    for slot in cat_360.get("configurable_slots", []):
        sid = slot["id"]
        for opt in slot.get("options", []):
            if opt.get("id") == "original":
                opt["thumbnail"] = f"{rel_cam}/thumb_original_{sid}.webp"

    cat_360_path = public_dir / "assets" / "catalog" / "sala_estar_360.json"
    cat_360_path.write_text(json.dumps(cat_360, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Catálogo 360 salvo em: {cat_360_path}")

    # Atualiza index.json para incluir sala_estar_360
    idx_path = public_dir / "assets" / "catalog" / "index.json"
    if idx_path.is_file():
        idx = json.loads(idx_path.read_text(encoding="utf-8"))
        projs = idx.get("projects", [])
        if not any(p["id"] == "sala_estar_360" for p in projs):
            projs.append({
                "id": "sala_estar_360",
                "name": "Living room - Panorama 360°",
                "catalog": "assets/catalog/sala_estar_360.json"
            })
            idx["projects"] = projs
            idx_path.write_text(json.dumps(idx, indent=2, ensure_ascii=False), encoding="utf-8")
            print("  + Projeto sala_estar_360 adicionado ao index.json")

    print("\n>>> IMPORTAÇÃO 360 CONCLUÍDA COM SUCESSO! <<<")
    return 0


if __name__ == "__main__":
    sys.exit(run_import())
