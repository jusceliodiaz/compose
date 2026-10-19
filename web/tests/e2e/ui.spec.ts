import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';
import { openApp } from './helpers';

test('troca o material pela URL e confere o screenshot', async ({ page }) => {
  await openApp(page, '?floor=marble');
  await expect(page.locator('.mat-card.is-active .mat-name')).toHaveText('Mármore Carrara');
  await expect(page.locator('.frame')).toHaveClass(/is-ready/);
  await expect(page.locator('.frame-canvas')).toHaveScreenshot('floor-marble.png', { maxDiffPixelRatio: 0.01 });

  // e a imagem tem que ser diferente da do carvalho (padrão)
  const marble = await page.locator('.frame-canvas').screenshot();
  await openApp(page, '');
  await expect(page.locator('.frame')).toHaveClass(/is-ready/);
  const oak = await page.locator('.frame-canvas').screenshot();
  expect(Buffer.compare(marble, oak)).not.toBe(0);
});

test('a interface atualiza a URL (material, rotação, luz) e restaura ao recarregar', async ({ page }) => {
  await openApp(page);
  await page.getByRole('radio', { name: /Mármore Carrara/ }).click();
  await page.getByRole('button', { name: '90°' }).click();
  await page.getByRole('slider', { name: 'Intensidade' }).first().fill('1.5');
  await expect.poll(() => page.url()).toContain('floor=marble');
  await expect.poll(() => page.url()).toContain('floor.rot=90');
  await expect.poll(() => page.url()).toContain('sun=1.5');

  await page.reload();
  await page.waitForFunction(() => (window as any).__compose?.ready);
  await page.evaluate(() => (window as any).__compose.ready);
  await expect(page.locator('.mat-card.is-active .mat-name')).toHaveText('Mármore Carrara');
  await expect(page.locator('#floor-rot')).toHaveValue('90');
  const st = await page.evaluate(() => (window as any).__compose.store.get());
  expect(st.lights.sun.intensity).toBe(1.5);
  // 29,76 m² × R$ 890,00
  await expect(page.locator('.bud-total-val')).toContainText('26.486,40');
});

test('grade de teste e comparador antes/depois', async ({ page }) => {
  await openApp(page);
  await page.keyboard.press('t');
  await expect(page.getByRole('button', { name: /Grade de teste/ })).toHaveAttribute('aria-pressed', 'true');
  await expect.poll(() => page.url()).toContain('floor=checker');
  await page.keyboard.press('t');
  await expect.poll(() => page.url()).not.toContain('floor=checker');

  await page.getByRole('button', { name: /Antes \/ depois/ }).click();
  const box = (await page.locator('.frame').boundingBox())!;
  await page.mouse.click(box.x + box.width * 0.25, box.y + box.height / 2);
  const split = await page.evaluate(() => (window as any).__compose.compositor.material.uniforms.u_splitX.value);
  expect(split).toBeGreaterThan(0.2);
  expect(split).toBeLessThan(0.3);
});

test('export: PNG na resolução esperada e idêntico ao render', async ({ page }) => {
  await openApp(page, '?floor=oak&floor.rot=30');
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: /Baixar imagem/ }).click();
  const file = await (await download).path();
  const png = readFileSync(file);
  expect(png.subarray(1, 4).toString()).toBe('PNG');
  const w = png.readUInt32BE(16);
  const h = png.readUInt32BE(20);
  // o catálogo de teste pede 3840×2160 mas não tem passes de export → sai na resolução dos passes, com aviso
  expect([w, h]).toEqual([1920, 1080]);
  await expect(page.locator('.toast')).toContainText('não é a resolução nativa');

  const diff = await page.evaluate(async () => {
    const c = (window as any).__compose;
    const r = c.lastExport;
    const bmp = await createImageBitmap(r.blob, { colorSpaceConversion: 'none', premultiplyAlpha: 'none' });
    const cv = new OffscreenCanvas(r.width, r.height);
    const ctx = cv.getContext('2d')!;
    ctx.drawImage(bmp, 0, 0);
    const a = ctx.getImageData(0, 0, r.width, r.height).data;
    const b: Uint8Array = c.compositor.renderToPixels(r.width, r.height);
    let n = 0;
    for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) n++;
    return n;
  });
  expect(diff).toBe(0);
});
