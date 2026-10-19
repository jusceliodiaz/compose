// Kelvin → RGB linear. Aproximação de Tanner Helland (ajuste do corpo negro, 1000–40000 K),
// que devolve sRGB 0–255; convertido aqui para linear e normalizado.

export type RGB = [number, number, number];

export const KELVIN_MIN = 2700;
export const KELVIN_MAX = 6500;

const clamp = (x: number, a: number, b: number) => Math.min(b, Math.max(a, x));

function srgbToLinear(c: number): number {
  return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

/** Cor do corpo negro em sRGB 0..1 (antes da linearização). */
export function kelvinToSRGB(kelvin: number): RGB {
  const t = clamp(kelvin, 1000, 40000) / 100;
  const r = t <= 66 ? 255 : 329.698727446 * Math.pow(t - 60, -0.1332047592);
  const g = t <= 66 ? 99.4708025861 * Math.log(t) - 161.1195681661 : 288.1221695283 * Math.pow(t - 60, -0.0755148492);
  const b = t >= 66 ? 255 : t <= 19 ? 0 : 138.5177312231 * Math.log(t - 10) - 305.0447927307;
  return [clamp(r, 0, 255) / 255, clamp(g, 0, 255) / 255, clamp(b, 0, 255) / 255];
}

const luminance = (c: RGB) => 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];

/** RGB linear com luminância 1 (a temperatura muda só a cor, não a intensidade). */
export function kelvinToLinearRGB(kelvin: number): RGB {
  const s = kelvinToSRGB(kelvin);
  const lin: RGB = [srgbToLinear(s[0]), srgbToLinear(s[1]), srgbToLinear(s[2])];
  const y = luminance(lin);
  return [lin[0] / y, lin[1] / y, lin[2] / y];
}

/**
 * Multiplicador RGB de um light group: intensidade × cor(T) / cor(T_render).
 * Com T == T_render e intensidade 1, devolve exatamente [1, 1, 1] (LightMix neutro).
 */
export function lightTint(intensity: number, kelvin: number, renderKelvin: number): RGB {
  if (kelvin === renderKelvin) return [intensity, intensity, intensity];
  const a = kelvinToLinearRGB(kelvin);
  const b = kelvinToLinearRGB(renderKelvin);
  const ratio: RGB = [a[0] / b[0], a[1] / b[1], a[2] / b[2]];
  const y = luminance(ratio);
  return [(intensity * ratio[0]) / y, (intensity * ratio[1]) / y, (intensity * ratio[2]) / y];
}

/** Cor de exibição (CSS) de uma temperatura, para o trilho do slider. */
export function kelvinToCss(kelvin: number): string {
  const [r, g, b] = kelvinToSRGB(kelvin);
  return `rgb(${Math.round(r * 255)} ${Math.round(g * 255)} ${Math.round(b * 255)})`;
}
