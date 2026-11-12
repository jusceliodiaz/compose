import { normalizeCatalog, type NormalizedCatalog } from './schema';

export async function loadCatalog(url: string, base = import.meta.env.BASE_URL): Promise<NormalizedCatalog> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(
      `Catalog not found (${res.status}) at ${url}. ` +
        'Generate the test assets with: python tools/make_test_assets.py',
    );
  }
  const cat = normalizeCatalog(await res.json(), base);
  for (const n of cat.notes) console.info(`[catalog] ${n}`);
  return cat;
}
