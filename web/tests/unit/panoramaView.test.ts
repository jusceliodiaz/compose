import { describe, expect, it } from 'vitest';
import { clampView, dirToEquirect, screenToEquirect } from '../../src/engine/panoramaView';

describe('panoramaView', () => {
  it('frente = centro da imagem; direita, trás, zênite e nadir', () => {
    expect(dirToEquirect(0, 0, -1)).toEqual([0.5, 0.5]);
    expect(dirToEquirect(1, 0, 0)[0]).toBeCloseTo(0.75);
    expect(dirToEquirect(-1, 0, 0)[0]).toBeCloseTo(0.25);
    expect(dirToEquirect(0, 0, 1)[0]).toBeCloseTo(0, 5);
    expect(dirToEquirect(0, 1, 0)[1]).toBeCloseTo(1);
    expect(dirToEquirect(0, -1, 0)[1]).toBeCloseTo(0);
  });

  it('centro da tela segue yaw/pitch; v da tela cresce para baixo (referencial do Picker)', () => {
    const c = screenToEquirect({ yaw: 0, pitch: 0, fov: 75 }, 0.5, 0.5, 16 / 9);
    expect(c[0]).toBeCloseTo(0.5);
    expect(c[1]).toBeCloseTo(0.5);
    const right = screenToEquirect({ yaw: Math.PI / 2, pitch: 0, fov: 75 }, 0.5, 0.5, 1);
    expect(right[0]).toBeCloseTo(0.75);
    const up = screenToEquirect({ yaw: 0, pitch: Math.PI / 4, fov: 75 }, 0.5, 0.5, 1);
    expect(up[1]).toBeCloseTo(0.25);
    // sem espelhamento: o lado direito da tela cai à direita na imagem; o de cima, acima
    const v = { yaw: 0, pitch: 0, fov: 75 };
    expect(screenToEquirect(v, 0.9, 0.5, 1)[0]).toBeGreaterThan(0.5);
    expect(screenToEquirect(v, 0.5, 0.1, 1)[1]).toBeLessThan(0.5);
  });

  it('limita pitch e fov e normaliza yaw', () => {
    const v = clampView({ yaw: 3 * Math.PI, pitch: 3, fov: 500 });
    expect(v.yaw).toBeCloseTo(-Math.PI);
    expect(v.pitch).toBeCloseTo((85 * Math.PI) / 180);
    expect(v.fov).toBe(100);
  });
});
