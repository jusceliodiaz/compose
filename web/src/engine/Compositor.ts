// Motor de composição: um quad em tela cheia com o shader de produção, renderizado sob demanda.
import * as THREE from 'three';
import type { CameraDef, MaterialOption, NormalizedCatalog, Slot, Vec2, Vec3 } from '../catalog/schema';
import { lightTint } from '../util/kelvin';
import {
  loadAlbedo,
  loadData,
  loadDisplay,
  loadHDR,
  meanColor,
  solidData,
  textureBytes,
  whiteAlbedo,
} from './loaders';
import fragmentShader from './shaders/composite.frag.glsl?raw';
import vertexShader from './shaders/composite.vert.glsl?raw';

export interface SlotTransform {
  /** Multiplicador sobre a escala física (2 = textura 2× maior). */
  scale: number;
  rotationDeg: number;
  /** Deslocamento em frações de tile. */
  offset: Vec2;
}

export interface LightSetting {
  intensity: number;
  kelvin: number;
}

export enum DebugMode {
  Off = 0,
  UV = 1,
  Masks = 2,
  DiffuseLight = 3,
  Seams = 4,
  Albedo = 5,
}

export interface PassSet {
  beauty: THREE.Texture;
  diffLight: THREE.Texture | null;
  glossy: THREE.Texture | null;
  shadowAO: THREE.Texture | null;
  uvHi: THREE.Texture;
  uvLo: THREE.Texture | null;
  masks: THREE.Texture[];
  lightGroups: THREE.Texture[];
  fallbackLight: Vec3;
  width: number;
  height: number;
}

interface SlotState {
  slot: Slot;
  option: MaterialOption;
  variantId: string | null;
  transform: SlotTransform;
  albedo: THREE.Texture;
  /** Contador de pedidos: uma textura que chega atrasada não sobrescreve a escolha mais nova. */
  req: number;
}

const TONE_OPS = { standard: 0, aces: 1, agx: 2 } as const;
const MAX_SLOTS = 3;
const MAX_LG = 4;

export type ProgressFn = (loaded: number, total: number) => void;

export class Compositor {
  readonly renderer: THREE.WebGLRenderer;
  readonly material: THREE.RawShaderMaterial;
  private readonly scene = new THREE.Scene();
  private readonly camera3 = new THREE.Camera();
  private readonly quad: THREE.Mesh;

  private catalog: NormalizedCatalog | null = null;
  private cam: CameraDef | null = null;
  private passes: PassSet | null = null;
  private slots = new Map<string, SlotState>();
  private lights = new Map<string, LightSetting>();
  private albedoCache = new Map<string, Promise<THREE.Texture>>();
  private readonly white = whiteAlbedo();
  private readonly black = solidData([0, 0, 0, 255]);
  private frame = 0;
  private renderCount = 0;
  /** Chamado depois de cada render (a UI usa para atualizar indicadores). */
  onRender: (() => void) | null = null;

