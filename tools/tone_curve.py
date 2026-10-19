"""Reconstrói a curva de tone mapping de um render que já veio "display-referred" (EXR com tone mapping).

Ideia: dentro de um slot texturizado a luz varia devagar e o albedo (veio, juntas) varia rápido. Então, nos
detalhes finos, ∂log(beauty) ≈ p(T)·∂log(albedo), onde p(T) = d log T / d log x é a inclinação local da curva
no brilho T. Medimos p por faixa de brilho, ajustamos um modelo suave p(T) = p0·(1 − (T/Tc)^n) (com piso
`P_MIN` para a curva continuar invertível até ~1) e integramos d log x = d log T / p(T).

Com a curva T(x) em mãos:
  - o importador "deslineariza" os passes: x = T⁻¹(beauty), luz = x / albedo;
  - o shader aplica a MESMA curva como tone mapping (LUT) → material original = beauty exato, e materiais
    claros comprimem no ombro da curva como no render.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

import exr_io

P_MIN = 0.08          # inclinação mínima (acima de Tc) — mantém a curva invertível até T ≈ 1
ANCHOR = 0.18         # T(0.18) = 0.18: fixa a escala do espaço linear reconstruído
LUT_SIZE = 128


@dataclass
class Curve:
    p0: float
    tc: float
    n: float
    t: np.ndarray       # brilho de saída (crescente)
    log2x: np.ndarray   # log2 da entrada linear correspondente
    bins: list[tuple[float, float, int]]

    pmin: float = P_MIN
    method: str = "slopes"

    def p(self, t: np.ndarray) -> np.ndarray:
        return slope_model(t, self.p0, self.tc, self.n, self.pmin)

    def forward(self, x: np.ndarray) -> np.ndarray:
        """T(x), por canal."""
        ev = np.log2(np.maximum(x, 1e-12))
        out = np.interp(ev, self.log2x, self.t)
        low = ev < self.log2x[0]
        return np.where(low, self.t[0] * np.exp2(self.p0 * (ev - self.log2x[0])), out)

    def inverse(self, t: np.ndarray) -> np.ndarray:
        """x = T⁻¹(t), por canal (t é limitado ao intervalo da curva)."""
        t = np.asarray(t, dtype=np.float64)
        ev = np.interp(np.clip(t, self.t[0], self.t[-1]), self.t, self.log2x)
        low = t < self.t[0]
        ev = np.where(low, self.log2x[0] + np.log2(np.maximum(t, 1e-12) / self.t[0]) / self.p0, ev)
        return np.exp2(ev)

    def lut(self) -> dict:
        lo, hi = float(self.log2x[0]), float(self.log2x[-1])
        evs = np.linspace(lo, hi, LUT_SIZE)
        vals = np.interp(evs, self.log2x, self.t)
        return {"log2_min": round(lo, 5), "log2_max": round(hi, 5), "low_slope": round(self.p0, 5),
                "values": [round(float(v), 6) for v in vals]}


def slope_model(t, p0, tc, n, pmin=P_MIN):
    t = np.asarray(t, dtype=np.float64)
    return np.maximum(p0 * (1.0 - np.power(np.clip(t / tc, 0, None), n)), pmin)


def local_slopes(beauty: np.ndarray, albedo: np.ndarray, mask: np.ndarray,
                 width: float = 0.05, min_n: int = 3000, min_corr: float = 0.5) -> list[tuple[float, float, int]]:
    """(brilho central, inclinação p, nº de pixels) por faixa de brilho do beauty suavizado."""
    import cv2

    yb = exr_io.luminance(beauty).astype(np.float32)
    lb = np.log(np.maximum(yb, 1e-4))
    ld = np.log(np.maximum(exr_io.luminance(albedo), 1e-4)).astype(np.float32)
    hb = lb - cv2.GaussianBlur(lb, (0, 0), 6)
    hd = ld - cv2.GaussianBlur(ld, (0, 0), 6)
    smooth = cv2.GaussianBlur(yb, (0, 0), 6)
    inner = cv2.erode(mask.astype(np.uint8), np.ones((25, 25), np.uint8)) > 0
    out = []
    for lo in np.arange(0.0, 1.0, width):
        sel = inner & (smooth >= lo) & (smooth < lo + width)
        if sel.sum() < min_n:
            continue
        x, y = hd[sel], hb[sel]
        if float((x * x).sum()) < 1e-6:
            continue
        corr = float(np.corrcoef(x, y)[0, 1])
        if corr < min_corr:
            continue
        out.append((float(lo + width / 2), float((x * y).sum() / (x * x).sum()), int(sel.sum())))
    return out


def _integrate(p0: float, tc: float, n: float, pmin: float) -> tuple[np.ndarray, np.ndarray]:
    """Integra d ln x = d ln T / p(T); devolve (T, log2 x) com T(ANCHOR) = ANCHOR."""
    tg = np.geomspace(1e-3, 0.999, 4000)
    lnt = np.log(tg)
    inv_p = 1.0 / slope_model(tg, p0, tc, n, pmin)
    lnx = np.concatenate([[0.0], np.cumsum(0.5 * (inv_p[1:] + inv_p[:-1]) * np.diff(lnt))])
    lnx += np.log(ANCHOR) - np.interp(np.log(ANCHOR), lnt, lnx)
    return tg, lnx / np.log(2)


def fit_from_light(beauty: np.ndarray, albedo: np.ndarray, light_tm: np.ndarray, reflect: np.ndarray | None = None,
                   samples: int = 60000, seed: int = 0) -> Curve | None:
    """Ajuste pela relação T⁻¹(beauty) = albedo · T⁻¹(diff_light), quando o passe de luz difusa também saiu
    com tone mapping. Usa a imagem inteira (todos os albedos), só pixels com pouco reflexo."""
    yb, ya, yl = exr_io.luminance(beauty), exr_io.luminance(albedo), exr_io.luminance(light_tm)
    sel = (ya > 0.02) & (yl > 0.02) & (yl < 0.99) & (yb > 0.01) & (yb < 0.99)
    if reflect is not None:
        sel &= exr_io.luminance(reflect) < 0.15 * yb
    idx = np.flatnonzero(sel)
    if idx.size < 2000 or np.ptp(np.log(ya.flat[idx])) < 1.0:
        return None
    idx = np.random.default_rng(seed).choice(idx, min(samples, idx.size), replace=False)
    y1, y2, a = yl.flat[idx], yb.flat[idx], np.log(ya.flat[idx])
    best = (np.inf, None)
    for p0 in np.linspace(0.3, 1.6, 27):
        for tc in np.linspace(0.5, 1.4, 19):
            for n in (1.0, 2.0, 3.0, 4.0, 6.0, 8.0):
                for pmin in (0.05, 0.1, 0.2, 0.3, 0.4):
                    tg, l2 = _integrate(p0, tc, n, pmin)
                    r = np.interp(y2, tg, l2) - np.interp(y1, tg, l2) - a / np.log(2)
                    e = float(np.median(np.abs(r - np.median(r))))
                    if e < best[0]:
                        best = (e, (p0, tc, n, pmin))
    p0, tc, n, pmin = best[1]
    tg, l2 = _integrate(p0, tc, n, pmin)
    c = Curve(float(p0), float(tc), float(n), tg, l2, [], float(pmin), "diff_light")
    c.fit_error = best[0]  # type: ignore[attr-defined]
    return c


def fit_curve(bins: list[tuple[float, float, int]]) -> Curve:
    """Ajusta p(T) aos pontos medidos e integra a curva. Sem pontos, usa uma curva fílmica genérica."""
    if bins:
        t = np.array([b[0] for b in bins])
        p = np.array([b[1] for b in bins])
        wgt = np.array([b[2] for b in bins], dtype=np.float64)
        best = (np.inf, 0.6, 1.0, 4.0)
        for p0 in np.linspace(0.3, 1.0, 36):
            for tc in np.linspace(max(t.max(), 0.3), 1.3, 41):
                for n in np.linspace(1, 10, 37):
                    e = float((wgt * (slope_model(t, p0, tc, n) - p) ** 2).sum())
                    if e < best[0]:
                        best = (e, p0, tc, n)
        _, p0, tc, n = best
    else:
        p0, tc, n = 0.6, 1.0, 4.0
    # integra d ln x = d ln T / p(T) numa grade log de T
    tg = np.geomspace(1e-3, 0.999, 4000)
    lnt = np.log(tg)
    inv_p = 1.0 / slope_model(tg, p0, tc, n)
    lnx = np.concatenate([[0.0], np.cumsum(0.5 * (inv_p[1:] + inv_p[:-1]) * np.diff(lnt))])
    lnx += np.log(ANCHOR) - np.interp(np.log(ANCHOR), lnt, lnx)
    return Curve(float(p0), float(tc), float(n), tg, lnx / np.log(2), list(bins))
