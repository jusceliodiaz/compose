// Carregamento das texturas com as configurações obrigatórias do CLAUDE.md §4 (regras 1–3).
import * as THREE from 'three';
import { EXRLoader } from 'three/addons/loaders/EXRLoader.js';

const textureLoader = new THREE.TextureLoader();

/** Passes de DADOS (UV, máscaras, AO): sem cor, sem filtro, sem mipmap. flipY = true (padrão). */
export async function loadData(url: string): Promise<THREE.Texture> {
  const t = await textureLoader.loadAsync(url);
  t.colorSpace = THREE.NoColorSpace;
  t.minFilter = THREE.NearestFilter;
  t.magFilter = THREE.NearestFilter;
  t.generateMipmaps = false;
  t.needsUpdate = true;
  return t;
}

/**
 * Passes de LUZ (HDR linear): EXR half-float, LinearFilter, sem mipmaps.
 * O EXRLoader grava as linhas de baixo para cima e usa flipY = false — a orientação final é a
 * mesma dos PNGs com flipY = true (provado no teste e2e de orientação).
 */
export async function loadHDR(url: string): Promise<THREE.DataTexture> {
  const t = (await new EXRLoader().setDataType(THREE.HalfFloatType).loadAsync(url)) as THREE.DataTexture;
  t.colorSpace = THREE.LinearSRGBColorSpace;
  t.minFilter = THREE.LinearFilter;
  t.magFilter = THREE.LinearFilter;
  t.generateMipmaps = false;
  t.needsUpdate = true;
  return t;
}

/** Albedo de MATERIAL: sRGB, REPEAT, mipmaps e anisotropia máxima. */
export async function loadAlbedo(url: string, maxAnisotropy: number): Promise<THREE.Texture> {
  const t = await textureLoader.loadAsync(url);
  return configureAlbedo(t, maxAnisotropy);
}

export function configureAlbedo<T extends THREE.Texture>(t: T, maxAnisotropy: number): T {
  t.colorSpace = THREE.SRGBColorSpace;
  t.wrapS = THREE.RepeatWrapping;
  t.wrapT = THREE.RepeatWrapping;
  t.generateMipmaps = true;
  t.minFilter = THREE.LinearMipmapLinearFilter;
  t.magFilter = THREE.LinearFilter;
  t.anisotropy = maxAnisotropy;
  t.needsUpdate = true;
  return t;
}

/** Imagem de exibição (beauty.webp, sRGB) — usada como fallback de beauty sem EXR linear. */
export async function loadDisplay(url: string): Promise<THREE.Texture> {
  const t = await textureLoader.loadAsync(url);
  t.colorSpace = THREE.SRGBColorSpace;
  t.minFilter = THREE.LinearFilter;
  t.magFilter = THREE.LinearFilter;
  t.generateMipmaps = false;
  t.needsUpdate = true;
  return t;
}

/** Textura 1×1 (dado): cor neutra para samplers não usados. */
export function solidData(rgba: [number, number, number, number]): THREE.DataTexture {
  const t = new THREE.DataTexture(new Uint8Array(rgba), 1, 1, THREE.RGBAFormat);
  t.colorSpace = THREE.NoColorSpace;
  t.needsUpdate = true;
  return t;
}

/** Albedo branco 1×1 para materiais de cor sólida (a cor vai no tint). */
export function whiteAlbedo(): THREE.DataTexture {
  const t = new THREE.DataTexture(new Uint8Array([255, 255, 255, 255]), 1, 1, THREE.RGBAFormat);
  t.colorSpace = THREE.SRGBColorSpace;
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.needsUpdate = true;
  return t;
}

/** Cor média de um DataTexture half-float (amostrado em grade), em linear. */
export function meanColor(t: THREE.DataTexture, step = 16): [number, number, number] {
  const img = t.image as { data: Uint16Array | Float32Array; width: number; height: number };
  const ch = img.data.length / (img.width * img.height);
  const half = img.data instanceof Uint16Array;
  const sum = [0, 0, 0];
  let n = 0;
  for (let y = 0; y < img.height; y += step) {
    for (let x = 0; x < img.width; x += step) {
      const i = (y * img.width + x) * ch;
      for (let c = 0; c < 3; c++) {
        const v = img.data[i + c]!;
        sum[c]! += half ? THREE.DataUtils.fromHalfFloat(v) : v;
      }
      n++;
    }
  }
  return [sum[0]! / n, sum[1]! / n, sum[2]! / n];
}

/** Bytes aproximados de uma textura na GPU (para a estimativa de memória). */
export function textureBytes(t: THREE.Texture): number {
  const img = t.image as { width?: number; height?: number } | null;
  if (!img?.width || !img.height) return 0;
  const bpp = t.type === THREE.HalfFloatType ? 8 : t.type === THREE.FloatType ? 16 : 4;
  return img.width * img.height * bpp * (t.generateMipmaps ? 4 / 3 : 1);
}
