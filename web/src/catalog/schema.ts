// Tipos do catálogo (schema v2, docs Seção 6.2) + validação + normalização com fallbacks (Seção 6.3).
// O resto do app só enxerga o formato normalizado (NormalizedCatalog), nunca o JSON cru.

export type Vec2 = [number, number];
export type Vec3 = [number, number, number];
export type Channel = 'r' | 'g' | 'b';
export type ToneOperator = 'standard' | 'aces' | 'agx' | 'lut';

/** Curva de tone mapping tabelada (renders que já vieram com tone mapping; ver tools/tone_curve.py). */
export interface ToneLut {
  log2_min: number;
  log2_max: number;
  /** inclinação em log-log abaixo de log2_min */
  low_slope: number;
  values: number[];
}

export interface RawTintVariant { id: string; name: string; tint: Vec3 }
export interface RawPrice { value: number; unit: string; currency: string }

export interface RawOption {
  id: string;
  name: string;
  thumbnail?: string;
  diffuse_map?: string;
  albedo_color?: Vec3;
  default_tiling?: Vec2;
  texture_size_m?: Vec2;
  default_rotation_deg?: number;
  tint_variants?: RawTintVariant[];
  gloss_keep?: number;
  sku?: string;
  price?: RawPrice;
  finish?: string;
  is_test?: boolean;
  /** Mostra o material do próprio render (o slot não é alterado). */
  keep_original?: boolean;
}

export interface RawSlot {
  id: string;
  name: string;
  mask?: string;
  mask_ref?: { file: number; channel: Channel };
  default_texture: string;
  allow_user_transform?: { scale?: Vec2; rotation?: boolean; offset?: boolean };
  gloss_keep?: number;
  area_m2?: number;
  options: RawOption[];
}

export interface RawLightGroup {
  id: string;
  name: string;
  pass: string;
  intensity?: number;
  kelvin?: number;
  range?: Vec2;
}

export interface RawCatalog {
  schema_version?: number;
  project_id: string;
  project_name?: string;
  camera: string;
  camera_name?: string;
  resolution?: { view?: Vec2; export?: Vec2 };
  tone_mapping?: { operator?: ToneOperator; exposure?: number; lut?: ToneLut };
  base_passes: {
    beauty: string;
    beauty_linear?: string;
    uv_map?: string;
    uv_hi?: string;
    uv_lo?: string;
    uv_encoding?: string;
    uv_range?: [number, number, number, number];
    shadow_ao?: string;
    diffuse_light?: string;
    glossy?: string;
    masks_packed?: { file: string; channels: Partial<Record<Channel, string>> }[];
    export_passes_prefix?: string;
  };
  light_groups?: RawLightGroup[];
  configurable_slots: RawSlot[];
}

// --- Formato normalizado ---------------------------------------------------------------

export interface MaterialOption {
  id: string;
  name: string;
  thumbnail: string | null;
  /** URL da textura de albedo; null = cor sólida (albedoColor). */
  diffuseMap: string | null;
  /** Cor linear para materiais sem textura. */
  albedoColor: Vec3;
  /** Tiling físico: 1 / texture_size_m, ou default_tiling (fallback). */
  tiling: Vec2;
  sizeM: Vec2 | null;
  defaultRotationDeg: number;
  tintVariants: RawTintVariant[];
  glossKeep: number;
  sku: string | null;
  price: RawPrice | null;
  finish: string;
  isTest: boolean;
  keepOriginal: boolean;
}

export interface Slot {
  id: string;
  name: string;
  maskFile: string;
  channel: Channel;
  defaultOption: string;
  scaleRange: Vec2;
  allowRotation: boolean;
  allowOffset: boolean;
  areaM2: number | null;
  options: MaterialOption[];
}

export interface LightGroup {
  id: string;
  name: string;
  pass: string;
  intensity: number;
  /** Temperatura com que a luz foi renderizada (referência neutra do slider). */
  kelvin: number;
  range: Vec2;
}

export interface CameraPasses {
  beautyDisplay: string;
  beautyLinear: string | null;
  uv:
    | { kind: 'u16_hilo'; hi: string; lo: string; range: [number, number, number, number] }
    | { kind: 'u8'; map: string; range: [number, number, number, number] };
  diffuseLight: string | null;
  glossy: string | null;
  shadowAO: string | null;
  maskFiles: string[];
  exportPrefix: string | null;
}

