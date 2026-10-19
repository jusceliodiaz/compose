import { describe, expect, it } from 'vitest';
import { decodeUV, encodeUV, transformUV } from '../../src/util/uvDecode';

const RANGE = [0, 0, 6.2, 4.8] as const;

describe('decodeUV (espelho do shader)', () => {
  it('ida e volta com erro ≤ range/65535', () => {
    for (let i = 0; i < 2000; i++) {
      const u = Math.random() * 6.2;
      const v = Math.random() * 4.8;
      const { hi, lo } = encodeUV(u, v, RANGE);
      const [du, dv] = decodeUV(hi, lo, RANGE);
      expect(Math.abs(du - u)).toBeLessThanOrEqual(6.2 / 65535);
      expect(Math.abs(dv - v)).toBeLessThanOrEqual(4.8 / 65535);
    }
  });

  it('exemplo numérico dos docs (Seção 3.3): q = (0.25, 0.60)', () => {
    const qu = Math.round(0.25 * 65535);
    const qv = Math.round(0.6 * 65535);
    const [u, v] = decodeUV([qu >> 8, qv >> 8], [qu & 255, qv & 255], RANGE);
    expect(u).toBeCloseTo(1.55, 3);
    expect(v).toBeCloseTo(2.88, 3);
  });

  it('extremos do range', () => {
    expect(decodeUV([0, 0], [0, 0], RANGE)).toEqual([0, 0]);
    expect(decodeUV([255, 255], [255, 255], RANGE)).toEqual([6.2, 4.8]);
  });
});

describe('transformUV: tuv = R(θ)·(uv·S) + O', () => {
  it('escala física de 1,20 m', () => {
    const [x, y] = transformUV([1.55, 2.88], [1 / 1.2, 1 / 1.2], 0, [0, 0]);
    expect(x).toBeCloseTo(1.2917, 3);
    expect(y).toBeCloseTo(2.4, 3);
  });

  it('gira no sentido anti-horário (+θ), não em −θ', () => {
    const [x, y] = transformUV([1, 0], [1, 1], Math.PI / 2, [0, 0]);
    expect(x).toBeCloseTo(0, 6);
    expect(y).toBeCloseTo(1, 6);
  });

  it('o offset é somado depois da rotação', () => {
    const [x, y] = transformUV([1, 0], [1, 1], Math.PI / 2, [0.5, 0]);
    expect(x).toBeCloseTo(0.5, 6);
    expect(y).toBeCloseTo(1, 6);
  });
});
