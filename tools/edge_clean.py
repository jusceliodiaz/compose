"""Limpa as bordas entre superfícies para a troca de material não deixar "linha" da cor antiga.

O beauty tem antialiasing: o pixel da divisa parede/piso é meio parede, meio piso. As máscaras do render de
dados são duras (cada pixel pertence a uma superfície). Ao trocar a parede, o pixel da divisa que ficou do lado
do piso ainda carrega a cor da parede antiga → aparece um fio claro/escuro.

Solução: rotular cada pixel (superfície dominante ou fundo) e, numa faixa de `width` px de cada lado de toda
divisa, copiar os valores do pixel INTERIOR mais próximo da mesma região. Aplica-se aos passes de luz/beauty;
o UV e as máscaras (já duros) ficam como estão.
"""

from __future__ import annotations

import exr_io  # noqa: F401 — liga o OpenEXR do OpenCV antes do primeiro import do cv2
import cv2
import numpy as np


def region_labels(slot_masks: list[np.ndarray], threshold: float = 0.5) -> np.ndarray:
    """0 = fundo (nenhuma superfície), i+1 = superfície i dominante."""
    stack = np.stack(slot_masks)
    lab = np.argmax(stack, axis=0).astype(np.int32) + 1
    lab[stack.max(axis=0) < threshold] = 0
    return lab


def nearest_interior(labels: np.ndarray, width: int = 2) -> tuple[np.ndarray, np.ndarray]:
    """Para cada pixel de borda, o índice (linear) do pixel interior mais próximo da mesma região.

    Devolve (pixels_de_borda[N], fonte[N]) em índices lineares da imagem.
    """
    h, w = labels.shape
    k = np.ones((2 * width + 1, 2 * width + 1), np.uint8)
    dst_all: list[np.ndarray] = []
    src_all: list[np.ndarray] = []
    for r in np.unique(labels):
        reg = (labels == r).astype(np.uint8)
        other = cv2.dilate(1 - reg, k) > 0
        edge = (reg > 0) & other
        interior = (reg > 0) & ~other
        if not edge.any() or not interior.any():
            continue
        # distância até o interior; DIST_LABEL_PIXEL dá um rótulo por pixel-zero (ordem de varredura)
        _, lab = cv2.distanceTransformWithLabels((~interior).astype(np.uint8), cv2.DIST_L2, 5,
                                                 labelType=cv2.DIST_LABEL_PIXEL)
        zeros = np.flatnonzero(interior.ravel())          # pixels interiores em ordem de varredura
        ey, ex = np.nonzero(edge)
        src = zeros[lab[ey, ex] - 1]
        dst_all.append(ey * w + ex)
        src_all.append(src)
    if not dst_all:
        return np.empty(0, np.int64), np.empty(0, np.int64)
    return np.concatenate(dst_all), np.concatenate(src_all)


def apply(img: np.ndarray, dst: np.ndarray, src: np.ndarray) -> np.ndarray:
    """Copia src → dst (índices lineares) em todos os canais."""
    out = img.copy()
    flat = out.reshape(-1, out.shape[-1]) if out.ndim == 3 else out.reshape(-1)
    flat[dst] = flat[src]
    return out


def fill_gaps(labels: np.ndarray, width: int = 2) -> np.ndarray:
    """Frestas finas de "fundo" (≤ 2·width px) entre superfícies viram a superfície mais próxima.

    O render de dados às vezes deixa 1 px sem nenhuma máscara entre dois objetos; esse pixel mostraria a cor
    antiga ao trocar qualquer um dos lados.
    """
    bg = (labels == 0).astype(np.uint8)
    k = np.ones((2 * width + 1, 2 * width + 1), np.uint8)
    gap = (bg > 0) & ~(cv2.morphologyEx(bg, cv2.MORPH_OPEN, k) > 0)
    if not gap.any() or not (labels > 0).any():
        return labels
    _, lab = cv2.distanceTransformWithLabels((labels == 0).astype(np.uint8), cv2.DIST_L2, 5,
                                             labelType=cv2.DIST_LABEL_PIXEL)
    zeros = np.flatnonzero((labels > 0).ravel())
    out = labels.copy()
    gy, gx = np.nonzero(gap)
    out[gy, gx] = labels.ravel()[zeros[lab[gy, gx] - 1]]
    return out