  constructor(canvas: HTMLCanvasElement) {
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: false, preserveDrawingBuffer: false });
    if (!this.renderer.capabilities.isWebGL2) throw new Error('Este navegador não tem WebGL2.');
    this.renderer.outputColorSpace = THREE.LinearSRGBColorSpace; // o shader já converte para sRGB
    this.renderer.toneMapping = THREE.NoToneMapping;
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

    const u = <T>(value: T) => ({ value });
    this.material = new THREE.RawShaderMaterial({
      glslVersion: THREE.GLSL3,
      vertexShader,
      fragmentShader,
      depthTest: false,
      depthWrite: false,
      uniforms: {
        u_beauty: u(this.black), u_diffLight: u(this.black), u_glossy: u(this.black),
        u_shadowAO: u(this.black), u_hasDiffLight: u(true), u_fallbackLight: u(new THREE.Vector3(1, 1, 1)),
        u_uvHi: u(this.black), u_uvLo: u(this.black), u_uvMode: u(0), u_uvRange: u(new THREE.Vector4(0, 0, 1, 1)),
        u_mask0: u(this.black), u_mask1: u(this.black),
        u_slotCount: u(0),
        u_albedo0: u(this.white), u_albedo1: u(this.white), u_albedo2: u(this.white),
        u_tint: u(Array.from({ length: MAX_SLOTS }, () => new THREE.Vector3(1, 1, 1))),
        u_tiling: u(Array.from({ length: MAX_SLOTS }, () => new THREE.Vector2(1, 1))),
        u_rotation: u(new Array<number>(MAX_SLOTS).fill(0)),
        u_offset: u(Array.from({ length: MAX_SLOTS }, () => new THREE.Vector2())),
        u_glossKeep: u(new Array<number>(MAX_SLOTS).fill(0.6)),
        u_slotSelect: u(Array.from({ length: MAX_SLOTS }, () => new THREE.Vector3(1, 0, 0))),
        u_slotMaskFile: u(new Array<number>(MAX_SLOTS).fill(0)),
        u_seamThreshold: u(0.02),
        u_lightCount: u(0), u_lightMixOn: u(false),
        u_lg0: u(this.black), u_lg1: u(this.black), u_lg2: u(this.black), u_lg3: u(this.black),
        u_lightTint: u(Array.from({ length: MAX_LG }, () => new THREE.Vector3(1, 1, 1))),
        u_exposure: u(1), u_toneOp: u(0), u_splitX: u(0), u_debug: u(0),
      },
    });
    this.quad = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), this.material);
    this.quad.frustumCulled = false;
    this.scene.add(this.quad);
  }

  get maxAnisotropy(): number {
    return this.renderer.capabilities.getMaxAnisotropy();
  }

  get maxTextureSize(): number {
    return this.renderer.capabilities.maxTextureSize;
  }

  get currentCamera(): CameraDef | null {
    return this.cam;
  }

  get passSize(): Vec2 {
    return this.passes ? [this.passes.width, this.passes.height] : [1920, 1080];
  }

  get renders(): number {
    return this.renderCount;
  }

  // --- Câmera ----------------------------------------------------------------------

  async setCamera(catalog: NormalizedCatalog, cameraId: string, onProgress?: ProgressFn): Promise<void> {
    const cam = catalog.cameras.find((c) => c.id === cameraId) ?? catalog.cameras[0];
    if (!cam) throw new Error('catálogo sem câmeras');
    const passes = await loadPassSet(cam, (u) => u, onProgress);

    this.disposePasses();
    this.catalog = catalog;
    this.cam = cam;
    this.passes = passes;
    this.bindPasses(passes, cam);

    this.lights.clear();
    for (const g of cam.lightGroups) this.lights.set(g.id, { intensity: g.intensity, kelvin: g.kelvin });
    this.applyLights();

    const U = this.material.uniforms;
    U.u_exposure!.value = cam.tone.exposure;
    U.u_toneOp!.value = TONE_OPS[cam.tone.operator];
    U.u_slotCount!.value = Math.min(catalog.slots.length, MAX_SLOTS);

    this.slots.clear();
    await Promise.all(
      catalog.slots.slice(0, MAX_SLOTS).map(async (slot, i) => {
        const option = slot.options.find((o) => o.id === slot.defaultOption)!;
        const albedo = await this.albedoFor(option);
        const st: SlotState = {
          slot, option, variantId: option.tintVariants[0]?.id ?? null,
          transform: { scale: 1, rotationDeg: 0, offset: [0, 0] }, albedo, req: 0,
        };
        this.slots.set(slot.id, st);
        const ch = { r: 0, g: 1, b: 2 }[slot.channel];
        (U.u_slotSelect!.value as THREE.Vector3[])[i]!.set(ch === 0 ? 1 : 0, ch === 1 ? 1 : 0, ch === 2 ? 1 : 0);
        (U.u_slotMaskFile!.value as number[])[i] = Math.max(0, cam.passes.maskFiles.indexOf(slot.maskFile));
        this.applySlot(slot.id);
      }),
    );
    this.requestRender();
  }

  private bindPasses(p: PassSet, cam: CameraDef): void {
    const U = this.material.uniforms;
    U.u_beauty!.value = p.beauty;
    U.u_diffLight!.value = p.diffLight ?? this.black;
    U.u_glossy!.value = p.glossy ?? this.black;
    U.u_shadowAO!.value = p.shadowAO ?? this.black;
    U.u_hasDiffLight!.value = p.diffLight !== null;
    (U.u_fallbackLight!.value as THREE.Vector3).fromArray(p.fallbackLight);
    U.u_uvHi!.value = p.uvHi;
    U.u_uvLo!.value = p.uvLo ?? this.black;
    U.u_uvMode!.value = cam.passes.uv.kind === 'u16_hilo' ? 0 : 1;
    (U.u_uvRange!.value as THREE.Vector4).fromArray(cam.passes.uv.range);
    U.u_mask0!.value = p.masks[0] ?? this.black;
    U.u_mask1!.value = p.masks[1] ?? this.black;
    U.u_lightCount!.value = Math.min(p.lightGroups.length, MAX_LG);
    for (let i = 0; i < MAX_LG; i++) U[`u_lg${i}`]!.value = p.lightGroups[i] ?? this.black;
  }

  // --- Materiais -------------------------------------------------------------------

  private albedoFor(option: MaterialOption): Promise<THREE.Texture> {
    if (!option.diffuseMap) return Promise.resolve(this.white);
    let p = this.albedoCache.get(option.diffuseMap);
    if (!p) {
      p = loadAlbedo(option.diffuseMap, this.maxAnisotropy);
      p.catch(() => this.albedoCache.delete(option.diffuseMap!));
      this.albedoCache.set(option.diffuseMap, p);
    }
    return p;
  }

  /** Pré-carrega o albedo (ex.: ao passar o mouse sobre a miniatura). */
  preload(option: MaterialOption): void {
    void this.albedoFor(option);
  }

  async setSlotMaterial(slotId: string, optionId: string, variantId?: string | null): Promise<void> {
    const st = this.slots.get(slotId);
    if (!st) throw new Error(`slot desconhecido: ${slotId}`);
    const option = st.slot.options.find((o) => o.id === optionId);
    if (!option) throw new Error(`opção desconhecida: ${slotId}/${optionId}`);
    const token = ++st.req;
    const albedo = await this.albedoFor(option);
    if (token !== st.req) return;
    st.option = option;
    st.albedo = albedo;
    st.variantId =
      variantId && option.tintVariants.some((v) => v.id === variantId) ? variantId : (option.tintVariants[0]?.id ?? null);
    this.applySlot(slotId);
  }

  setVariant(slotId: string, variantId: string | null): void {
    const st = this.slots.get(slotId);
    if (!st) return;
    st.variantId = variantId;
    this.applySlot(slotId);
  }

  setTransform(slotId: string, t: Partial<SlotTransform>): void {
    const st = this.slots.get(slotId);
    if (!st) return;
    const [lo, hi] = st.slot.scaleRange;
    st.transform = { ...st.transform, ...t };
    st.transform.scale = Math.min(hi, Math.max(lo, st.transform.scale));
    this.applySlot(slotId);
  }

  private applySlot(slotId: string): void {
    const st = this.slots.get(slotId);
    if (!st) return;
    const idx = this.catalog!.slots.findIndex((s) => s.id === slotId);
    const U = this.material.uniforms;
    const o = st.option;
    const variant = o.tintVariants.find((v) => v.id === st.variantId);
    const vt = variant?.tint ?? [1, 1, 1];
    const base = o.diffuseMap ? [1, 1, 1] : o.albedoColor;
    (U.u_tint!.value as THREE.Vector3[])[idx]!.set(base[0]! * vt[0], base[1]! * vt[1], base[2]! * vt[2]);
    const s = st.transform.scale;
    (U.u_tiling!.value as THREE.Vector2[])[idx]!.set(o.tiling[0] / s, o.tiling[1] / s);
    (U.u_rotation!.value as number[])[idx] = THREE.MathUtils.degToRad(o.defaultRotationDeg + st.transform.rotationDeg);
    (U.u_offset!.value as THREE.Vector2[])[idx]!.set(st.transform.offset[0], st.transform.offset[1]);
    (U.u_glossKeep!.value as number[])[idx] = o.glossKeep;
    U[`u_albedo${idx}`]!.value = st.albedo;
    this.requestRender();
  }

  // --- Luz e saída -----------------------------------------------------------------

  setLight(groupId: string, s: Partial<LightSetting>): void {
    const cur = this.lights.get(groupId);
    if (!cur) return;
    this.lights.set(groupId, { ...cur, ...s });
    this.applyLights();
    this.requestRender();
  }

  private applyLights(): void {
    const groups = this.cam?.lightGroups ?? [];
    const U = this.material.uniforms;
    let neutral = true;
    groups.slice(0, MAX_LG).forEach((g, i) => {
      const s = this.lights.get(g.id)!;
      const tint = lightTint(s.intensity, s.kelvin, g.kelvin);
      if (tint.some((c) => Math.abs(c - 1) > 1e-6)) neutral = false;
      (U.u_lightTint!.value as THREE.Vector3[])[i]!.fromArray(tint);
    });
    // LightMix neutro → usa o beauty direto (identidade exata, sem erro de soma dos grupos)
    U.u_lightMixOn!.value = !neutral && groups.length > 0;
  }

  setExposure(exposure: number): void {
    this.material.uniforms.u_exposure!.value = exposure;
    this.requestRender();
  }

  /** Cortina antes/depois: fração horizontal [0, 1] que mostra o render original. */
  setSplit(x: number): void {
    this.material.uniforms.u_splitX!.value = Math.min(1, Math.max(0, x));
    this.requestRender();
  }

  setDebug(mode: DebugMode): void {
    this.material.uniforms.u_debug!.value = mode;
    this.requestRender();
  }

  get debugMode(): DebugMode {
    return this.material.uniforms.u_debug!.value as DebugMode;
  }

  /** Ajusta o canvas ao tamanho exibido (CSS px). */
  setSize(cssWidth: number, cssHeight: number): void {
    this.renderer.setSize(Math.max(1, Math.round(cssWidth)), Math.max(1, Math.round(cssHeight)), false);
    this.requestRender();
  }

  // --- Render sob demanda ----------------------------------------------------------

  /** Agenda UM render no próximo frame (várias mudanças no mesmo frame → um render só). */
  requestRender(): void {
    if (this.frame) return;
    this.frame = requestAnimationFrame(() => {
      this.frame = 0;
      this.render();
    });
  }

  render(): void {
    if (!this.passes) return;
    this.renderer.setRenderTarget(null);
    this.renderer.render(this.scene, this.camera3);
    this.renderCount++;
    this.onRender?.();
  }

  /**
   * Renderiza num WebGLRenderTarget e devolve os pixels RGBA 8-bit, linhas de CIMA para baixo.
   * `passes` permite renderizar com outro conjunto (ex.: passes 4K de export).
   */
  renderToPixels(width: number, height: number, passes?: PassSet): Uint8Array {
    const max = this.maxTextureSize;
    if (width > max || height > max) throw new Error(`resolução ${width}×${height} acima do limite da GPU (${max})`);
    const rt = new THREE.WebGLRenderTarget(width, height, {
      type: THREE.UnsignedByteType,
      format: THREE.RGBAFormat,
      depthBuffer: false,
      generateMipmaps: false,
    });
    const prev = this.passes;
    try {
      if (passes && this.cam) this.bindPasses(passes, this.cam);
      this.renderer.setRenderTarget(rt);
      this.renderer.render(this.scene, this.camera3);
      const buf = new Uint8Array(width * height * 4);
      this.renderer.readRenderTargetPixels(rt, 0, 0, width, height, buf);
      // WebGL lê de baixo para cima → inverte as linhas
      const row = width * 4;
      const out = new Uint8Array(buf.length);
      for (let y = 0; y < height; y++) out.set(buf.subarray((height - 1 - y) * row, (height - y) * row), y * row);
      return out;
    } finally {
      this.renderer.setRenderTarget(null);
      if (passes && prev && this.cam) this.bindPasses(prev, this.cam);
      rt.dispose();
    }
  }

  getSlotState(slotId: string): Readonly<SlotState> | undefined {
    return this.slots.get(slotId);
  }

  getLight(groupId: string): LightSetting | undefined {
    return this.lights.get(groupId);
  }

  /** Estimativa de memória de GPU das texturas carregadas (MB). */
  async gpuMemoryMB(): Promise<number> {
    let bytes = 0;
    const p = this.passes;
    if (p) {
      for (const t of [p.beauty, p.diffLight, p.glossy, p.shadowAO, p.uvHi, p.uvLo, ...p.masks, ...p.lightGroups]) {
        if (t) bytes += textureBytes(t);
      }
    }
    for (const t of await Promise.allSettled(this.albedoCache.values())) {
      if (t.status === 'fulfilled') bytes += textureBytes(t.value);
    }
    return bytes / (1024 * 1024);
  }

  private disposePasses(): void {
    if (this.passes) disposePassSet(this.passes);
    this.passes = null;
  }

  dispose(): void {
    if (this.frame) cancelAnimationFrame(this.frame);
    this.disposePasses();
    for (const p of this.albedoCache.values()) void p.then((t) => t.dispose()).catch(() => {});
    this.albedoCache.clear();
    this.white.dispose();
    this.black.dispose();
    this.material.dispose();
    this.quad.geometry.dispose();
    this.renderer.dispose();
  }

}