export interface CameraDef {
  id: string;
  name: string;
  viewResolution: Vec2;
  exportResolution: Vec2;
  tone: { operator: ToneOperator; exposure: number; lut: ToneLut | null };
  passes: CameraPasses;
  lightGroups: LightGroup[];
}

export interface NormalizedCatalog {
  projectId: string;
  projectName: string;
  cameras: CameraDef[];
  slots: Slot[];
  /** Avisos de fallback (modo simplificado etc.), para o console e a UI. */
  notes: string[];
}

export class CatalogError extends Error {
  constructor(public readonly problems: string[]) {
    super(`Catálogo inválido:\n- ${problems.join('\n- ')}`);
    this.name = 'CatalogError';
  }
}

export const MAX_SLOTS = 3;
export const MAX_LIGHT_GROUPS = 4;
export const DEFAULT_GLOSS_KEEP = 0.6;
export const MAX_TONE_LUT = 128;

const isNum = (x: unknown): x is number => typeof x === 'number' && Number.isFinite(x);
const isVec = (x: unknown, n: number): boolean => Array.isArray(x) && x.length === n && x.every(isNum);

/** Resolve caminhos do catálogo contra a base (ex.: import.meta.env.BASE_URL). */
export function resolveUrl(base: string, path: string): string {
  if (/^(https?:|data:|blob:|\/)/.test(path)) return path;
  return base.replace(/\/?$/, '/') + path;
}

