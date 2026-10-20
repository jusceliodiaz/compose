// Descobre qual superfície (slot) está sob um ponto da imagem, lendo as máscaras na CPU.
import type { NormalizedCatalog, Slot } from '../catalog/schema';

/** Largura máxima da cópia em CPU (a máscara 4K inteira ocuparia ~33 MB por arquivo). */
const MAX_W = 1280;

interface MaskData {
  data: Uint8ClampedArray;
  width: number;
  height: number;
}

export class Picker {
  private masks = new Map<string, MaskData>();

  constructor(private readonly catalog: NormalizedCatalog) {}

  async load(): Promise<void> {
    const files = this.catalog.cameras[0]?.passes.maskFiles ?? [];
    await Promise.all(
      files.map(async (url) => {
        const blob = await (await fetch(url)).blob();
        const bmp = await createImageBitmap(blob, { colorSpaceConversion: 'none', premultiplyAlpha: 'none' });
        const k = Math.min(1, MAX_W / bmp.width);
        const w = Math.max(1, Math.round(bmp.width * k));
        const h = Math.max(1, Math.round(bmp.height * k));
        const cv = new OffscreenCanvas(w, h);
        const ctx = cv.getContext('2d', { willReadFrequently: true })!;
        ctx.imageSmoothingEnabled = false; // máscara é dado: sem interpolação
        ctx.drawImage(bmp, 0, 0, w, h);
        bmp.close();
        this.masks.set(url, { data: ctx.getImageData(0, 0, w, h).data, width: w, height: h });
      }),
    );
  }

  /** (u, v) em [0, 1], origem no canto superior esquerdo da imagem. */
  slotAt(u: number, v: number): Slot | null {
    if (u < 0 || u > 1 || v < 0 || v > 1) return null;
    for (const slot of this.catalog.slots) {
      const m = this.masks.get(slot.maskFile);
      if (!m) continue;
      const x = Math.min(m.width - 1, Math.floor(u * m.width));
      const y = Math.min(m.height - 1, Math.floor(v * m.height));
      const ch = { r: 0, g: 1, b: 2 }[slot.channel];
      if (m.data[(y * m.width + x) * 4 + ch]! >= 128) return slot;
    }
    return null;
  }
}
