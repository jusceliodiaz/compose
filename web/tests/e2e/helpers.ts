import type { Page } from '@playwright/test';

export interface Probe { x: number; y: number; mask: number; u: number; v: number }

/** Abre a página e espera o motor carregar a câmera. */
export async function openApp(page: Page, query = ''): Promise<void> {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  // os testes usam sempre a sala sintética (o projeto padrão do índice pode ser outro)
  await page.goto(`/?project=test_room${query ? `&${query.replace(/^\?/, '')}` : ''}`);
  await page.waitForFunction(() => (window as any).__compose?.ready, null, { timeout: 30_000 });
  await page.evaluate(() => (window as any).__compose.ready);
  if (errors.length) throw new Error(errors.join('\n'));
}

export async function probes(page: Page): Promise<Probe[]> {
  return page.evaluate(async () => (await fetch('assets/scenes/test_room/cam_main/probes.json')).json());
}
