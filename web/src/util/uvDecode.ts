// Espelho em JS do decodeUV do shader (composite.frag.glsl), para testes e para o debug.

export type UVRange = readonly [number, number, number, number];

/** hi/lo: bytes 0..255 dos canais R (U) e G (V). Devolve [u, v] em metros. */
export function decodeUV(hi: readonly [number, number], lo: readonly [number, number], range: UVRange): [number, number] {
  const qu = (Math.round(hi[0]) * 256 + Math.round(lo[0])) / 65535;
  const qv = (Math.round(hi[1]) * 256 + Math.round(lo[1])) / 65535;
  return [range[0] + (range[2] - range[0]) * qu, range[1] + (range[3] - range[1]) * qv];
}

/** Inverso (o que o pack_uv.py faz), útil para testes de ida e volta. */
export function encodeUV(u: number, v: number, range: UVRange): { hi: [number, number]; lo: [number, number] } {
  const q = (x: number, a: number, b: number) =>
    Math.round(Math.min(1, Math.max(0, (x - a) / Math.max(b - a, 1e-9))) * 65535);
  const qu = q(u, range[0], range[2]);
  const qv = q(v, range[1], range[3]);
  return { hi: [qu >> 8, qv >> 8], lo: [qu & 255, qv & 255] };
}

/** Transformação do material: tuv = R(θ)·(uv·S) + O, com R = mat2(c, s, -s, c) (column-major). */
export function transformUV(
  uv: readonly [number, number],
  tiling: readonly [number, number],
  rotationRad: number,
  offset: readonly [number, number],
): [number, number] {
  const c = Math.cos(rotationRad);
  const s = Math.sin(rotationRad);
  const x = uv[0] * tiling[0];
  const y = uv[1] * tiling[1];
  // mat2(c, s, -s, c) * (x, y) = (c·x − s·y, s·x + c·y)
  return [c * x - s * y + offset[0], s * x + c * y + offset[1]];
}
