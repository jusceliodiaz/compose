import { loadCatalog } from './catalog/loadCatalog';
import { Compositor } from './engine/Compositor';

// Harness do Marco 4 (substituído pela interface no Marco 5)
const canvas = document.querySelector<HTMLCanvasElement>('#view')!;
const compositor = new Compositor(canvas);
const ready = (async () => {
  const catalog = await loadCatalog(`${import.meta.env.BASE_URL}assets/catalog/test_room.json`);
  await compositor.setCamera(catalog, catalog.cameras[0]!.id);
  const q = new URLSearchParams(location.search);
  for (const slot of catalog.slots) {
    const opt = q.get(slot.id);
    if (opt) await compositor.setSlotMaterial(slot.id, opt);
  }
  compositor.setSize(canvas.clientWidth, canvas.clientHeight);
  return catalog;
})();

Object.assign(window, { __compose: { compositor, ready } });
