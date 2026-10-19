"""Gera uma "câmera falsa" fisicamente coerente (sem Blender/3ds Max) — Marco 1.

Cena: câmera em (0, 1.6, 0) olhando 35° para baixo (eixo -Z), FOV vertical 50°, 1920×1080.
Sala de 6.2 m (X) × 4.8 m (Z) com piso em y=0, parede do fundo em z=-5.7 e paredes laterais em
x=±3.1. Só o piso é slot configurável (mask=1); as paredes são o "fundo" (mask=0).

Para cada pixel: interseção raio–plano → UV em metros (u = x - x0, v = z - z0) e iluminação
analítica (janela na parede esquerda, sombra de um "sofá", termo indireto constante).

Uso: python tools/make_test_assets.py [--out web/public/assets] [--width 1920 --height 1080]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

import exr_io
from make_checker import make_checker

ROOT = Path(__file__).resolve().parents[1]

# --- Geometria (metros) ----------------------------------------------------------------
CAM_POS = np.array([0.0, 1.6, 0.0])
PITCH_DEG = 35.0
VFOV_DEG = 50.0
X0, X1 = -3.1, 3.1          # largura do piso → u ∈ [0, 6.2]
Z0, Z1 = -5.7, -0.9         # profundidade do piso → v ∈ [0, 4.8]
WINDOW_Z = (-4.6, -2.2)     # janela na parede esquerda (x = X0)
WINDOW_Y = (0.5, 2.4)
SOFA = dict(cx=-1.0, cz=-3.2, rx=1.0, rz=0.45)

FLOOR_ALBEDO = 0.35                         # albedo original do piso (linear, cinza-bege neutro)
WALL_ALBEDO = np.array([0.62, 0.58, 0.52])  # linear
TONE = {"operator": "standard", "exposure": 1.0}


def smoothstep(e0: float, e1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def camera_rays(w: int, h: int) -> np.ndarray:
    """Direções (h, w, 3) normalizadas, linha 0 = topo da imagem."""
    p = np.radians(PITCH_DEG)
    fwd = np.array([0.0, -np.sin(p), -np.cos(p)])
    right = np.array([1.0, 0.0, 0.0])
    up = np.array([0.0, np.cos(p), -np.sin(p)])
    tv = np.tan(np.radians(VFOV_DEG) / 2)
    th = tv * w / h
    xs = ((np.arange(w) + 0.5) / w * 2 - 1) * th
    ys = (1 - (np.arange(h) + 0.5) / h * 2) * tv
    gx, gy = np.meshgrid(xs, ys)
    d = fwd + gx[..., None] * right + gy[..., None] * up
    return d / np.linalg.norm(d, axis=-1, keepdims=True)


def build_scene(w: int = 1920, h: int = 1080) -> dict[str, np.ndarray]:
    d = camera_rays(w, h)
    dx, dy, dz = d[..., 0], d[..., 1], d[..., 2]
    big = np.full(dx.shape, np.inf)

    with np.errstate(divide="ignore", invalid="ignore"):
        t_floor = np.where(dy < 0, -CAM_POS[1] / dy, big)
        t_back = np.where(dz < 0, (Z0 - CAM_POS[2]) / dz, big)
        t_left = np.where(dx < 0, (X0 - CAM_POS[0]) / dx, big)
        t_right = np.where(dx > 0, (X1 - CAM_POS[0]) / dx, big)
    ts = np.stack([t_floor, t_back, t_left, t_right])
    surf = np.argmin(ts, axis=0)            # 0 piso, 1 fundo, 2 esquerda, 3 direita
    t = np.min(ts, axis=0)
    P = CAM_POS + d * t[..., None]
    x, y, z = P[..., 0], P[..., 1], P[..., 2]

    floor = (surf == 0) & (x >= X0) & (x <= X1) & (z >= Z0) & (z <= Z1)

    # --- Luz no piso ---
    q = ((x - SOFA["cx"]) / SOFA["rx"]) ** 2 + ((z - SOFA["cz"]) / SOFA["rz"]) ** 2
    blob = np.exp(-q)                                           # sombra suave do "sofá"
    band = smoothstep(WINDOW_Z[0] - 0.2, WINDOW_Z[0] + 0.5, z) * (1 - smoothstep(WINDOW_Z[1] - 0.5, WINDOW_Z[1] + 0.2, z))
    sun_floor = 2.65 * band * np.exp(-np.maximum(x - X0, 0) / 1.3) * (1 - 0.8 * blob)
    ceil_floor = np.full_like(x, 0.32) * (1 - 0.35 * blob)
    gloss_floor = 0.17 * np.exp(-((x + 2.0) ** 2) / (2 * 0.3 ** 2)) * np.exp(-((z + 2.6) ** 2) / (2 * 1.1 ** 2)) * (1 - 0.6 * blob)

    # --- Paredes (fundo, mask = 0) ---
    ao_floor = 1 - 0.35 * np.exp(-np.maximum(y, 0) / 0.15)
    sun_back = 0.55 * np.exp(-(x - X0) / 2.2) * ao_floor
    ceil_back = 0.42 * ao_floor
    window = (surf == 2) & (z > WINDOW_Z[0]) & (z < WINDOW_Z[1]) & (y > WINDOW_Y[0]) & (y < WINDOW_Y[1])
    sun_right = 1.5 * np.exp(-((z + 3.6) ** 2) / 0.6) * smoothstep(0.2, 0.5, y) * (1 - smoothstep(1.4, 1.8, y))
    ceil_side = 0.30 * ao_floor

    sun = np.zeros_like(x)
    ceil = np.zeros_like(x)
    gloss = np.zeros(x.shape + (3,))
    albedo = np.zeros(x.shape + (3,))

    def put(sel, s, c, a):
        sun[sel] = s[sel] if isinstance(s, np.ndarray) else s
        ceil[sel] = c[sel] if isinstance(c, np.ndarray) else c
        albedo[sel] = a

    put(surf == 1, sun_back, ceil_back, WALL_ALBEDO)
    put(surf == 2, np.zeros_like(x), ceil_side, WALL_ALBEDO)
    put(surf == 3, sun_right, ceil_side + 0.05, WALL_ALBEDO)
    put(window, 3.2, 0.0, np.ones(3))                             # vidro "emissivo" da janela
    put(surf == 0, sun_floor, ceil_floor, np.full(3, FLOOR_ALBEDO * 0.9))  # piso fora do slot
    put(floor, sun_floor, ceil_floor, np.full(3, FLOOR_ALBEDO))
    gloss[floor] = gloss_floor[floor][:, None]

    # A luz é cinza (sem cor) exceto um leve tom quente no sol
    sun_rgb = sun[..., None] * np.array([1.0, 0.96, 0.9])
    ceil_rgb = ceil[..., None] * np.array([0.92, 0.96, 1.0])

    # Quantiza para half ANTES de compor: assim a reconstrução bate com o que está no arquivo
    dc = exr_io.to_half(albedo)
    dl = exr_io.to_half(sun_rgb + ceil_rgb)
    gl = exr_io.to_half(gloss)
    beauty = exr_io.to_half(dc * dl + gl)
    lg_ceiling = exr_io.to_half(dc * exr_io.to_half(ceil_rgb))
    lg_sun = exr_io.to_half(beauty - lg_ceiling)

    uv = np.zeros(x.shape + (4,), np.float32)
    uv[..., 0] = np.where(floor, x - X0, 0)
    uv[..., 1] = np.where(floor, z - Z0, 0)
    uv[..., 3] = floor.astype(np.float32)                         # alfa = cobertura

    return dict(
        beauty=beauty, diff_light=dl, diff_color=dc, glossy=gl,
        lg_sun=lg_sun, lg_ceiling=lg_ceiling, uv=uv,
        mask=floor.astype(np.float32), shadow=np.clip(dl.mean(-1) / 3.0, 0, 1),
    )


# --- Materiais procedurais (sem emendas: ruído periódico via FFT) ------------------------

def periodic_noise(h: int, w: int, beta: float, seed: int, stretch: tuple[float, float] = (1.0, 1.0)) -> np.ndarray:
    """Ruído 1/f^beta. Por ser síntese no domínio da frequência, é periódico (tileable)."""
    rng = np.random.default_rng(seed)
    fy = np.fft.fftfreq(h)[:, None] * h * stretch[0]
    fx = np.fft.fftfreq(w)[None, :] * w * stretch[1]
    f = np.sqrt(fx ** 2 + fy ** 2)
    f[0, 0] = 1.0
    spec = np.fft.fft2(rng.standard_normal((h, w))) / f ** beta
    spec[0, 0] = 0
    n = np.real(np.fft.ifft2(spec))
    return (n - n.mean()) / (n.std() + 1e-9)


def make_wood(px_per_m: int = 512, seed: int = 7) -> np.ndarray:
    """Réguas de 1.2 × 0.2 m, 6 fileiras desencontradas; textura cobre 2.4 × 1.2 m."""
    W, H = int(2.4 * px_per_m), int(1.2 * px_per_m)
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    row_h = H / 6
    plank_w = W / 2
    row = (yy // row_h).astype(int)
    offsets = rng.choice([0.0, 0.25, 0.5, 0.75], 6) * plank_w
    xm = (xx + offsets[row]) % W
    plank = row * 2 + (xm // plank_w).astype(int)
    tones = rng.uniform(0.82, 1.15, 12)
    shift = rng.uniform(0, W, 12)

    grain = periodic_noise(H, W, 1.6, seed + 1, stretch=(1.0, 14.0))
    fine = periodic_noise(H, W, 0.9, seed + 2, stretch=(1.0, 30.0))
    ly = (yy % row_h) / row_h
    rings = 0.5 + 0.5 * np.sin(2 * np.pi * (ly * 3.0 + 0.35 * np.roll(grain, 37, 1) + shift[plank] / W * 2))
    base = np.array([0.42, 0.24, 0.12])                       # carvalho, linear
    v = tones[plank][..., None] * (1 + 0.10 * grain[..., None] + 0.05 * fine[..., None]) * (0.86 + 0.18 * rings[..., None])
    col = base * v
    # juntas entre réguas
    seam_x = np.minimum(xm % plank_w, plank_w - xm % plank_w)
    seam_y = np.minimum(yy % row_h, row_h - yy % row_h)
    seam = np.clip(np.minimum(seam_x, seam_y) / 1.5, 0, 1)
    col *= (0.55 + 0.45 * seam)[..., None]
    return exr_io.to_u8(exr_io.linear_to_srgb(col))


def make_marble(px: int = 1024, seed: int = 11) -> np.ndarray:
    """Mármore claro com veios; textura cobre 1.2 × 1.2 m."""
    yy, xx = np.mgrid[0:px, 0:px].astype(np.float64) / px
    turb = periodic_noise(px, px, 1.9, seed)
    turb2 = periodic_noise(px, px, 1.2, seed + 3)
    phase = 2 * np.pi * (1 * xx + 2 * yy) + 2.4 * turb
    veins = np.power(np.abs(np.sin(phase)), 0.18)
    veins2 = np.power(np.abs(np.sin(2 * np.pi * (3 * xx - 1 * yy) + 3.0 * turb2)), 0.08)
    base = np.array([0.80, 0.80, 0.78]) * (1 + 0.03 * turb2[..., None])
    vein_col = np.array([0.30, 0.31, 0.33])
    k = (1 - veins)[..., None] * 0.85 + (1 - veins2)[..., None] * 0.35
    col = base * (1 - np.clip(k, 0, 1)) + vein_col * np.clip(k, 0, 1)
    return exr_io.to_u8(exr_io.linear_to_srgb(col))


def make_concrete(px: int = 1024, seed: int = 23) -> np.ndarray:
    """Cimento queimado; textura cobre 1.0 × 1.0 m."""
    a = periodic_noise(px, px, 1.8, seed)
    b = periodic_noise(px, px, 1.0, seed + 1)
    c = periodic_noise(px, px, 0.3, seed + 2)
    lum = 0.20 * (1 + 0.18 * a + 0.06 * b + 0.04 * c)
    col = lum[..., None] * np.array([1.0, 1.0, 1.02])
    return exr_io.to_u8(exr_io.linear_to_srgb(col))


MATERIALS = {
    # id: (função, tamanho real em metros [u, v])
    "oak": (make_wood, (2.4, 1.2)),
    "marble": (make_marble, (1.2, 1.2)),
    "concrete": (make_concrete, (1.0, 1.0)),
}


def write_materials(mat_dir: Path) -> None:
    for mid, (fn, _) in MATERIALS.items():
        img = fn()
        exr_io.write_webp(mat_dir / mid / "albedo.webp", img, 92)
        h, w = img.shape[:2]
        s = min(h, w)
        exr_io.write_webp(mat_dir / mid / "thumb.webp", exr_io.resize_area(img[:s, :s], (256, 256)), 88)
    chk = make_checker(1024)
    exr_io.write_png(mat_dir / "checker" / "albedo.png", chk)
    exr_io.write_webp(mat_dir / "checker" / "thumb.webp", exr_io.resize_area(chk, (256, 256)), 88)


def probe_points(scene: dict[str, np.ndarray]) -> list[dict]:
    """Pixels de referência (x, y a partir do topo) com UV e máscara esperados — usados nos
    testes de orientação (flipY) no navegador."""
    h, w = scene["mask"].shape
    pts = []
    for fx, fy in [(0.5, 0.95), (0.2, 0.8), (0.8, 0.6), (0.5, 0.45), (0.1, 0.35), (0.5, 0.05)]:
        px, py = int(fx * w), int(fy * h)
        uvp = scene["uv"][py, px]
        pts.append({"x": px, "y": py, "mask": int(scene["mask"][py, px]), "u": float(uvp[0]), "v": float(uvp[1])})
    return pts


def write_scene(cam_dir: Path, scene: dict[str, np.ndarray]) -> None:
    cam_dir.mkdir(parents=True, exist_ok=True)
    for name in ["beauty", "diff_light", "diff_color", "glossy", "lg_sun", "lg_ceiling"]:
        exr_io.write_exr(cam_dir / f"{name}.exr", scene[name], half=True)
    # UV em float32: o half teria degraus de ~4 mm acima de 4 m (só a fonte; a web usa hi/lo)
    exr_io.write_exr(cam_dir / "uv.exr", scene["uv"], half=False)

    m = exr_io.to_u8(scene["mask"])
    masks = np.zeros(m.shape + (3,), np.uint8)
    masks[..., 0] = m                                             # R = piso
    exr_io.write_png(cam_dir / "masks_a.png", masks)
    exr_io.write_png(cam_dir / "shadow_ao.png", np.repeat(exr_io.to_u8(scene["shadow"])[..., None], 3, -1))

    ldr = exr_io.linear_to_srgb(exr_io.tonemap(scene["beauty"], TONE["operator"], TONE["exposure"]))
    exr_io.write_webp(cam_dir / "beauty.webp", exr_io.to_u8(ldr), 101)  # lossless
    (cam_dir / "probes.json").write_text(json.dumps(probe_points(scene), indent=2), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "web" / "public" / "assets")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--skip-materials", action="store_true")
    args = ap.parse_args()

    scene = build_scene(args.width, args.height)
    cam_dir = args.out / "scenes" / "test_room" / "cam_main"
    write_scene(cam_dir, scene)
    print(f"passes: {cam_dir}")
    if not args.skip_materials:
        write_materials(args.out / "materials")
        print(f"materiais: {args.out / 'materials'}")

    try:  # Marco 2: empacota o UV e escreve o catálogo, se as ferramentas existirem
        from build_test_catalog import build_all
    except ImportError:
        return
    build_all(args.out)


if __name__ == "__main__":
    main()
