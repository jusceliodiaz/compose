import { normalizeCatalog, type NormalizedCatalog } from './schema';

export async function loadCatalog(url: string, base = import.meta.env.BASE_URL): Promise<NormalizedCatalog> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(
      `Não encontrei o catálogo (${res.status}) em ${url}. ` +
        'Gere os assets de teste com: python tools/make_test_assets.py',
    );
  }
  const cat = normalizeCatalog(await res.json(), base);
  for (const n of cat.notes) console.info(`[catálogo] ${n}`);
  return cat;
}
