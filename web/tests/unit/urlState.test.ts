import { describe, expect, it } from 'vitest';
import { normalizeCatalog, type RawCatalog } from '../../src/catalog/schema';
import { budget, defaultState } from '../../src/state/store';
import { deserializeState, serializeState } from '../../src/state/urlState';

const raw: RawCatalog = {
  schema_version: 2,
  project_id: 'p',
  camera: 'cam_main',
  base_passes: {
    beauty: 'b.webp', uv_hi: 'hi.png', uv_lo: 'lo.png', uv_encoding: 'u16_hilo', uv_range: [0, 0, 6.2, 4.8],
    diffuse_light: 'dl.exr', masks_packed: [{ file: 'm.png', channels: { r: 'floor' } }],
  },
  light_groups: [
    { id: 'sun', name: 'Sol', pass: 'sun.exr', intensity: 1, kelvin: 5600, range: [0, 3] },
    { id: 'leds', name: 'LED', pass: 'leds.exr', intensity: 1, kelvin: 3000, range: [0, 5] },
  ],
  configurable_slots: [
    {
      id: 'floor', name: 'Piso', mask_ref: { file: 0, channel: 'r' }, default_texture: 'oak', area_m2: 18.4,
      allow_user_transform: { scale: [0.5, 2] },
      options: [
        {
          id: 'oak', name: 'Carvalho', diffuse_map: 'o.webp', price: { value: 189.9, unit: 'm2', currency: 'BRL' },
          tint_variants: [
            { id: 'natural', name: 'Natural', tint: [1, 1, 1] },
            { id: 'mel', name: 'Mel', tint: [1.05, 0.88, 0.7] },
          ],
        },
        { id: 'marble', name: 'Mármore', diffuse_map: 'm.webp', price: { value: 890, unit: 'm2', currency: 'BRL' } },
        { id: 'checker', name: 'Checker', diffuse_map: 'c.png', is_test: true },
      ],
    },
  ],
};
const cat = normalizeCatalog(raw);

describe('urlState', () => {
  it('estado padrão → URL só com a câmera', () => {
    expect(serializeState(defaultState(cat), cat).toString()).toBe('cam=cam_main');
  });

  it('exemplo do CLAUDE.md: ida e volta', () => {
    const q = 'cam=cam_main&floor=marble&floor.rot=90&floor.s=1.2&sun=1.4&sun.k=5600';
    const st = deserializeState(q, cat);
    expect(st.slots.floor).toMatchObject({ option: 'marble', rotation: 90, scale: 1.2 });
    expect(st.lights.sun).toEqual({ intensity: 1.4, kelvin: 5600 });
    // sun.k=5600 é o padrão, então some na volta; o resto se mantém
    const back = serializeState(st, cat);
    expect(Object.fromEntries(back)).toEqual({ cam: 'cam_main', floor: 'marble', 'floor.s': '1.2', 'floor.rot': '90', sun: '1.4' });
    expect(deserializeState(back, cat)).toEqual(st);
  });

  it('ida e volta com todos os campos', () => {
    const st = defaultState(cat);
    Object.assign(st.slots.floor!, { option: 'oak', variant: 'mel', scale: 0.75, rotation: 33.5, ox: 0.125, oy: 0.5 });
    st.lights.leds = { intensity: 2.35, kelvin: 4500 };
    expect(deserializeState(serializeState(st, cat), cat)).toEqual(st);
  });

  it('valores inválidos são ignorados ou limitados', () => {
    const st = deserializeState('floor=nao_existe&floor.s=9&floor.rot=-90&floor.ox=abc&sun=99&leds.k=100&floor.v=xx', cat);
    expect(st.slots.floor).toMatchObject({ option: 'oak', variant: 'natural', scale: 2, rotation: 270, ox: 0 });
    expect(st.lights.sun!.intensity).toBe(3);
    expect(st.lights.leds!.kelvin).toBe(2700);
  });

  it('trocar de material reinicia a variante para a primeira da opção', () => {
    const st = deserializeState('floor=marble&floor.v=mel', cat);
    expect(st.slots.floor!.variant).toBeNull();
  });
});

describe('orçamento', () => {
  it('área × preço com total (exemplo dos docs)', () => {
    const b = budget(cat, defaultState(cat));
    expect(b.lines[0]!.total).toBeCloseTo(3494.16, 2);
    expect(b.total).toBeCloseTo(3494.16, 2);
  });

  it('opção sem preço não entra', () => {
    const st = defaultState(cat);
    st.slots.floor!.option = 'checker';
    expect(budget(cat, st).lines).toHaveLength(0);
  });
});
