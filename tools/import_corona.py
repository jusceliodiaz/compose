"""Importa os EXRs do Corona (3ds Max) para a estrutura web e gera o catálogo — Marco 3.

Uso:
  python tools/import_corona.py <pasta_renders> <projeto> <camera> [opções]

Exemplo (cozinha, ver docs/CHECKLIST_3dsMax_Corona.md):
  python tools/import_corona.py renders/cam1 cozinha_ilha cam1 --project-name "Cozinha com ilha" ^
      --area piso=51.6 --area bancada=5.3 --area parede=110

Arquivos esperados na pasta (nome = PREFIXO + nome do Render Element + .exr; prefixo padrão "<camera>_"):
  obrigatórios: beauty, diff_light, uv, masks_a
  opcionais:    diff_color, reflect (→ glossy), refract, transl, emission, sss, volum, lg_<grupo>, masks_b

Passos: encontra os EXRs → confere resoluções → máscara PNG → pack_uv → beauty.webp (mesmo tone map
do shader) → reconstrução (beauty ≈ diff_color×diff_light + componentes) → copia (EXR half) →
catálogo v2 + índice de projetos → validate_catalog.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import numpy as np

import exr_io
import pack_uv
import reconstruct_check
import tone_curve
import validate_catalog
from catalog_index import update_index

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ["beauty", "diff_light", "uv", "masks_a"]
MASK_NAMES = ("masks_a", "masks_b", "masks_c", "masks_d", "masks_e", "masks_f")
OPTIONAL = ["diff_color", "reflect", "refract", "transl", "emission", "sss", "volum", *MASK_NAMES[1:]]
KINDS = ("floor", "stone", "paint", "fabric", "rug", "cabinet")
MAX_SLOTS = 5   # limite do motor web: 16 texturas no shader (ver composite.frag.glsl)
GLOSS_KEEP = {"floor": 0.6, "stone": 0.8, "paint": 0.15, "fabric": 0.1, "rug": 0.05, "cabinet": 0.5}
EXTRA_COMPONENTS = ["refract", "transl", "emission", "sss", "volum"]


@dataclass
class SlotSpec:
    mask: str      # masks_a | masks_b
    channel: str   # r | g | b
    id: str
    name: str
    kind: str      # floor | stone | paint


DEFAULT_SLOTS = [
    SlotSpec("masks_a", "r", "piso", "Piso", "floor"),
    SlotSpec("masks_a", "g", "bancada", "Mármore", "stone"),
    SlotSpec("masks_a", "b", "parede", "Paredes", "paint"),
]


def parse_slot(s: str) -> SlotSpec:
    """Formato: [masks_x.]canal:id:Nome:tipo  (ex.: r:piso:Piso:floor, masks_b.g:assento:Assento:fabric)

    Tipos: floor (piso), stone (pedra), paint (tinta), fabric (tecido), rug (tapete), cabinet (marcenaria)."""
    parts = s.split(":")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(f"--slot espera canal:id:Nome:tipo, recebi '{s}'")
    ch, sid, name, kind = parts
    mask = "masks_a"
    if "." in ch:
        mask, ch = ch.split(".", 1)
    if ch not in ("r", "g", "b") or kind not in KINDS or mask not in MASK_NAMES:
        raise argparse.ArgumentTypeError(
            f"--slot inválido: '{s}' (máscara masks_a…masks_f; canal r/g/b; tipo {'/'.join(KINDS)})")
    return SlotSpec(mask, ch, sid, name, kind)


# --- Biblioteca de materiais por tipo de slot ----------------------------------------------

def _hex_to_linear(h: str) -> list[float]:
    rgb = np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)]) / 255.0
    return [round(float(x), 4) for x in exr_io.srgb_to_linear(rgb)]


PAINTS = [
    ("branco_gelo", "Branco gelo", "#EEEDE8"),
    ("areia", "Areia", "#D9CBB3"),
    ("salvia", "Verde sálvia", "#A2AD97"),
    ("terracota", "Terracota", "#B5704F"),
    ("petroleo", "Azul petróleo", "#2F5662"),
    ("grafite", "Grafite", "#4B4A48"),
]


LACQUERS = [
    ("laca_branca", "Laca branca", "#F1F0EC"),
    ("off_white", "Off-white", "#E4DDD0"),
    ("verde_oliva", "Verde oliva", "#6F7350"),
    ("azul_petroleo", "Azul petróleo", "#2E4F58"),
    ("grafite", "Grafite", "#3D3C3A"),
]


def library(kind: str) -> list[dict]:
    m = "assets/materials"

    def tex(mid, name, size, price, **kw):
        ext = "png" if mid == "checker" else "webp"
        o = {"id": mid, "name": name, "thumbnail": f"{m}/{mid}/thumb.webp", "diffuse_map": f"{m}/{mid}/albedo.{ext}",
             "texture_size_m": list(size), "default_tiling": [1.0, 1.0]}
        if price is not None:
            o["price"] = {"value": price, "unit": "m2", "currency": "BRL"}
        o.update(kw)
        return o

    oak = tex("oak", "Carvalho em régua", (2.4, 1.2), 189.9, sku="PISO-CARV-001", finish="Madeira · réguas 1,20 × 0,20 m",
              tint_variants=[{"id": "natural", "name": "Natural", "tint": [1, 1, 1]},
                             {"id": "mel", "name": "Mel", "tint": [1.05, 0.88, 0.70]},
                             {"id": "fume", "name": "Fumê", "tint": [0.55, 0.52, 0.50]}])
    marble = tex("marble", "Mármore Carrara", (1.2, 1.2), 890.0, sku="PEDRA-CARR-120", finish="Pedra natural · placa 1,20 × 1,20 m",
                 gloss_keep=0.85,
                 tint_variants=[{"id": "branco", "name": "Branco", "tint": [1, 1, 1]},
                                {"id": "bege", "name": "Bege", "tint": [1.0, 0.9, 0.76]}])
    concrete = tex("concrete", "Cimento queimado", (1.0, 1.0), 120.0, sku="CIM-QUEI-100", finish="Revestimento contínuo",
                   tint_variants=[{"id": "cinza", "name": "Cinza", "tint": [1, 1, 1]},
                                  {"id": "areia", "name": "Areia", "tint": [1.25, 1.12, 0.92]}])
    checker = tex("checker", "Grade de teste", (1.0, 1.0), None, is_test=True, finish="1 tile = 1 m · célula = 10 cm")

    def tones(*items):
        return [{"id": i, "name": n, "tint": t} for i, n, t in items]

    linen = tex("linen", "Linho", (0.5, 0.5), 149.9, sku="TEC-LINHO-01", finish="Tecido · trama tela",
                tint_variants=tones(("areia", "Areia", [1.0, 0.88, 0.70]), ("cinza", "Cinza", [0.72, 0.72, 0.72]),
                                    ("oliva", "Oliva", [0.58, 0.60, 0.40]), ("terracota", "Terracota", [0.95, 0.52, 0.36]),
                                    ("grafite", "Grafite", [0.30, 0.30, 0.31])))
    rug = tex("rug", "Lã em laçadas", (1.0, 1.0), 220.0, sku="TAP-LA-01", finish="Tapete · lã natural",
              tint_variants=tones(("cru", "Cru", [1.0, 0.94, 0.84]), ("cinza", "Cinza", [0.70, 0.70, 0.70]),
                                  ("caramelo", "Caramelo", [0.92, 0.68, 0.44]), ("musgo", "Musgo", [0.55, 0.58, 0.42])))

    def solids(items, finish, gloss, price, sku):
        return [{"id": pid, "name": name, "albedo_color": _hex_to_linear(hx), "finish": f"{finish} · {hx}",
                 "gloss_keep": gloss, "price": {"value": price, "unit": "m2", "currency": "BRL"},
                 "sku": f"{sku}-{pid.upper()}"} for pid, name, hx in items]

    if kind == "floor":
        return [oak, marble, concrete, checker]
    if kind == "stone":
        return [marble, concrete, checker]
    if kind == "fabric":
        return [linen, checker]
    if kind == "rug":
        return [rug, linen, checker]
    if kind == "cabinet":
        return [oak, *solids(LACQUERS, "Laca semibrilho", 0.5, 420.0, "LACA"), checker]
    return [*solids(PAINTS, "Tinta acrílica fosca", 0.15, 38.0, "TINTA"), checker]


# --- Utilitários ----------------------------------------------------------------------

def find_passes(folder: Path, prefix: str) -> tuple[dict[str, Path], dict[str, Path]]:
    """Devolve (passes, light_groups). Procura PREFIXO+nome.exr; senão, um único *nome*.exr."""
    files = sorted(folder.glob("*.exr"))
    found: dict[str, Path] = {}
    for name in REQUIRED + OPTIONAL:
        exact = folder / f"{prefix}{name}.exr"
        if exact.is_file():
            found[name] = exact
            continue
        pat = re.compile(rf"(^|[_.\-]){re.escape(name)}([_.\-]|$)", re.I)
        cands = [f for f in files if pat.search(f.stem)]
        if len(cands) == 1:
            found[name] = cands[0]
        elif len(cands) > 1:
            raise ValueError(f"vários arquivos para '{name}': {[c.name for c in cands]} — use --prefix")
    if "beauty" not in found:
        # saída principal do 3ds Max sem nome de elemento: "cam7_.exr" quando o prefixo é "cam7__"
        base = prefix.rstrip("_.-")
        for cand in (base, base + "_", base + "."):
            f = folder / f"{cand}.exr"
            if f.is_file():
                found["beauty"] = f
                break
    lgs: dict[str, Path] = {}
    for f in files:
        m = re.search(r"(?:^|[_.\-])lg_([a-z0-9]+)$", f.stem, re.I)
        if m:
            g = m.group(1).lower()
            # prefere PREFIXO+lg_x.exr a cópias como cam1_output_lg_x.exr
            if g not in lgs or f.stem.lower() == f"{prefix}lg_{g}".lower():
                lgs[g] = f
    return found, lgs


def auto_exposure(beauty: np.ndarray, key: float = 0.18) -> float:
    """Exposição pela média logarítmica da luminância (chave 0.18, Reinhard)."""
    lum = exr_io.luminance(beauty)
    lum = lum[np.isfinite(lum) & (lum > 1e-6)]
    if lum.size == 0:
        return 1.0
    return float(key / np.exp(np.mean(np.log(lum))))


def visible_area_m2(uv: np.ndarray, mask: np.ndarray) -> float:
    """Área visível estimada: Σ |det J| dos pixels do slot, com J = ∂(u,v)/∂(x,y) (UV em metros)."""
    u, v = uv[..., 0].astype(np.float64), uv[..., 1].astype(np.float64)
    uy, ux = np.gradient(u)
    vy, vx = np.gradient(v)
    det = np.abs(ux * vy - uy * vx)
    sel = mask > 0.5
    # bordas e costuras dão saltos enormes: descarta o que passa de 20× a mediana
    vals = det[sel]
    if vals.size == 0:
        return 0.0
    med = np.median(vals)
    vals = np.where(vals > med * 20, med, vals)
    return float(vals.sum())


def original_thumb(beauty_ldr: np.ndarray, mask: np.ndarray, out: Path) -> None:
    """Miniatura "Original": recorte quadrado do render em volta do slot."""
    ys, xs = np.nonzero(mask > 0.5)
    h, w = mask.shape
    if ys.size == 0:
        cy, cx, side = h // 2, w // 2, min(h, w) // 2
    else:
        cy, cx = int(np.median(ys)), int(np.median(xs))
        side = int(max(np.percentile(ys, 90) - np.percentile(ys, 10), np.percentile(xs, 90) - np.percentile(xs, 10), 64))
        side = min(side, h, w)
    y0 = int(np.clip(cy - side // 2, 0, h - side))
    x0 = int(np.clip(cx - side // 2, 0, w - side))
    exr_io.write_webp(out, exr_io.resize_area(beauty_ldr[y0:y0 + side, x0:x0 + side], (256, 256)), 88)


ALIGN_FAIL = 0.60
ALIGN_WARN = 0.75


def mask_alignment(mask: np.ndarray, uv: np.ndarray) -> tuple[float, int]:
    """Fração da borda do slot que coincide com uma borda da geometria (salto no UV).

    Numa máscara do próprio render a borda do objeto É uma borda de UV (0,78–0,98 nas cenas testadas);
    uma máscara feita de outra câmera/resolução ou desenhada à mão fica bem abaixo (≈ 0,05–0,5).
    """
    import cv2

    m = (mask > 0.5).astype(np.uint8)
    edge_m = cv2.morphologyEx(m, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
    edge_m[:3] = edge_m[-3:] = False
    edge_m[:, :3] = edge_m[:, -3:] = False
    g = np.zeros(m.shape, np.float32)
    for c in (uv[..., 0].astype(np.float32), uv[..., 1].astype(np.float32)):
        gx = np.abs(np.diff(c, axis=1, append=c[:, -1:]))
        gy = np.abs(np.diff(c, axis=0, append=c[-1:, :]))
        g = np.maximum(g, np.maximum(gx, gy))
    # borda de verdade = SALTO: gradiente muito maior que o dos vizinhos (piso visto de raspão tem
    # gradiente alto, mas suave, e não conta)
    jump = g > 4 * cv2.medianBlur(g, 5) + 1e-4
    edge_uv = cv2.dilate(jump.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    n = int(edge_m.sum())
    return (float((edge_m & edge_uv).sum()) / n if n else 1.0), n


def uv_clamped(uv: np.ndarray, valid: np.ndarray) -> bool:
    """UV salvo com clamp em [0, 1]: muitos pixels exatamente em 1,0 e nada acima."""
    u, v = uv[..., 0][valid], uv[..., 1][valid]
    if u.size == 0 or max(float(u.max()), float(v.max())) > 1.0 + 1e-6:
        return False
    return float(((u >= 1.0 - 1e-6) | (v >= 1.0 - 1e-6)).mean()) > 0.02


def rgb(img: np.ndarray) -> np.ndarray:
    if img.shape[2] >= 3:
        return img[..., :3]
    return np.repeat(img[..., :1], 3, axis=-1)


# --- Import ---------------------------------------------------------------------------

def run(args: argparse.Namespace) -> int:
    src = args.render_dir.resolve()
    if not src.is_dir():
        print(f"ERRO: pasta não encontrada: {src}", file=sys.stderr)
        return 1
    prefix = args.prefix if args.prefix is not None else f"{args.camera}_"
    passes, lg_files = find_passes(src, prefix)
    required = [n for n in REQUIRED if not (n == "masks_a" and args.masks_png)]
    missing = [n for n in required if n not in passes]
    if missing:
        print(f"ERRO: faltam passes obrigatórios em {src}: {missing}\n"
              f"      encontrados: {sorted(p.name for p in src.glob('*.exr')) or 'nenhum .exr'}", file=sys.stderr)
        return 1

    public = args.web_root
    rel_cam = f"assets/scenes/{args.project_id}/{args.camera}"
    dest = public / rel_cam
    dest.mkdir(parents=True, exist_ok=True)
    print(f"── import Corona: {src} → {dest}")
    for n, p in sorted(passes.items()):
        print(f"   {n:<11} {p.name}")
    for g, p in sorted(lg_files.items()):
        print(f"   lg_{g:<8} {p.name}")

    # 1. leitura + resoluções
    img = {n: exr_io.read_exr(p) for n, p in passes.items()}
    if args.masks_png:
        print(f"   masks_a     {args.masks_png} (substitui o EXR do render)")
        img["masks_a"] = exr_io.read_png(args.masks_png)[..., :3].astype(np.float32) / 255.0
    lgi = {g: exr_io.read_exr(p) for g, p in lg_files.items()}
    for g in list(lgi):
        if float(np.abs(lgi[g][..., :3]).max()) < 1e-6:
            print(f"aviso: o grupo de luz lg_{g} está vazio (tudo preto) — ignorado. Confira as luzes do LightSelect.")
            del lgi[g]
    shapes = {n: a.shape[:2] for n, a in {**img, **{f"lg_{g}": a for g, a in lgi.items()}}.items()}
    if len(set(shapes.values())) != 1:
        print(f"ERRO: resoluções diferentes entre os passes: {shapes}", file=sys.stderr)
        return 1
    h, w = img["beauty"].shape[:2]

    # 2. máscaras do render (cada masks_x pode ter 1 a 3 objetos) → slots
    masks_f: dict[str, np.ndarray] = {m: np.clip(rgb(img[m]), 0.0, 1.0) for m in MASK_NAMES if m in img}

    slots = [s for s in args.slot if s.mask in masks_f
             and (masks_f[s.mask][..., "rgb".index(s.channel)] > 0.5).mean() >= 0.0005]
    for s in args.slot:
        if s.mask not in masks_f:
            print(f"aviso: slot {s.id} usa {s.mask}, que não foi renderizado — ignorado")
    slot_mask = {s.id: masks_f[s.mask][..., "rgb".index(s.channel)] for s in slots}
    for s in slots:
        cov = float((slot_mask[s.id] > 0.5).mean() * 100)
        print(f"   slot {s.id:<9} {s.mask}.{s.channel}  cobertura {cov:5.1f}% da imagem")
    for s in args.slot:
        if s not in slots and s.mask in masks_f:
            print(f"aviso: slot {s.id} ({s.mask}.{s.channel}) está vazio na máscara — ignorado")
    if not slots:
        print("ERRO: nenhum slot com máscara. O masks_a veio preto? (CMasking_Mask: confira o modo e os objetos)",
              file=sys.stderr)
        return 1
    if len(slots) > MAX_SLOTS:
        print(f"ERRO: {len(slots)} superfícies; o configurador aceita até {MAX_SLOTS} por câmera "
              f"({[s.id for s in slots]}). Escolha as principais com --slot.", file=sys.stderr)
        return 1
    # reempacota para a web: 3 slots por PNG (R, G, B), na ordem dos --slot
    packed: list[dict] = []
    slot_ref: dict[str, tuple[int, str]] = {}
    for i in range(0, len(slots), 3):
        group = slots[i:i + 3]
        rgb_mask = np.zeros((h, w, 3), np.float32)
        channels = {}
        for ch, s in zip("rgb", group):
            rgb_mask[..., "rgb".index(ch)] = slot_mask[s.id]
            channels[ch] = s.id
            slot_ref[s.id] = (len(packed), ch)
        name = f"masks_{len(packed)}.png"
        exr_io.write_png(dest / name, exr_io.to_u8(rgb_mask))
        packed.append({"file": f"{rel_cam}/{name}", "channels": channels})

    # 2b. a máscara precisa coincidir com a geometria desta câmera
    uv = img["uv"]
    bad = []
    for s in slots:
        score, n = mask_alignment(slot_mask[s.id], uv)
        tag = "ok" if score >= ALIGN_WARN else ("AVISO" if score >= ALIGN_FAIL else "DESALINHADA")
        print(f"   alinhamento máscara×geometria {s.id:<9} {score * 100:5.1f}% da borda  {tag}")
        if score < ALIGN_FAIL:
            bad.append(s.id)
    if bad and not args.ignore_alignment:
        print(f"ERRO: a máscara de {bad} não coincide com a geometria desta câmera (borda do slot não cai nas bordas\n"
              "      do UV). Ela foi feita de outra câmera/resolução ou desenhada à mão? Gere masks_* no próprio render\n"
              "      (CMasking_Mask no modo por objetos). Para importar mesmo assim: --ignorar-alinhamento", file=sys.stderr)
        return 1

    # 3. UV → hi/lo (validade = união das máscaras dos slots)
    valid = np.zeros((h, w), bool)
    for m in slot_mask.values():
        valid |= m > 0.5
    hi, lo, uv_range = pack_uv.pack_uv(uv, valid)
    exr_io.write_png(dest / "uv_hi.png", hi)
    exr_io.write_png(dest / "uv_lo.png", lo)
    (dest / "uv_meta.json").write_text(json.dumps({"uv_encoding": "u16_hilo", "uv_range": uv_range}, indent=2), encoding="utf-8")
    print(f"   uv_range = [{', '.join(f'{v:.3f}' for v in uv_range)}] m")
    if uv_clamped(uv, valid):
        print("aviso: o UV está CORTADO em 1,0 (muitos pixels exatamente em 1). O EXR foi salvo com clamp/tone mapping:\n"
              "       a escala das texturas e as áreas ficam erradas. Salve o elemento uv em EXR float, sem tone mapping.")
    if max(uv_range[2] - uv_range[0], uv_range[3] - uv_range[1]) <= 1.01:
        print("aviso: o UV cabe em 0–1 — não parece estar em metros (confira o UV_config no canal 2)")

    # 4. tone map + exposição → beauty.webp
    beauty = rgb(img["beauty"])
    # Passes com tone mapping ("display-referred"): beauty ≤ 1, ou quase (≤ 1,25, highlights de curva fílmica)
    # E os componentes não reconstroem o beauty — um render linear de verdade passa de 40 dB.
    bmax = float(np.percentile(exr_io.luminance(beauty), 99.9))
    display_referred = float(beauty.max()) <= 1.001
    if not display_referred and bmax <= 1.25 and "diff_color" in img:
        adds0 = [rgb(img[n]) for n in ["reflect", *EXTRA_COMPONENTS] if n in img]
        psnr0 = reconstruct_check.compare(
            beauty, reconstruct_check.reconstruct([[rgb(img["diff_color"]), rgb(img["diff_light"])]], adds0)).psnr
        display_referred = psnr0 < 25
    if display_referred:
        print("aviso: os passes parecem já ter tone mapping do Corona (beauty ≈ 0–1 e a reconstrução não fecha). O EXR")
        print("       deveria ser linear, sem tone mapping. Usando tone 'standard' e exposição 1 para não aplicar a curva")
        print("       duas vezes; use --light-from-beauty para reconstruir a curva.")
        args.tone = "standard"
        if args.exposure == "auto":
            args.exposure = "1"
    exposure = auto_exposure(beauty) if args.exposure == "auto" else float(args.exposure)
    ldr = exr_io.to_u8(exr_io.linear_to_srgb(exr_io.tonemap(beauty, args.tone, exposure)))
    exr_io.write_webp(dest / "beauty.webp", ldr, 92)
    print(f"   tone map {args.tone}, exposição {exposure:.4f}")

    # 5. passes de luz em EXR half RGB (sem alfa; arquivos menores)
    use_glossy = "reflect" in img and not args.light_from_beauty
    tone_json: dict = {"operator": args.tone, "exposure": round(exposure, 6)}
    lin = lambda a: a  # noqa: E731 — passes já lineares
    if args.light_from_beauty and "diff_color" not in img:
        print("ERRO: --light-from-beauty precisa do diff_color", file=sys.stderr)
        return 1
    if args.light_from_beauty and display_referred:
        # Reconstrói a curva do Corona e volta os passes para um espaço linear (ver tools/tone_curve.py)
        dc_all = rgb(img["diff_color"])
        curve = None
        if "diff_light" in img and float(np.percentile(exr_io.luminance(rgb(img["diff_light"])), 99.9)) <= 1.25:
            # o diff_light também veio com a curva: T⁻¹(beauty) = albedo · T⁻¹(diff_light), na imagem toda
            curve = tone_curve.fit_from_light(beauty, dc_all, rgb(img["diff_light"]),
                                              rgb(img["reflect"]) if "reflect" in img else None)
            if curve is not None:
                print(f"   curva de tone mapping reconstruída pelo diff_light: p0 = {curve.p0:.3f}, "
                      f"joelho {curve.tc:.3f}, n = {curve.n:.0f}, mínimo {curve.pmin:.2f} "
                      f"(erro mediano {curve.fit_error:.4f} em log2)")
        if curve is None:
            bins = []
            for m in slot_mask.values():
                bins += tone_curve.local_slopes(beauty, dc_all, m > 0.5)
            curve = tone_curve.fit_curve(bins)
            print(f"   curva de tone mapping reconstruída pelos detalhes do albedo: p0 = {curve.p0:.3f}, "
                  f"joelho em T ≈ {curve.tc:.3f} ({len(bins)} faixas{'' if bins else ' — SEM dados, curva genérica'})")
        lin = curve.inverse
        tone_json = {"operator": "lut", "exposure": 1.0, "lut": curve.lut()}
    beauty_lin = lin(beauty).astype(np.float32)
    exr_io.write_exr(dest / "beauty.exr", beauty_lin)
    if args.light_from_beauty:
        # Fallback dos docs (Seção 4.2): luz ≈ beauty / albedo original (o reflexo fica embutido na luz).
        light = beauty_lin / np.maximum(rgb(img["diff_color"]), 0.02)
        print("   diff_light = T⁻¹(beauty) / max(diff_color, 0.02)  (modo --light-from-beauty)")
        exr_io.write_exr(dest / "diff_light.exr", np.minimum(light, 60000.0))
    else:
        exr_io.write_exr(dest / "diff_light.exr", rgb(img["diff_light"]))
    if use_glossy:
        exr_io.write_exr(dest / "glossy.exr", rgb(img["reflect"]))
    for g, a in lgi.items():
        exr_io.write_exr(dest / f"lg_{g}.exr", np.minimum(lin(rgb(a)), 60000.0).astype(np.float32))

    # 6. reconstrução
    recon_ok = None
    if "diff_color" in img:
        adds = [rgb(img[n]) for n in ["reflect", *EXTRA_COMPONENTS] if n in img]
        rep = reconstruct_check.compare(beauty, reconstruct_check.reconstruct([[rgb(img["diff_color"]), rgb(img["diff_light"])]], adds))
        recon_ok = rep.psnr >= 40
        print(f"   reconstrução: {rep}  {'ok' if recon_ok else 'ABAIXO DE 40 dB'}")
        if not recon_ok:
            print("aviso: falta algum componente (emissão, refração, volume, SSS?) ou há pós-processamento no beauty")
    else:
        print("aviso: sem diff_color — reconstrução não verificada")
    if lgi:
        rep = reconstruct_check.compare(beauty, reconstruct_check.reconstruct([], [rgb(a) for a in lgi.values()]))
        print(f"   LightMix (Σ lg ≈ beauty): {rep}")

    # 7. miniaturas "Original" e áreas
    areas: dict[str, float] = dict(args.area)
    slots_json = []
    for s in slots:
        original_thumb(ldr, slot_mask[s.id], dest / f"thumb_original_{s.id}.webp")
        if s.id not in areas:
            areas[s.id] = round(visible_area_m2(uv, slot_mask[s.id]), 2)
            print(f"   área de {s.id}: {areas[s.id]} m² (estimada pela parte VISÍVEL; use --area {s.id}=… para o valor real)")
        original = {"id": "original", "name": "Original do render", "keep_original": True,
                    "thumbnail": f"{rel_cam}/thumb_original_{s.id}.webp", "finish": "Material do render, sem alteração"}
        slots_json.append({
            "id": s.id,
            "name": s.name,
            "mask_ref": {"file": slot_ref[s.id][0], "channel": slot_ref[s.id][1]},
            "default_texture": "original",
            "allow_user_transform": {"scale": [0.5, 2.0], "rotation": s.kind != "paint", "offset": s.kind != "paint"},
            "gloss_keep": GLOSS_KEEP[s.kind],
            "area_m2": areas[s.id],
            "options": [original, *library(s.kind)],
        })

    catalog = {
        "schema_version": 2,
        "project_id": args.project_id,
        "project_name": args.project_name or args.project_id,
        "camera": args.camera,
        "camera_name": args.camera_name or args.camera,
        "resolution": {"view": [w, h], "export": [w, h]},
        "tone_mapping": tone_json,
        "base_passes": {
            "beauty": f"{rel_cam}/beauty.webp",
            "beauty_linear": f"{rel_cam}/beauty.exr",
            "uv_hi": f"{rel_cam}/uv_hi.png",
            "uv_lo": f"{rel_cam}/uv_lo.png",
            "uv_encoding": "u16_hilo",
            "uv_range": uv_range,
            "diffuse_light": f"{rel_cam}/diff_light.exr",
            **({"glossy": f"{rel_cam}/glossy.exr"} if use_glossy else {}),
            "masks_packed": packed,
        },
        "light_groups": [
            {"id": g, "name": args.lg_name.get(g, g.replace("_", " ").capitalize()), "pass": f"{rel_cam}/lg_{g}.exr",
             "intensity": 1.0, "kelvin": args.lg_kelvin.get(g, 6500), "range": [0, 3]}
            for g in sorted(lgi)
        ][:4],
        "configurable_slots": slots_json,
    }
    cat_dir = public / "assets" / "catalog"
    cat_path = cat_dir / f"{args.project_id}.json"
    cat_dir.mkdir(parents=True, exist_ok=True)
    cat_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
    update_index(cat_dir, args.project_id, catalog["project_name"], make_default=args.default)
    print(f"── catálogo: {cat_path}")

    import make_test_assets
    mat_dir = cat_dir.parent / "materials"
    if any(not (mat_dir / mid / "albedo.webp").is_file() for mid in make_test_assets.MATERIALS):
        make_test_assets.write_materials(mat_dir)
        print("   materiais da biblioteca gerados em assets/materials")

    chk = validate_catalog.validate(catalog, public)
    for wmsg in chk.warnings:
        print(f"aviso: {wmsg}")
    for e in chk.errors:
        print(f"ERRO: {e}", file=sys.stderr)
    if chk.errors:
        return 1
    print(f"ok — abra http://localhost:5173/?project={args.project_id}")
    return 0


def _kv(cast):
    def parse(s: str):
        if "=" not in s:
            raise argparse.ArgumentTypeError(f"use chave=valor, recebi '{s}'")
        k, v = s.split("=", 1)
        return k.strip(), cast(v)
    return parse


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("render_dir", type=Path)
    ap.add_argument("project_id")
    ap.add_argument("camera")
    ap.add_argument("--prefix", help="prefixo dos arquivos (padrão: '<camera>_')")
    ap.add_argument("--project-name")
    ap.add_argument("--camera-name")
    ap.add_argument("--slot", type=parse_slot, action="append",
                    help="canal:id:Nome:tipo (padrão: r:piso:Piso:floor, g:bancada:Mármore:stone, b:parede:Paredes:paint)")
    ap.add_argument("--area", type=_kv(float), action="append", default=[], help="slot=m² (área real)")
    ap.add_argument("--tone", choices=["standard", "aces", "agx"], default="agx")
    ap.add_argument("--exposure", default="auto", help="'auto' ou número")
    ap.add_argument("--lg-kelvin", type=_kv(float), action="append", default=[], help="grupo=K com que a luz foi renderizada")
    ap.add_argument("--lg-name", type=_kv(str), action="append", default=[], help="grupo=Nome na interface")
    ap.add_argument("--default", action="store_true", help="tornar este o projeto padrão da página")
    ap.add_argument("--ignorar-alinhamento", dest="ignore_alignment", action="store_true",
                    help="importa mesmo com a máscara desalinhada da geometria")
    ap.add_argument("--masks-png", type=Path, help="PNG RGB que substitui o masks_a do render (ex.: derive_masks.py)")
    ap.add_argument("--light-from-beauty", action="store_true",
                    help="diff_light = beauty / diff_color (quando os passes de luz não reconstroem o beauty)")
    ap.add_argument("--web-root", type=Path, default=ROOT / "web" / "public")
    args = ap.parse_args(argv)
    args.slot = args.slot or DEFAULT_SLOTS
    args.lg_kelvin = dict(args.lg_kelvin)
    args.lg_name = dict(args.lg_name)
    try:
        return run(args)
    except (OSError, ValueError) as e:
        print(f"ERRO import_corona: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
