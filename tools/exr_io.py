"""Leitura/escrita de imagens para as ferramentas do pipeline.

Tudo aqui trabalha em **RGB** (o OpenCV usa BGR internamente; a conversão acontece só neste
módulo). Importe este módulo antes de qualquer `import cv2` para garantir o suporte a EXR.
"""

from __future__ import annotations

import os

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")

from pathlib import Path  # noqa: E402

import cv2  # noqa: E402
import numpy as np  # noqa: E402

EXR_HALF = [
    cv2.IMWRITE_EXR_TYPE, cv2.IMWRITE_EXR_TYPE_HALF,
    cv2.IMWRITE_EXR_COMPRESSION, cv2.IMWRITE_EXR_COMPRESSION_ZIP,
]
EXR_FLOAT = [
    cv2.IMWRITE_EXR_TYPE, cv2.IMWRITE_EXR_TYPE_FLOAT,
    cv2.IMWRITE_EXR_COMPRESSION, cv2.IMWRITE_EXR_COMPRESSION_ZIP,
]


def _swap_rb(img: np.ndarray) -> np.ndarray:
    if img.ndim == 3 and img.shape[2] >= 3:
        out = img.copy()
        out[..., [0, 2]] = img[..., [2, 0]]
        return out
    return img


def _check_written(ok: bool, path: Path) -> None:
    if not ok:
        raise IOError(f"OpenCV não conseguiu gravar {path}. Verifique a pasta e o formato.")


def read_exr(path: str | Path) -> np.ndarray:
    """Lê um EXR e devolve float32 RGB(A), linhas de cima para baixo."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"EXR não encontrado: {path}")
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise IOError(
            f"OpenCV não leu {path}. Se for um EXR multilayer, use o pacote OpenEXR; "
            "confira também OPENCV_IO_ENABLE_OPENEXR=1 e opencv-python<5."
        )
    if img.ndim == 2:
        img = img[..., None]
    return _swap_rb(img.astype(np.float32))


def write_exr(path: str | Path, rgb: np.ndarray, half: bool = True) -> None:
    """Grava float RGB(A) como EXR (half + ZIP por padrão)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _swap_rb(np.ascontiguousarray(rgb, dtype=np.float32))
    _check_written(cv2.imwrite(str(path), data, EXR_HALF if half else EXR_FLOAT), path)


def to_half(x: np.ndarray) -> np.ndarray:
    """Arredonda para a precisão do EXR half (o que o arquivo realmente guarda)."""
    return np.asarray(x, dtype=np.float32).astype(np.float16).astype(np.float32)


def write_png(path: str | Path, rgb_u8: np.ndarray) -> None:
    """PNG 8-bit lossless. O OpenCV não grava chunks ICC/gAMA (regra 1 do CLAUDE.md)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if rgb_u8.dtype != np.uint8:
        raise TypeError("write_png espera uint8")
    _check_written(cv2.imwrite(str(path), _swap_rb(rgb_u8), [cv2.IMWRITE_PNG_COMPRESSION, 9]), path)


def read_png(path: str | Path) -> np.ndarray:
    path = Path(path)
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(f"Imagem não encontrada ou ilegível: {path}")
    if img.ndim == 2:
        img = img[..., None]
    return _swap_rb(img)


def write_webp(path: str | Path, rgb_u8: np.ndarray, quality: int = 90) -> None:
    """WebP; quality > 100 grava lossless."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _check_written(cv2.imwrite(str(path), _swap_rb(rgb_u8), [cv2.IMWRITE_WEBP_QUALITY, quality]), path)


def resize_area(img: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    return cv2.resize(img, size, interpolation=cv2.INTER_AREA)


# --- Cor -------------------------------------------------------------------------------

def linear_to_srgb(c: np.ndarray) -> np.ndarray:
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def srgb_to_linear(c: np.ndarray) -> np.ndarray:
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.04045, c / 12.92, np.power((c + 0.055) / 1.055, 2.4))


# Matrizes do AgX (mesmas do shader / three.js). GLSL é column-major: cada vec3 é uma COLUNA.
_SRGB_TO_REC2020 = np.array([[0.6274, 0.0691, 0.0164], [0.3293, 0.9195, 0.0880], [0.0433, 0.0113, 0.8956]]).T
_REC2020_TO_SRGB = np.array([[1.6605, -0.1246, -0.0182], [-0.5876, 1.1329, -0.1006], [-0.0728, -0.0083, 1.1187]]).T
_AGX_INSET = np.array([[0.856627153315983, 0.137318972929847, 0.11189821299995],
                       [0.0951212405381588, 0.761241990602591, 0.0767994186031903],
                       [0.0482516061458583, 0.101439036467562, 0.811302368396859]]).T
_AGX_OUTSET = np.array([[1.1271005818144368, -0.1413297634984383, -0.14132976349843826],
                        [-0.11060664309660323, 1.157823702216272, -0.11060664309660294],
                        [-0.016493938717834573, -0.016493938717834257, 1.2519364065950405]]).T


def _agx(x: np.ndarray) -> np.ndarray:
    c = x[..., :3] @ (_AGX_INSET @ _SRGB_TO_REC2020).T
    c = np.clip((np.log2(np.maximum(c, 1e-10)) + 12.47393) / (4.026069 + 12.47393), 0.0, 1.0)
    c2 = c * c
    c4 = c2 * c2
    c = 15.5 * c4 * c2 - 40.14 * c4 * c + 31.96 * c4 - 6.868 * c2 * c + 0.4298 * c2 + 0.1191 * c - 0.00232
    c = c @ _AGX_OUTSET.T
    c = np.power(np.maximum(c, 0.0), 2.2)
    return np.clip(c @ _REC2020_TO_SRGB.T, 0.0, 1.0)


def tonemap(hdr: np.ndarray, operator: str = "standard", exposure: float = 1.0) -> np.ndarray:
    """Mesmo tone mapping do shader (standard = clamp, aces, agx)."""
    x = hdr * exposure
    if operator == "standard":
        return np.clip(x, 0.0, 1.0)
    if operator == "aces":
        return np.clip((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0)
    if operator == "agx":
        return _agx(x)
    raise ValueError(f"tone mapping '{operator}' desconhecido (use standard, aces ou agx)")


def luminance(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722


def to_u8(x01: np.ndarray) -> np.ndarray:
    return np.clip(np.round(x01 * 255.0), 0, 255).astype(np.uint8)
