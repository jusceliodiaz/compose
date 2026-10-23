// Panorama 360°: matemática da vista (espelho em JS do panorama.frag.glsl, para o clique e os testes).
// Convenção: a câmera olha para −Z, X para a direita, Y para cima. yaw > 0 vira para a direita,
// pitch > 0 olha para cima. O centro da imagem equirretangular (u = 0,5) é a frente.

export interface PanoView {
  /** Radianos. */
  yaw: number;
  /** Radianos, limitado a ±PITCH_LIMIT. */
  pitch: number;
  /** Campo de visão VERTICAL, em graus. */
  fov: number;
}

export const FOV_RANGE: readonly [number, number] = [35, 100];
export const PITCH_LIMIT = (85 * Math.PI) / 180;

export function clampView(v: PanoView): PanoView {
  const tau = Math.PI * 2;
  return {
    yaw: ((((v.yaw + Math.PI) % tau) + tau) % tau) - Math.PI,
    pitch: Math.min(PITCH_LIMIT, Math.max(-PITCH_LIMIT, v.pitch)),
    fov: Math.min(FOV_RANGE[1], Math.max(FOV_RANGE[0], v.fov)),
  };
}

/** Direção (mundo) → (u, v) equirretangular, v = 0 EMBAIXO (como as texturas do WebGL). */
export function dirToEquirect(x: number, y: number, z: number): [number, number] {
  const len = Math.hypot(x, y, z) || 1;
  const u = 0.5 + Math.atan2(x, -z) / (2 * Math.PI);
  const v = 0.5 + Math.asin(Math.min(1, Math.max(-1, y / len))) / Math.PI;
  return [u - Math.floor(u), v];
}

/**
 * Ponto da tela → (u, v) na imagem equirretangular, ambos com origem no canto SUPERIOR esquerdo
 * (o mesmo referencial do Picker). (sx, sy) em [0, 1] a partir do canto superior esquerdo da tela.
 */
export function screenToEquirect(view: PanoView, sx: number, sy: number, aspect: number): [number, number] {
  const t = Math.tan(((view.fov * Math.PI) / 180) / 2);
  let x = (sx * 2 - 1) * t * aspect;
  let y = (1 - sy * 2) * t;
  let z = -1;
  // pitch: rotação em X
  const cp = Math.cos(view.pitch);
  const sp = Math.sin(view.pitch);
  [y, z] = [y * cp - z * sp, y * sp + z * cp];
  // yaw: rotação em Y
  const cy = Math.cos(view.yaw);
  const sy2 = Math.sin(view.yaw);
  [x, z] = [x * cy - z * sy2, x * sy2 + z * cy];
  const [u, v] = dirToEquirect(x, y, z);
  return [u, 1 - v];
}