export function normalizeCatalog(raw: unknown, base = '/'): NormalizedCatalog {
  const p: string[] = [];
  const notes: string[] = [];
  const c = raw as RawCatalog;
  if (!c || typeof c !== 'object') throw new CatalogError(['o JSON não é um objeto']);
  if (c.schema_version !== undefined && c.schema_version !== 2 && c.schema_version !== 1) {
    p.push(`schema_version ${c.schema_version} não suportado`);
  }
  if (!c.project_id) p.push('project_id ausente');
  if (!c.camera) p.push('camera ausente');
  const bp = c.base_passes;
  if (!bp?.beauty) p.push('base_passes.beauty ausente');
  if (!Array.isArray(c.configurable_slots)) p.push('configurable_slots ausente');
  if (p.length) throw new CatalogError(p);

  const url = (s: string) => resolveUrl(base, s);

  // UV: hi/lo (16-bit) → fallback uv_map 8-bit
  let uv: CameraPasses['uv'];
  const range = (isVec(bp.uv_range, 4) ? bp.uv_range : [0, 0, 1, 1]) as [number, number, number, number];
  if (bp.uv_hi && bp.uv_lo) {
    if (!isVec(bp.uv_range, 4)) p.push('uv_range obrigatório com uv_hi/uv_lo');
    uv = { kind: 'u16_hilo', hi: url(bp.uv_hi), lo: url(bp.uv_lo), range };
  } else if (bp.uv_map) {
    notes.push('UV em 8 bits (uv_map): a textura pode mostrar degraus; gere uv_hi/uv_lo com o pack_uv.py.');
    uv = { kind: 'u8', map: url(bp.uv_map), range };
  } else {
    p.push('sem UV: informe uv_hi/uv_lo ou uv_map');
    uv = { kind: 'u8', map: '', range };
  }

  if (!bp.diffuse_light) {
    if (!bp.shadow_ao) p.push('sem diffuse_light e sem shadow_ao');
    notes.push('Modo simplificado: sem diffuse_light, o material é iluminado por shadow_ao × cor média do beauty.');
  }

  // Máscaras: masks_packed[] + mask_ref → fallback mask individual (canal R)
  const maskFiles: string[] = (bp.masks_packed ?? []).map((m) => url(m.file));
  const slots: Slot[] = [];
  const usedChannels = new Set<string>();
  for (const s of c.configurable_slots) {
    let maskFile: string;
    let channel: Channel;
    if (s.mask_ref && maskFiles[s.mask_ref.file]) {
      maskFile = maskFiles[s.mask_ref.file]!;
      channel = s.mask_ref.channel;
    } else if (s.mask) {
      maskFile = url(s.mask);
      channel = 'r';
      if (!maskFiles.includes(maskFile)) maskFiles.push(maskFile);
    } else {
      p.push(`slot ${s.id}: sem mask_ref nem mask`);
      continue;
    }
    const key = `${maskFile}#${channel}`;
    if (usedChannels.has(key)) p.push(`slot ${s.id}: canal de máscara repetido (${channel})`);
    usedChannels.add(key);

    const slotGloss = isNum(s.gloss_keep) ? s.gloss_keep : DEFAULT_GLOSS_KEEP;
    const options: MaterialOption[] = (s.options ?? []).map((o) => {
      if (!o.diffuse_map && !isVec(o.albedo_color, 3) && !o.keep_original) p.push(`${s.id}/${o.id}: sem diffuse_map nem albedo_color`);
      const size = isVec(o.texture_size_m, 2) ? (o.texture_size_m as Vec2) : null;
      const tiling: Vec2 = size
        ? [1 / size[0], 1 / size[1]]
        : isVec(o.default_tiling, 2)
          ? (o.default_tiling as Vec2)
          : [1, 1];
      return {
        id: o.id,
        name: o.name,
        thumbnail: o.thumbnail ? url(o.thumbnail) : null,
        diffuseMap: o.diffuse_map ? url(o.diffuse_map) : null,
        albedoColor: isVec(o.albedo_color, 3) ? (o.albedo_color as Vec3) : [1, 1, 1],
        tiling,
        sizeM: size,
        defaultRotationDeg: isNum(o.default_rotation_deg) ? o.default_rotation_deg : 0,
        tintVariants: o.tint_variants ?? [],
        glossKeep: isNum(o.gloss_keep) ? o.gloss_keep : slotGloss,
        sku: o.sku ?? null,
        price: o.price ?? null,
        finish: o.finish ?? '',
        isTest: o.is_test === true,
        keepOriginal: o.keep_original === true,
      };
    });
    if (!options.some((o) => o.id === s.default_texture)) {
      p.push(`slot ${s.id}: default_texture '${s.default_texture}' não existe nas opções`);
    }
    const aut = s.allow_user_transform;
    slots.push({
      id: s.id,
      name: s.name,
      maskFile,
      channel,
      defaultOption: s.default_texture,
      scaleRange: isVec(aut?.scale, 2) ? (aut!.scale as Vec2) : [0.5, 2.0],
      allowRotation: aut?.rotation ?? true,
      allowOffset: aut?.offset ?? true,
      areaM2: isNum(s.area_m2) ? s.area_m2 : null,
      options,
    });
  }
  if (slots.length > MAX_SLOTS) p.push(`no máximo ${MAX_SLOTS} slots por câmera (vieram ${slots.length})`);
  if (maskFiles.length > 2) p.push('no máximo 2 arquivos de máscara por câmera');

  const lgs = (c.light_groups ?? []).map<LightGroup>((g) => ({
    id: g.id,
    name: g.name,
    pass: url(g.pass),
    intensity: isNum(g.intensity) ? g.intensity : 1,
    kelvin: isNum(g.kelvin) ? g.kelvin : 6500,
    range: isVec(g.range, 2) ? (g.range as Vec2) : [0, 2],
  }));
  if (lgs.length > MAX_LIGHT_GROUPS) p.push(`no máximo ${MAX_LIGHT_GROUPS} light groups`);
  if (c.tone_mapping?.operator === 'lut') {
    const l = c.tone_mapping.lut;
    if (!l || !Array.isArray(l.values) || l.values.length < 2 || l.values.length > MAX_TONE_LUT) {
      p.push(`tone_mapping.lut precisa de 2–${MAX_TONE_LUT} valores`);
    }
  }

  if (p.length) throw new CatalogError(p);

  const view: Vec2 = isVec(c.resolution?.view, 2) ? (c.resolution!.view as Vec2) : [1920, 1080];
  const camera: CameraDef = {
    id: c.camera,
    name: c.camera_name ?? c.camera,
    viewResolution: view,
    exportResolution: isVec(c.resolution?.export, 2) ? (c.resolution!.export as Vec2) : view,
    tone: {
      operator: c.tone_mapping?.operator ?? 'agx',
      exposure: isNum(c.tone_mapping?.exposure) ? c.tone_mapping!.exposure! : 1,
      lut: c.tone_mapping?.lut ?? null,
    },
    passes: {
      beautyDisplay: url(bp.beauty),
      beautyLinear: bp.beauty_linear ? url(bp.beauty_linear) : null,
      uv,
      diffuseLight: bp.diffuse_light ? url(bp.diffuse_light) : null,
      glossy: bp.glossy ? url(bp.glossy) : null,
      shadowAO: bp.shadow_ao ? url(bp.shadow_ao) : null,
      maskFiles,
      exportPrefix: bp.export_passes_prefix ? url(bp.export_passes_prefix) : null,
    },
    lightGroups: lgs,
  };

  return {
    projectId: c.project_id,
    projectName: c.project_name ?? c.project_id,
    cameras: [camera],
    slots,
    notes,
  };
}
