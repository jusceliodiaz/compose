// Estado da configuração (o que o usuário escolheu). Fonte única para UI, motor e URL.
import type { NormalizedCatalog } from '../catalog/schema';

export interface SlotConfig {
  option: string;
  variant: string | null;
  /** Multiplicador da escala física. */
  scale: number;
  /** Rotação do usuário em graus (somada à default_rotation_deg da opção). */
  rotation: number;
  /** Deslocamento em frações de tile. */
  ox: number;
  oy: number;
}

export interface LightConfig {
  intensity: number;
  kelvin: number;
}

export interface ConfigState {
  cam: string;
  slots: Record<string, SlotConfig>;
  lights: Record<string, LightConfig>;
}

export function defaultState(catalog: NormalizedCatalog, camId?: string): ConfigState {
  const cam = catalog.cameras.find((c) => c.id === camId) ?? catalog.cameras[0]!;
  const slots: Record<string, SlotConfig> = {};
  for (const s of catalog.slots) {
    const opt = s.options.find((o) => o.id === s.defaultOption)!;
    slots[s.id] = { option: opt.id, variant: opt.tintVariants[0]?.id ?? null, scale: 1, rotation: 0, ox: 0, oy: 0 };
  }
  const lights: Record<string, LightConfig> = {};
  for (const g of cam.lightGroups) lights[g.id] = { intensity: g.intensity, kelvin: g.kelvin };
  return { cam: cam.id, slots, lights };
}

type Listener = (state: ConfigState, prev: ConfigState) => void;

export class Store {
  private state: ConfigState;
  private listeners = new Set<Listener>();

  constructor(initial: ConfigState) {
    this.state = initial;
  }

  get(): ConfigState {
    return this.state;
  }

  /** Atualiza de forma imutável e avisa os ouvintes. */
  update(fn: (draft: ConfigState) => void): void {
    const prev = this.state;
    const next = structuredClone(prev);
    fn(next);
    this.state = next;
    for (const l of this.listeners) l(next, prev);
  }

  setSlot(slotId: string, patch: Partial<SlotConfig>): void {
    this.update((d) => {
      const s = d.slots[slotId];
      if (s) Object.assign(s, patch);
    });
  }

  setLight(groupId: string, patch: Partial<LightConfig>): void {
    this.update((d) => {
      const l = d.lights[groupId];
      if (l) Object.assign(l, patch);
    });
  }

  subscribe(l: Listener): () => void {
    this.listeners.add(l);
    return () => this.listeners.delete(l);
  }
}

/** Orçamento: área × preço por slot, com total. */
export interface BudgetLine {
  slotId: string;
  slotName: string;
  optionName: string;
  area: number;
  unitPrice: number;
  currency: string;
  total: number;
}

export function budget(catalog: NormalizedCatalog, state: ConfigState): { lines: BudgetLine[]; total: number; currency: string } {
  const lines: BudgetLine[] = [];
  for (const s of catalog.slots) {
    const cfg = state.slots[s.id];
    const opt = s.options.find((o) => o.id === cfg?.option);
    if (!opt?.price || s.areaM2 === null) continue;
    lines.push({
      slotId: s.id,
      slotName: s.name,
      optionName: opt.name,
      area: s.areaM2,
      unitPrice: opt.price.value,
      currency: opt.price.currency,
      total: Math.round(s.areaM2 * opt.price.value * 100) / 100,
    });
  }
  const total = Math.round(lines.reduce((a, l) => a + l.total, 0) * 100) / 100;
  return { lines, total, currency: lines[0]?.currency ?? 'BRL' };
}
