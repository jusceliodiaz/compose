// Estado ↔ URL. Ex.: ?cam=cam_main&floor=marble&floor.rot=90&floor.s=1.2&sun=1.4&sun.k=5600
// Só grava o que difere do padrão; ao ler, valida tudo contra o catálogo (valores fora da faixa são limitados).
import type { NormalizedCatalog } from '../catalog/schema';
import { KELVIN_MAX, KELVIN_MIN } from '../util/kelvin';
import { defaultState, type ConfigState } from './store';

const clamp = (x: number, a: number, b: number) => Math.min(b, Math.max(a, x));
const num = (s: string | null): number | null => {
  if (s === null || s.trim() === '') return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
};
const fmt = (x: number, digits: number) => String(Number(x.toFixed(digits)));

export function kelvinBounds(renderKelvin: number): [number, number] {
  return [Math.min(KELVIN_MIN, renderKelvin), Math.max(KELVIN_MAX, renderKelvin)];
}

export function serializeState(state: ConfigState, catalog: NormalizedCatalog): URLSearchParams {
  const def = defaultState(catalog, state.cam);
  const q = new URLSearchParams();
  q.set('cam', state.cam);
  for (const s of catalog.slots) {
    const c = state.slots[s.id];
    const d = def.slots[s.id];
    if (!c || !d) continue;
    if (c.option !== d.option) q.set(s.id, c.option);
    const opt = s.options.find((o) => o.id === c.option);
    const defVariant = opt?.tintVariants[0]?.id ?? null;
    if (c.variant && c.variant !== defVariant) q.set(`${s.id}.v`, c.variant);
    if (c.scale !== 1) q.set(`${s.id}.s`, fmt(c.scale, 2));
    if (c.rotation !== 0) q.set(`${s.id}.rot`, fmt(c.rotation, 1));
    if (c.ox !== 0) q.set(`${s.id}.ox`, fmt(c.ox, 3));
    if (c.oy !== 0) q.set(`${s.id}.oy`, fmt(c.oy, 3));
  }
  for (const [id, l] of Object.entries(state.lights)) {
    const d = def.lights[id];
    if (!d) continue;
    if (l.intensity !== d.intensity) q.set(id, fmt(l.intensity, 2));
    if (l.kelvin !== d.kelvin) q.set(`${id}.k`, fmt(l.kelvin, 0));
  }
  return q;
}

export function deserializeState(params: URLSearchParams | string, catalog: NormalizedCatalog): ConfigState {
  const q = typeof params === 'string' ? new URLSearchParams(params) : params;
  const camId = q.get('cam');
  const cam = catalog.cameras.find((c) => c.id === camId) ?? catalog.cameras[0]!;
  const st = defaultState(catalog, cam.id);

  for (const s of catalog.slots) {
    const c = st.slots[s.id]!;
    const optId = q.get(s.id);
    const opt = s.options.find((o) => o.id === optId);
    if (opt) {
      c.option = opt.id;
      c.variant = opt.tintVariants[0]?.id ?? null;
    }
    const current = s.options.find((o) => o.id === c.option)!;
    const v = q.get(`${s.id}.v`);
    if (v && current.tintVariants.some((t) => t.id === v)) c.variant = v;
    const sc = num(q.get(`${s.id}.s`));
    if (sc !== null) c.scale = clamp(sc, s.scaleRange[0], s.scaleRange[1]);
    const rot = num(q.get(`${s.id}.rot`));
    if (rot !== null && s.allowRotation) c.rotation = ((rot % 360) + 360) % 360;
    const ox = num(q.get(`${s.id}.ox`));
    const oy = num(q.get(`${s.id}.oy`));
    if (s.allowOffset) {
      if (ox !== null) c.ox = clamp(ox, 0, 1);
      if (oy !== null) c.oy = clamp(oy, 0, 1);
    }
  }
  for (const g of cam.lightGroups) {
    const l = st.lights[g.id]!;
    const i = num(q.get(g.id));
    if (i !== null) l.intensity = clamp(i, g.range[0], g.range[1]);
    const k = num(q.get(`${g.id}.k`));
    if (k !== null) l.kelvin = clamp(Math.round(k), ...kelvinBounds(g.kelvin));
  }
  return st;
}
