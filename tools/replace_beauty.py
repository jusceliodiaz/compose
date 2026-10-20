"""Troca só a imagem base (beauty) de uma câmera já importada — ex.: uma versão refeita/retocada com IA.

Uso:
  python tools/replace_beauty.py web/public/assets/catalog/sala_estar.json renders/sala_estar_ia/cam7_beauty_ia.png

A imagem nova costuma ter outro tamanho/enquadramento: ela é REGISTRADA (pontos SIFT + homografia) sobre o
beauty atual da câmera e reamostrada para a resolução dos passes. Depois é levada ao mesmo espaço de luz do motor
(inversa da curva de tone mapping do catálogo), as bordas entre superfícies são limpas e as miniaturas
"Original do render" são refeitas. Os passes de luz/UV/máscaras não mudam.

Limites (avisados no fim):
  - o que a IA redesenhou (forma, objetos novos) não bate com as máscaras/UV;
  - os grupos de luz (LightMix) vêm do render original: são removidos do catálogo (use --manter-luzes para manter).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import exr_io  # antes do cv2: liga o OpenEXR
import cv2
import numpy as np

import edge_clean
import import_corona
import validate_catalog

ROOT = Path(__file__).resolve().parents[1]
WORK_W = 1920  # largura usada para achar a correspondência


def lut_inverse(t: np.ndarray, lut: dict) -> np.ndarray:
    """T⁻¹ pela LUT do catálogo (o mesmo que o shader aplica, invertido)."""
    vals = np.asarray(lut["values"], dtype=np.float64)
    grid = np.linspace(lut["log2_min"], lut["log2_max"], len(vals))
    tt = np.clip(np.asarray(t, dtype=np.float64), 1e-6, vals[-1])
    ev = np.interp(tt, vals, grid)
    low = tt < vals[0]
    ev = np.where(low, grid[0] + np.log2(tt / vals[0]) / lut["low_slope"], ev)
    return np.exp2(ev)


def register(img: np.ndarray, ref: np.ndarray) -> tuple[np.ndarray, dict]:
    """Homografia img → ref (coordenadas de pixel completas) e estatísticas da correspondência."""
    si, sr = WORK_W / img.shape[1], WORK_W / ref.shape[1]
    g1 = cv2.cvtColor(cv2.resize(img, None, fx=si, fy=si, interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2GRAY)
    g2 = cv2.cvtColor(cv2.resize(ref, None, fx=sr, fy=sr, interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2GRAY)
    sift = cv2.SIFT_create(8000)
    k1, d1 = sift.detectAndCompute(g1, None)
    k2, d2 = sift.detectAndCompute(g2, None)
    if d1 is None or d2 is None:
        raise ValueError("não encontrei pontos de referência nas imagens")
    good = [a for a, b in cv2.BFMatcher().knnMatch(d1, d2, k=2) if a.distance < 0.75 * b.distance]
    if len(good) < 50:
        raise ValueError(f"só {len(good)} correspondências — a imagem parece ser de outro enquadramento")
    p1 = np.float32([k1[a.queryIdx].pt for a in good])
    p2 = np.float32([k2[a.trainIdx].pt for a in good])
    H, inl = cv2.findHomography(p1, p2, cv2.RANSAC, 3.0)
    inl = inl.ravel() > 0
    err = np.linalg.norm(cv2.perspectiveTransform(p1[inl].reshape(-1, 1, 2), H).reshape(-1, 2) - p2[inl], axis=1)
    Hf = np.diag([1 / sr, 1 / sr, 1]) @ H @ np.diag([si, si, 1])
    stats = {"matches": len(good), "inliers": int(inl.sum()),
             "err_med_px": float(np.median(err) / sr), "err_p90_px": float(np.percentile(err, 90) / sr)}
    return Hf / Hf[2, 2], stats


def register_structure(img: np.ndarray, ref: np.ndarray) -> tuple[np.ndarray, float]:
    """Registro pela estrutura (gradientes) com ECC — funciona mesmo quando a IA trocou cores/materiais,
    porque linhas de teto, quinas e janelas continuam no lugar. Tenta encaixe pela largura e pela altura."""
    W = 960
    Hh = round(ref.shape[0] * W / ref.shape[1])

    def grad(x, size):
        g = cv2.cvtColor(cv2.resize(x, size, interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
        g = cv2.GaussianBlur(g, (0, 0), 1.2)
        m = np.hypot(cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1))
        return m / (m.max() + 1e-6)

    R = grad(ref, (W, Hh))
    best = None
    for s in (W / img.shape[1], Hh / img.shape[0]):
        tw, th = round(img.shape[1] * s), round(img.shape[0] * s)
        A = grad(img, (tw, th))
        canvas = np.zeros_like(R)
        ox, oy = (W - tw) // 2, (Hh - th) // 2
        x0, y0, x1, y1 = max(ox, 0), max(oy, 0), min(ox + tw, W), min(oy + th, Hh)
        canvas[y0:y1, x0:x1] = A[y0 - oy:y1 - oy, x0 - ox:x1 - ox]
        try:
            cc, warp = cv2.findTransformECC(R, canvas, np.eye(3, dtype=np.float32), cv2.MOTION_HOMOGRAPHY,
                                            (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 300, 1e-6), None, 5)
        except cv2.error:
            continue
        if best is None or cc > best[0]:
            best = (cc, s, ox, oy, warp)
    if best is None:
        raise ValueError("o registro pela estrutura não convergiu")
    cc, s, ox, oy, warp = best
    to_canvas = np.array([[s, 0, ox], [0, s, oy], [0, 0, 1]], np.float64)
    Hf = np.diag([ref.shape[1] / W, ref.shape[1] / W, 1]) @ np.linalg.inv(warp.astype(np.float64)) @ to_canvas
    return Hf / Hf[2, 2], float(cc)


def edge_agreement(a: np.ndarray, b: np.ndarray) -> float:
    """Fração das bordas de a que caem (±2 px) sobre bordas de b, em 1080p."""
    def edges(x):
        g = cv2.cvtColor(cv2.resize(x, (WORK_W, round(x.shape[0] * WORK_W / x.shape[1])), interpolation=cv2.INTER_AREA),
                         cv2.COLOR_RGB2GRAY)
        return cv2.Canny(g, 60, 150) > 0
    ea, eb = edges(a), edges(b)
    eb = cv2.dilate(eb.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    return float((ea & eb).sum() / max(ea.sum(), 1))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("catalog", type=Path)
    ap.add_argument("image", type=Path, help="PNG/JPG/WebP 8-bit (sRGB)")
    ap.add_argument("--web-root", type=Path, default=ROOT / "web" / "public")
    ap.add_argument("--manter-luzes", dest="keep_lights", action="store_true")
    ap.add_argument("--forcar", dest="force", action="store_true", help="aceita registro ruim")
    args = ap.parse_args(argv)

    cat = json.loads(args.catalog.read_text(encoding="utf-8"))
    bp = cat["base_passes"]
    cam = args.web_root / Path(bp["beauty"]).parent
    ref = exr_io.read_png(args.web_root / bp["beauty"])[..., :3]           # beauty atual (exibição)
    img = cv2.imread(str(args.image), cv2.IMREAD_COLOR)
    if img is None:
        print(f"ERRO: não consegui ler {args.image}", file=sys.stderr)
        return 1
    img = img[..., ::-1].copy()
    h, w = ref.shape[:2]
    print(f"── nova base: {args.image.name} {img.shape[1]}×{img.shape[0]} → {w}×{h}")

    try:
        H, st = register(img, ref)
        print(f"   registro por pontos: {st['inliers']}/{st['matches']} coerentes · erro mediano "
              f"{st['err_med_px']:.2f} px (p90 {st['err_p90_px']:.2f} px)")
        ok_points = st["inliers"] >= 150 and st["err_med_px"] <= 2.5
    except ValueError as e:
        print(f"   registro por pontos: {e}")
        st, ok_points = {}, False
    if not ok_points:
        H, cc = register_structure(img, ref)
        st = {"method": "estrutura (ECC)", "correlation": round(cc, 3)}
        print(f"   poucos pontos em comum (a IA mudou cores/materiais) → registro pela estrutura: correlação {cc:.2f}")
        if cc < 0.5 and not args.force:
            print("ERRO: o alinhamento ficou ruim. Use --forcar para aplicar mesmo assim.", file=sys.stderr)
            return 1
    warp = cv2.warpPerspective(img, H, (w, h), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
    print(f"   bordas que coincidem com o render: antes {edge_agreement(cv2.resize(img, (w, h)), ref) * 100:.0f}% "
          f"→ depois {edge_agreement(warp, ref) * 100:.0f}%")

    # espaço de luz do motor: exibição → T⁻¹
    disp = exr_io.srgb_to_linear(warp.astype(np.float32) / 255.0)
    tm = cat.get("tone_mapping", {})
    lin = lut_inverse(disp, tm["lut"]) if tm.get("operator") == "lut" else disp / max(tm.get("exposure", 1.0), 1e-6)

    # bordas: mesmas regiões das máscaras atuais
    slot_mask = {}
    for s in cat["configurable_slots"]:
        ref_m = s["mask_ref"]
        m = exr_io.read_png(args.web_root / bp["masks_packed"][ref_m["file"]]["file"])
        slot_mask[s["id"]] = m[..., "rgb".index(ref_m["channel"])].astype(np.float32) / 255.0
    labels = edge_clean.region_labels(list(slot_mask.values()))
    dst, src = edge_clean.nearest_interior(labels, width=2)
    lin = edge_clean.apply(lin.astype(np.float32), dst, src)

    backup = cam / "_beauty_anterior"
    if not backup.exists():
        backup.mkdir()
        for f in ("beauty.exr", "beauty.webp"):
            shutil.copy2(cam / f, backup / f)
        print(f"   cópia da base anterior em {backup}")
    exr_io.write_exr(cam / "beauty.exr", lin)
    exr_io.write_webp(cam / "beauty.webp", warp, 92)
    for sid, m in slot_mask.items():
        import_corona.original_thumb(warp, m, cam / f"thumb_original_{sid}.webp")

    if cat.get("light_groups") and not args.keep_lights:
        print(f"   grupos de luz removidos ({', '.join(g['id'] for g in cat['light_groups'])}): vinham do render "
              "original e devolveriam o visual antigo. A exposição continua ajustável.")
        cat["light_groups"] = []
    cat["beauty_source"] = {"file": args.image.name, "registration": st}
    chk = validate_catalog.validate(cat, args.web_root)
    for e in chk.errors:
        print(f"ERRO: {e}", file=sys.stderr)
    if chk.errors:
        return 1
    args.catalog.write_text(json.dumps(cat, indent=2, ensure_ascii=False), encoding="utf-8")
    print("ok — recarregue a página")
    return 0


if __name__ == "__main__":
    sys.exit(main())
