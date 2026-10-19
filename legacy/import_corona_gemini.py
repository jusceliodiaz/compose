"""Importa os passes EXR renderizados pelo Corona no 3ds Max para o projeto web do ZYcompose.

Uso:
  python tools/import_corona.py <pasta_renders> <projeto> <camera>

Exemplo:
  python tools/import_corona.py renders/cam1 cozinha_ilha cam1
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

# Importa o módulo exr_io local
import exr_io


def find_file(folder: Path, pattern: str) -> Path | None:
    matches = list(folder.glob(pattern))
    return matches[0] if matches else None


def tonemap_srgb(linear: np.ndarray) -> np.ndarray:
    """Converte imagem linear HDR para 8-bit sRGB simples para preview (beauty.webp)."""
    # Clamp e curva de gama sRGB padrão
    c = np.clip(linear, 0.0, 1.0)
    srgb = np.where(c <= 0.0031308, 12.92 * c, 1.055 * np.power(c, 1.0 / 2.4) - 0.055)
    return np.round(srgb * 255.0).astype(np.uint8)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("render_dir", type=Path, help="Pasta contendo os EXRs do Corona")
    ap.add_argument("project_id", type=str, help="ID do projeto (ex: cozinha_ilha)")
    ap.add_argument("camera", type=str, help="Nome da câmera (ex: cam1)")
    args = ap.parse_args(argv)

    render_dir = args.render_dir.resolve()
    if not render_dir.is_dir():
        print(f"Erro: pasta não encontrada: {render_dir}", file=sys.stderr)
        return 1

    tools_dir = Path(__file__).resolve().parent
    repo_root = tools_dir.parent
    web_dir = repo_root / "web"
    dest_dir = web_dir / "public" / "assets" / "scenes" / args.project_id / args.camera
    catalog_dir = web_dir / "public" / "assets" / "catalog"
    dest_dir.mkdir(parents=True, exist_ok=True)
    catalog_dir.mkdir(parents=True, exist_ok=True)

    print(f"--- IMPORT CORONA: {args.project_id} / {args.camera} ---")
    print(f"Lendo de: {render_dir}")
    print(f"Destino web: {dest_dir}")

    # 1. Localiza os passes
    beauty_exr = find_file(render_dir, "*beauty*.exr")
    diff_light_exr = find_file(render_dir, "*diff_light*.exr")
    diff_color_exr = find_file(render_dir, "*diff_color*.exr")
    reflect_exr = find_file(render_dir, "*reflect*.exr")
    refract_exr = find_file(render_dir, "*refract*.exr")
    transl_exr = find_file(render_dir, "*transl*.exr")
    emission_exr = find_file(render_dir, "*emission*.exr")
    uv_exr = find_file(render_dir, "*uv*.exr")
    masks_exr = find_file(render_dir, "*masks_a*.exr")
    lg_sol_exr = find_file(render_dir, "*lg_sol*.exr")
    lg_int_exr = find_file(render_dir, "*lg_interno*.exr")

    if not beauty_exr:
        print("Erro: beauty.exr não encontrado na pasta de renders!", file=sys.stderr)
        return 1
    if not uv_exr:
        print("Erro: uv.exr não encontrado na pasta de renders!", file=sys.stderr)
        return 1

    print(f"Encontrado beauty: {beauty_exr.name}")
    print(f"Encontrado uv: {uv_exr.name}")

    # 2. Converte a máscara para PNG RGB 8-bit
    mask_png_path = dest_dir / "masks_a.png"
    if masks_exr and masks_exr.is_file():
        print(f"Processando máscara: {masks_exr.name} -> {mask_png_path.name}")
        mask_data = exr_io.read_exr(masks_exr)
        mask_u8 = np.clip(mask_data[..., :3] * 255.0, 0, 255).astype(np.uint8)
        exr_io.write_png(mask_png_path, mask_u8)
    else:
        print("Aviso: masks_a.exr não encontrado, pulando máscara.")

    # 3. Roda o pack_uv.py
    print("Empacotando UV Pass com u16_hilo...")
    uv_prefix = str(dest_dir / "uv")
    cmd_uv = [sys.executable, str(tools_dir / "pack_uv.py"), str(uv_exr), uv_prefix]
    if mask_png_path.is_file():
        cmd_uv.extend(["--mask", str(mask_png_path), "--mask-channel", "r"])
    subprocess.run(cmd_uv, check=True)

    # 4. Gera beauty.webp para exibição inicial
    print("Gerando preview beauty.webp...")
    beauty_data = exr_io.read_exr(beauty_exr)
    beauty_srgb = tonemap_srgb(beauty_data)
    exr_io.write_webp(dest_dir / "beauty.webp", beauty_srgb, quality=92)

    # 5. Copia os passes HDR necessários para a pasta web
    print("Copiando passes de iluminação e luz...")
    passes_to_copy = [
        (beauty_exr, "beauty.exr"),
        (diff_light_exr, "diff_light.exr"),
        (diff_color_exr, "diff_color.exr"),
        (reflect_exr, "glossy.exr"),  # Na web o canal de reflexo é chamado de glossy
        (lg_sol_exr, "lg_sol.exr"),
        (lg_int_exr, "lg_interno.exr"),
    ]
    for src_file, dest_name in passes_to_copy:
        if src_file and src_file.is_file():
            shutil.copy2(src_file, dest_dir / dest_name)
            print(f"  Copiado: {dest_name}")

    # 6. Reconstruct check (Verificação da reconstrução matemática)
    print("\nExecutando teste de reconstrução matemática (Reconstruct Check)...")
    recon_cmd = [
        sys.executable, str(tools_dir / "reconstruct_check.py"), str(beauty_exr),
        "--mul", str(diff_color_exr), str(diff_light_exr)
    ]
    if reflect_exr and reflect_exr.is_file():
        recon_cmd.extend(["--add", str(reflect_exr)])
    if refract_exr and refract_exr.is_file():
        recon_cmd.extend(["--add", str(refract_exr)])
    if transl_exr and transl_exr.is_file():
        recon_cmd.extend(["--add", str(transl_exr)])
    if emission_exr and emission_exr.is_file():
        recon_cmd.extend(["--add", str(emission_exr)])

    try:
        subprocess.run(recon_cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Aviso no teste de reconstrução: {e}")

    # 7. Criação / Atualização do catálogo JSON
    catalog_path = catalog_dir / f"{args.project_id}.json"
    uv_meta_path = dest_dir / "uv_meta.json"
    uv_range = [0.0, 0.0, 8.41, 6.14]
    if uv_meta_path.is_file():
        with open(uv_meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
            uv_range = meta.get("uv_range", uv_range)

    catalog_data = {
        "schema_version": 2,
        "project_id": args.project_id,
        "title": "Cozinha Ilha - Corona Renderer",
        "default_camera": args.camera,
        "cameras": {
            args.camera: {
                "name": "Câmera Principal",
                "aspect_ratio": [4, 3],
                "resolution": [beauty_data.shape[1], beauty_data.shape[0]],
                "passes": {
                    "beauty_preview": f"assets/scenes/{args.project_id}/{args.camera}/beauty.webp",
                    "beauty_linear": f"assets/scenes/{args.project_id}/{args.camera}/beauty.exr",
                    "diffuse_light": f"assets/scenes/{args.project_id}/{args.camera}/diff_light.exr",
                    "glossy": f"assets/scenes/{args.project_id}/{args.camera}/glossy.exr",
                    "uv_hi": f"assets/scenes/{args.project_id}/{args.camera}/uv_hi.png",
                    "uv_lo": f"assets/scenes/{args.project_id}/{args.camera}/uv_lo.png",
                    "uv_encoding": "u16_hilo",
                    "uv_range": uv_range,
                    "masks": {
                        "masks_a": f"assets/scenes/{args.project_id}/{args.camera}/masks_a.png"
                    }
                },
                "slots": {
                    "piso": {
                        "name": "Piso Principal",
                        "mask": "masks_a",
                        "channel": "r",
                        "default_material": "wood_oak"
                    },
                    "bancada": {
                        "name": "Bancada de Mármore",
                        "mask": "masks_a",
                        "channel": "g",
                        "default_material": "marble_carrara"
                    },
                    "parede": {
                        "name": "Parede do Fundo",
                        "mask": "masks_a",
                        "channel": "b",
                        "default_material": "plaster_taupe"
                    }
                },
                "light_groups": {
                    "lg_sol": {
                        "name": "Sol & Céu",
                        "file": f"assets/scenes/{args.project_id}/{args.camera}/lg_sol.exr",
                        "default_intensity": 1.0
                    },
                    "lg_interno": {
                        "name": "Iluminação Interna",
                        "file": f"assets/scenes/{args.project_id}/{args.camera}/lg_interno.exr",
                        "default_intensity": 1.0
                    }
                }
            }
        }
    }

    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump(catalog_data, f, indent=2, ensure_ascii=False)

    print(f"\nCatálogo JSON gravado em: {catalog_path}")
    print("Importação concluída com sucesso!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
