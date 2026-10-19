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


def tonemap(hdr: np.ndarray, operator: str = "standard", exposure: float = 1.0) -> np.ndarray:
    """Mesmo tone mapping do shader. Só `standard` (clamp) e `aces` são espelhados aqui."""
    x = hdr * exposure
    if operator == "standard":
        return np.clip(x, 0.0, 1.0)
    if operator == "aces":
        return np.clip((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0)
    raise ValueError(f"tone mapping '{operator}' não suportado nas ferramentas (use standard ou aces)")


def to_u8(x01: np.ndarray) -> np.ndarray:
    return np.clip(np.round(x01 * 255.0), 0, 255).astype(np.uint8)
