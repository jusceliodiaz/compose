import { describe, expect, it } from 'vitest';
import { kelvinToLinearRGB, kelvinToSRGB, lightTint } from '../../src/util/kelvin';

describe('kelvin', () => {
  it('6500 K é praticamente branco', () => {
    const [r, g, b] = kelvinToSRGB(6500);
    expect(r).toBeGreaterThan(0.98);
    expect(g).toBeGreaterThan(0.9);
    expect(b).toBeGreaterThan(0.9);
  });

  it('2700 K é quente (R > G > B) e 6500 K é mais azul que 2700 K', () => {
    const warm = kelvinToLinearRGB(2700);
    const cool = kelvinToLinearRGB(6500);
    expect(warm[0]).toBeGreaterThan(warm[1]);
    expect(warm[1]).toBeGreaterThan(warm[2]);
    expect(cool[2] / cool[0]).toBeGreaterThan(warm[2] / warm[0]);
  });

  it('normalizado em luminância (só muda a cor)', () => {
    for (const k of [2700, 3500, 5000, 6500]) {
      const [r, g, b] = kelvinToLinearRGB(k);
      expect(0.2126 * r + 0.7152 * g + 0.0722 * b).toBeCloseTo(1, 6);
    }
  });

  it('LightMix neutro: kelvin == kelvin do render e intensidade 1 → [1, 1, 1]', () => {
    expect(lightTint(1, 5600, 5600)).toEqual([1, 1, 1]);
    expect(lightTint(2, 4000, 4000)).toEqual([2, 2, 2]);
  });

  it('a intensidade escala a luminância do tint', () => {
    const [r, g, b] = lightTint(1.5, 3000, 5600);
    expect(0.2126 * r + 0.7152 * g + 0.0722 * b).toBeCloseTo(1.5, 6);
    expect(r).toBeGreaterThan(b);
  });
});