// --- Conjunto de passes ------------------------------------------------------------------

/**
 * Carrega todos os passes de uma câmera em paralelo.
 * `mapUrl` troca cada URL (usado pelo export com `export_passes_prefix`).
 */
export async function loadPassSet(cam: CameraDef, mapUrl: (u: string) => string, onProgress?: ProgressFn): Promise<PassSet> {
  const P = cam.passes;
  let done = 0;
  const jobs: Promise<unknown>[] = [];
  const track = <T>(p: Promise<T>): Promise<T> => {
    jobs.push(p);
    void p.then(() => onProgress?.(++done, jobs.length), () => {});
    return p;
  };
  const opt = <T>(url: string | null, fn: (u: string) => Promise<T>) => (url ? track(fn(mapUrl(url))) : Promise.resolve(null));

  const beautyP = P.beautyLinear ? track(loadHDR(mapUrl(P.beautyLinear))) : track(loadDisplay(mapUrl(P.beautyDisplay)));
  const diffP = opt(P.diffuseLight, loadHDR);
  const glossP = opt(P.glossy, loadHDR);
  const aoP = opt(P.diffuseLight ? null : P.shadowAO, loadData);
  const uvHiP = track(loadData(mapUrl(P.uv.kind === 'u16_hilo' ? P.uv.hi : P.uv.map)));
  const uvLoP = P.uv.kind === 'u16_hilo' ? track(loadData(mapUrl(P.uv.lo))) : Promise.resolve(null);
  const masksP = Promise.all(P.maskFiles.map((m) => track(loadData(mapUrl(m)))));
  const lgP = Promise.all(cam.lightGroups.map((g) => track(loadHDR(mapUrl(g.pass)))));
  onProgress?.(0, jobs.length);

  const results = await Promise.allSettled([beautyP, diffP, glossP, aoP, uvHiP, uvLoP, masksP, lgP]);
  const failed = results.find((r) => r.status === 'rejected') as PromiseRejectedResult | undefined;
  if (failed) {
    // libera o que chegou a carregar antes de propagar o erro
    for (const r of results) {
      if (r.status !== 'fulfilled' || !r.value) continue;
      const v = r.value as THREE.Texture | THREE.Texture[];
      (Array.isArray(v) ? v : [v]).forEach((t) => t.dispose());
    }
    throw failed.reason instanceof Error ? failed.reason : new Error(String(failed.reason));
  }
  const [beauty, diffLight, glossy, shadowAO, uvHi, uvLo, masks, lightGroups] = await Promise.all([
    beautyP, diffP, glossP, aoP, uvHiP, uvLoP, masksP, lgP,
  ]);

  let fallbackLight: Vec3 = [1, 1, 1];
  if (!diffLight) {
    fallbackLight = beauty instanceof THREE.DataTexture ? meanColor(beauty) : [0.5, 0.5, 0.5];
    console.info('[compositor] modo simplificado: sem diffuse_light, usando shadow_ao × cor média do beauty', fallbackLight);
  }
  const img = uvHi.image as { width: number; height: number };
  return {
    beauty, diffLight, glossy, shadowAO, uvHi, uvLo, masks, lightGroups, fallbackLight,
    width: img.width, height: img.height,
  };
}

export function disposePassSet(p: PassSet): void {
  for (const t of [p.beauty, p.diffLight, p.glossy, p.shadowAO, p.uvHi, p.uvLo, ...p.masks, ...p.lightGroups]) {
    t?.dispose();
  }
}
