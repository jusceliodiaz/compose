import { expect, test } from '@playwright/test';
import { openApp, probes } from './helpers';

// Funções que rodam dentro da página (sem transferir megabytes de pixels para o Node).
declare global {
  interface Window { __compose: any }
}

test('material original + LightMix neutro = beauty (diferença < 2/255)', async ({ page }) => {
  await openApp(page, '?floor=original');
  const r = await page.evaluate(async () => {
    const c = window.__compose.compositor;
    const [w, h] = c.passSize;
    const px: Uint8Array = c.renderToPixels(w, h);
    const blob = await (await fetch('assets/scenes/test_room/cam_main/beauty.webp')).blob();
    const bmp = await createImageBitmap(blob, { colorSpaceConversion: 'none', premultiplyAlpha: 'none' });
    const cv = new OffscreenCanvas(w, h);
    const ctx = cv.getContext('2d')!;
    ctx.drawImage(bmp, 0, 0);
    const ref = ctx.getImageData(0, 0, w, h).data;
    let max = 0;
    let over = 0;
    for (let i = 0; i < px.length; i += 4) {
      for (let k = 0; k < 3; k++) {
        const d = Math.abs(px[i + k]! - ref[i + k]!);
        if (d > max) max = d;
        if (d >= 2) over++;
      }
    }
    return { max, over, w, h };
  });
  expect(r.w).toBe(1920);
  expect(r.h).toBe(1080);
  expect(r.over, `pixels com diferença ≥ 2 (máx ${r.max})`).toBe(0);
});

test('orientação: UV decodificado e máscara batem com os pontos de referência (flipY)', async ({ page }) => {
  await openApp(page);
  const pts = await probes(page);
  const r = await page.evaluate((pts) => {
    const c = window.__compose.compositor;
    const [w, h] = c.passSize;
    const range = c.currentCamera.passes.uv.range as number[];
    c.setDebug(1);
    const px: Uint8Array = c.renderToPixels(w, h);
    c.setDebug(0);
    let worstUV = 0;
    let maskErr = 0;
    for (const p of pts) {
      const i = (p.y * w + p.x) * 4;
      const mask = px[i + 2]! > 127 ? 1 : 0;
      if (mask !== p.mask) maskErr++;
      if (!p.mask) continue;
      const u = range[0]! + (px[i]! / 255) * (range[2]! - range[0]!);
      const v = range[1]! + (px[i + 1]! / 255) * (range[3]! - range[1]!);
      worstUV = Math.max(worstUV, Math.abs(u - p.u), Math.abs(v - p.v));
    }
    return { worstUV, maskErr };
  }, pts);
  expect(r.maskErr).toBe(0);
  expect(r.worstUV).toBeLessThan(0.03); // 8-bit da leitura: ~2,4 cm por degrau
});

test('checker: 1 tile por metro, sem espelhamento', async ({ page }) => {
  await openApp(page, '?floor=checker');
  const pts = (await probes(page)).filter((p) => p.mask && p.y > 1080 * 0.45);
  const r = await page.evaluate(async (pts) => {
    const c = window.__compose.compositor;
    const [w, h] = c.passSize;
    c.setDebug(5);
    const px: Uint8Array = c.renderToPixels(w, h);
    c.setDebug(0);
    const blob = await (await fetch('assets/materials/checker/albedo.png')).blob();
    const bmp = await createImageBitmap(blob, { colorSpaceConversion: 'none' });
    const S = bmp.width;
    const cv = new OffscreenCanvas(S, S);
    const ctx = cv.getContext('2d')!;
    ctx.drawImage(bmp, 0, 0);
    const tex = ctx.getImageData(0, 0, S, S).data;
    const frac = (x: number) => x - Math.floor(x);
    const texel = (u: number, v: number) => {
      const x = Math.min(S - 1, Math.floor(frac(u) * S));
      const y = Math.min(S - 1, Math.floor((1 - frac(v)) * S)); // flipY: v = 0 embaixo
      const i = (y * S + x) * 4;
      return [tex[i]!, tex[i + 1]!, tex[i + 2]!];
    };
    const hyps: Record<string, (u: number, v: number) => [number, number]> = {
      correto: (u, v) => [u, v],
      espelhoU: (u, v) => [-u, v],
      espelhoV: (u, v) => [u, -v],
      trocado: (u, v) => [v, u],
      escala2x: (u, v) => [u * 2, v * 2],
    };
    const err: Record<string, number> = {};
    for (const [name, f] of Object.entries(hyps)) {
      let sum = 0;
      for (const p of pts) {
        const [tu, tv] = f(p.u, p.v);
        const t = texel(tu, tv);
        const i = (p.y * w + p.x) * 4;
        sum += (Math.abs(px[i]! - t[0]!) + Math.abs(px[i + 1]! - t[1]!) + Math.abs(px[i + 2]! - t[2]!)) / 3;
      }
      err[name] = sum / pts.length;
    }
    return err;
  }, pts);
  expect(pts.length).toBeGreaterThan(100);
  expect(r.correto).toBeLessThan(12);
  for (const k of ['espelhoU', 'espelhoV', 'escala2x']) {
    expect(r[k], `${k} deveria errar mais que o correto (${JSON.stringify(r)})`).toBeGreaterThan(r.correto! * 1.8);
  }
  // o tabuleiro é quase simétrico na diagonal: só os números distinguem U↔V, então a margem é menor
  expect(r.trocado).toBeGreaterThan(r.correto! * 1.4);
});

test('sem costuras: nenhum pixel interno do piso é marcado como costura', async ({ page }) => {
  await openApp(page, '?floor=checker');
  const seams = await page.evaluate(() => {
    const c = window.__compose.compositor;
    const [w, h] = c.passSize;
    c.setDebug(2);
    const m: Uint8Array = c.renderToPixels(w, h);
    c.setDebug(4);
    const s: Uint8Array = c.renderToPixels(w, h);
    c.setDebug(0);
    let n = 0;
    const inside = (x: number, y: number) => m[(y * w + x) * 4]! > 127;
    for (let y = 1; y < h - 1; y++) {
      for (let x = 1; x < w - 1; x++) {
        let all = true;
        for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) all &&= inside(x + dx, y + dy);
        if (!all) continue;
        const i = (y * w + x) * 4;
        if (s[i]! > 240 && s[i + 1]! < 60) n++;
      }
    }
    return n;
  });
  expect(seams).toBe(0);
});
