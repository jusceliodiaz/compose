// Export em alta resolução (CLAUDE.md §4 regra 10, Marco 6).
import { type Compositor, disposePassSet, loadPassSet } from './Compositor';

export interface ExportResult {
  blob: Blob;
  width: number;
  height: number;
  /** true quando a imagem está na resolução nativa de export (passes próprios para isso). */
  native: boolean;
  note: string | null;
}

const FALLBACK_WIDTH = 2048;

/** Limita (w, h) ao maxTextureSize da GPU; se não couber, cai para 2K mantendo a proporção. */
export function fitResolution(w: number, h: number, maxTex: number): [number, number] {
  if (w <= maxTex && h <= maxTex) return [w, h];
  const target = Math.min(FALLBACK_WIDTH, maxTex);
  const k = target / Math.max(w, h);
  return [Math.round(w * k), Math.round(h * k)];
}

/** Arquivo do passe de export: prefixo + nome do arquivo original. */
export function exportUrl(prefix: string, url: string): string {
  return prefix + url.slice(url.lastIndexOf('/') + 1);
}

export async function exportImage(c: Compositor): Promise<ExportResult> {
  const cam = c.currentCamera;
  if (!cam) throw new Error('nenhuma câmera carregada');
  const maxTex = c.maxTextureSize;
  const [ew, eh] = cam.exportResolution;

  let width: number;
  let height: number;
  let native = false;
  let note: string | null = null;
  let pixels: Uint8Array;

  if (cam.passes.exportPrefix) {
    // passes próprios para export: carrega sob demanda, renderiza e libera
    const prefix = cam.passes.exportPrefix;
    const passes = await loadPassSet(cam, (u) => exportUrl(prefix, u));
    try {
      [width, height] = fitResolution(passes.width, passes.height, maxTex);
      native = width === passes.width && height === passes.height;
      if (!native) note = `A GPU limita o export a ${width}×${height}.`;
      pixels = c.renderToPixels(width, height, passes);
    } finally {
      disposePassSet(passes);
    }
  } else {
    // sem passes de export: renderiza na resolução dos passes de exibição
    const [pw, ph] = c.passSize;
    [width, height] = fitResolution(pw, ph, maxTex);
    native = pw >= ew && ph >= eh;
    if (!native) note = `Exportado em ${width}×${height}: esta câmera não tem passes ${ew}×${eh}, então não é a resolução nativa de export.`;
    pixels = c.renderToPixels(width, height);
  }

  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('canvas 2D indisponível');
  ctx.putImageData(new ImageData(new Uint8ClampedArray(pixels.buffer as ArrayBuffer), width, height), 0, 0);
  const blob = await new Promise<Blob>((res, rej) =>
    canvas.toBlob((b) => (b ? res(b) : rej(new Error('falha ao gerar o PNG'))), 'image/png'),
  );
  canvas.width = canvas.height = 0; // libera a memória do canvas
  return { blob, width, height, native, note };
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
