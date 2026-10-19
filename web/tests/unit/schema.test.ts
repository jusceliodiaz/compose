import { describe, expect, it } from 'vitest';
import { CatalogError, normalizeCatalog, type RawCatalog } from '../../src/catalog/schema';

function base(): RawCatalog {
  return {
    schema_version: 2,
    project_id: 'p',
    camera: 'cam',
    base_passes: {
      beauty: 'b.webp',
      uv_hi: 'hi.png',
      uv_lo: 'lo.png',
      uv_encoding: 'u16_hilo',
      uv_range: [0, 0, 6.2, 4.8],
      diffuse_light: 'dl.exr',
      masks_packed: [{ file: 'm.png', channels: { r: 'floor' } }],
    },
    configurable_slots: [
      {
        id: 'floor',
        name: 'Piso',
        mask_ref: { file: 0, channel: 'r' },
        default_texture: 'a',
        options: [
          { id: 'a', name: 'A', diffuse_map: 'a.webp', texture_size_m: [1.2, 0.2] },
          { id: 'b', name: 'B', diffuse_map: 'b.webp', default_tiling: [5, 5] },
          { id: 'c', name: 'C', albedo_color: [0.35, 0.35, 0.35] },
        ],
      },
    ],
  };
}

describe('normalizeCatalog', () => {
  it('tiling físico = 1 / texture_size_m; senão default_tiling', () => {
    const c = normalizeCatalog(base());
    const [a, b] = c.slots[0]!.options;
    expect(a!.tiling[0]).toBeCloseTo(0.8333, 4);
    expect(a!.tiling[1]).toBeCloseTo(5, 6);
    expect(b!.tiling).toEqual([5, 5]);
  });

  it('fallbacks: gloss_keep 0.6, escala [0.5, 2], tone agx, resolução 1080p', () => {
    const c = normalizeCatalog(base());
    expect(c.slots[0]!.options[0]!.glossKeep).toBe(0.6);
    expect(c.slots[0]!.scaleRange).toEqual([0.5, 2]);
    expect(c.cameras[0]!.tone.operator).toBe('agx');
    expect(c.cameras[0]!.viewResolution).toEqual([1920, 1080]);
  });

  it('sem uv_hi/uv_lo → uv_map 8-bit, com nota', () => {
    const raw = base();
    delete raw.base_passes.uv_hi;
    delete raw.base_passes.uv_lo;
    raw.base_passes.uv_map = 'uv.png';
    const c = normalizeCatalog(raw);
    expect(c.cameras[0]!.passes.uv.kind).toBe('u8');
    expect(c.notes.join(' ')).toMatch(/8 bits/);
  });

  it('sem diffuse_light → modo simplificado (precisa de shadow_ao)', () => {
    const raw = base();
    delete raw.base_passes.diffuse_light;
    expect(() => normalizeCatalog(raw)).toThrow(CatalogError);
    raw.base_passes.shadow_ao = 'ao.png';
    expect(normalizeCatalog(raw).notes.join(' ')).toMatch(/simplificado/);
  });

  it('resolve caminhos contra a base', () => {
    const c = normalizeCatalog(base(), '/app/');
    expect(c.cameras[0]!.passes.beautyDisplay).toBe('/app/b.webp');
  });

  it('erros: default inexistente e canal repetido', () => {
    const raw = base();
    raw.configurable_slots[0]!.default_texture = 'zz';
    raw.configurable_slots.push({ ...raw.configurable_slots[0]!, id: 'x', default_texture: 'a' });
    try {
      normalizeCatalog(raw);
      throw new Error('deveria falhar');
    } catch (e) {
      const msg = (e as CatalogError).problems.join(' | ');
      expect(msg).toMatch(/default_texture/);
      expect(msg).toMatch(/repetido/);
    }
  });
});
