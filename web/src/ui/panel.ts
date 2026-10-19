// Painel de inspeção: superfície → acabamento → variantes → ajuste → iluminação → orçamento.
import type { MaterialOption, NormalizedCatalog, Slot } from '../catalog/schema';
import { budget, type ConfigState, type Store } from '../state/store';
import { kelvinBounds } from '../state/urlState';
import { kelvinToCss } from '../util/kelvin';
import { h, icon, ICONS, money, num } from './dom';
import { slider, type Slider } from './slider';

export interface PanelEvents {
  /** Pré-carrega o albedo ao passar o mouse/focar a miniatura. */
  preload(slotId: string, option: MaterialOption): void;
}

const srgb = (c: number) => (c <= 0.0031308 ? c * 12.92 : 1.055 * Math.pow(c, 1 / 2.4) - 0.055);
const linToCss = (c: readonly number[]) =>
  `rgb(${c.map((x) => Math.round(Math.min(1, Math.max(0, srgb(x))) * 255)).join(' ')})`;

export class Panel {
  readonly el: HTMLElement;
  private activeSlot: string;
  private body: HTMLElement;
  private updaters: ((s: ConfigState) => void)[] = [];

  constructor(
    private readonly catalog: NormalizedCatalog,
    private readonly store: Store,
    private readonly events: PanelEvents,
  ) {
    this.activeSlot = catalog.slots[0]?.id ?? '';
    this.body = h('div', { class: 'insp-body' });
    const toggle = h(
      'button',
      {
        class: 'insp-toggle',
        type: 'button',
        'aria-expanded': 'true',
        'aria-controls': 'inspector-body',
        onclick: () => {
          const open = this.el.classList.toggle('is-collapsed') === false;
          toggle.setAttribute('aria-expanded', String(open));
        },
      },
      h('span', { class: 'insp-grab', 'aria-hidden': 'true' }),
      h('span', { class: 'insp-toggle-label' }, 'Personalizar'),
      icon(ICONS.chevron, 18),
    );
    this.body.id = 'inspector-body';
    this.el = h('aside', { class: 'inspector', 'aria-label': 'Personalização' }, toggle, this.body);
    this.build();
    store.subscribe((s, prev) => {
      if (s.slots[this.activeSlot]?.option !== prev.slots[this.activeSlot]?.option) this.build();
      else this.updaters.forEach((u) => u(s));
    });
  }

  get slotId(): string {
    return this.activeSlot;
  }

  private get slot(): Slot {
    return this.catalog.slots.find((s) => s.id === this.activeSlot)!;
  }

  /** (Re)constrói o conteúdo — só quando muda o slot ou a opção (o resto é atualizado no lugar). */
  build(): void {
    const scroll = this.body.scrollTop;
    this.updaters = [];
    const st = this.store.get();
    this.body.replaceChildren(
      this.sectionSurfaces(),
      this.sectionMaterials(st),
      this.sectionTransform(st),
      this.sectionLights(st),
      this.sectionBudget(),
    );
    this.updaters.forEach((u) => u(st));
    this.body.scrollTop = scroll;
  }

  private section(n: number, title: string, ...content: (Node | null)[]): HTMLElement {
    return h(
      'section',
      { class: 'insp-sec', style: `--i:${n}` },
      h('h2', { class: 'sec-title' }, h('span', { class: 'sec-num' }, String(n).padStart(2, '0')), title),
      ...content,
    );
  }

  // 01 — Superfícies (slots)
  private sectionSurfaces(): HTMLElement {
    const tabs = h('div', { class: 'slot-tabs', role: 'tablist', 'aria-label': 'Superfícies' });
    for (const s of this.catalog.slots) {
      const on = s.id === this.activeSlot;
      tabs.append(
        h(
          'button',
          {
            class: `slot-tab${on ? ' is-active' : ''}`,
            role: 'tab',
            type: 'button',
            'aria-selected': String(on),
            onclick: () => {
              this.activeSlot = s.id;
              this.build();
            },
          },
          icon(ICONS.layers, 16),
          h('span', { class: 'slot-tab-name' }, s.name),
          s.areaM2 !== null ? h('span', { class: 'slot-tab-meta' }, `${num(s.areaM2, 1)} m²`) : null,
        ),
      );
    }
    return this.section(1, 'Superfície', tabs);
  }

  // 02 — Acabamento (materiais + detalhe + variantes)
  private sectionMaterials(st: ConfigState): HTMLElement {
    const slot = this.slot;
    const cfg = st.slots[slot.id]!;
    const grid = h('div', { class: 'mat-grid', role: 'radiogroup', 'aria-label': `Acabamentos de ${slot.name}` });
    for (const o of slot.options.filter((x) => !x.isTest)) {
      const on = o.id === cfg.option;
      const thumb = o.thumbnail
        ? h('img', { class: 'mat-thumb', src: o.thumbnail, alt: '', loading: 'lazy', decoding: 'async', width: 256, height: 256 })
        : h('span', { class: 'mat-thumb mat-thumb--solid', style: `background:${linToCss(o.albedoColor)}` });
      const card = h(
        'button',
        {
          class: `mat-card${on ? ' is-active' : ''}`,
          type: 'button',
          role: 'radio',
          'aria-checked': String(on),
          onclick: () => this.store.setSlot(slot.id, { option: o.id, variant: o.tintVariants[0]?.id ?? null }),
          onpointerenter: () => this.events.preload(slot.id, o),
          onfocus: () => this.events.preload(slot.id, o),
        },
        h('span', { class: 'mat-media' }, thumb, on ? h('span', { class: 'mat-check' }, icon(ICONS.check, 14)) : null),
        h('span', { class: 'mat-name' }, o.name),
        h('span', { class: 'mat-price' }, o.price ? `${money(o.price.value, o.price.currency)}/m²` : '—'),
      );
      grid.append(card);
    }

    const opt = slot.options.find((o) => o.id === cfg.option)!;
    const detail = h(
      'div',
      { class: 'mat-detail' },
      h('p', { class: 'mat-eyebrow' }, opt.isTest ? 'Material de teste' : 'Selecionado'),
      h('h3', { class: 'mat-title' }, opt.name),
      opt.finish ? h('p', { class: 'mat-finish' }, opt.finish) : null,
      h(
        'dl',
        { class: 'mat-specs' },
        opt.sizeM ? [h('dt', {}, 'Módulo'), h('dd', {}, `${num(opt.sizeM[0])} × ${num(opt.sizeM[1])} m`)] : null,
        opt.sku ? [h('dt', {}, 'SKU'), h('dd', {}, opt.sku)] : null,
        [h('dt', {}, 'Reflexo'), h('dd', {}, `${Math.round(opt.glossKeep * 100)}%`)],
      ),
    );

    if (opt.tintVariants.length > 1) {
      const vs = h('div', { class: 'variants', role: 'radiogroup', 'aria-label': 'Variações de cor' });
      for (const v of opt.tintVariants) {
        const sw = h(
          'button',
          {
            class: 'variant',
            type: 'button',
            role: 'radio',
            title: v.name,
            onclick: () => this.store.setSlot(slot.id, { variant: v.id }),
          },
          h('span', {
            class: 'variant-swatch',
            style: `${opt.thumbnail ? `background-image:url(${opt.thumbnail});` : ''}background-color:${linToCss(v.tint)}`,
          }),
          h('span', { class: 'variant-name' }, v.name),
        );
        vs.append(sw);
        this.updaters.push((s) => {
          const on = s.slots[slot.id]?.variant === v.id;
          sw.classList.toggle('is-active', on);
          sw.setAttribute('aria-checked', String(on));
        });
      }
      detail.append(h('p', { class: 'sub-label' }, 'Tonalidade'), vs);
    }
    return this.section(2, 'Acabamento', grid, detail);
  }

  // 03 — Ajuste da textura
  private sectionTransform(st: ConfigState): HTMLElement {
    const slot = this.slot;
    const cfg = st.slots[slot.id]!;
    const opt = slot.options.find((o) => o.id === cfg.option)!;
    const solid = !opt.diffuseMap;
    const id = (k: string) => `${slot.id}-${k}`;
    const [smin, smax] = slot.scaleRange;
    const set = (patch: Parameters<Store['setSlot']>[1]) => this.store.setSlot(slot.id, patch);

    const sliders: [keyof typeof cfg, Slider][] = [
      ['scale', slider({
        id: id('scale'), label: 'Escala', min: smin, max: smax, step: 0.05, value: cfg.scale, reset: 1,
        format: (v) => `${num(v)}×`, onInput: (v) => set({ scale: v }),
        hint: opt.sizeM ? `1× = tamanho real (${num(opt.sizeM[0])} × ${num(opt.sizeM[1])} m)` : undefined,
        disabled: solid || smin === smax,
      })],
      ['rotation', slider({
        id: id('rot'), label: 'Rotação', min: 0, max: 360, step: 1, value: cfg.rotation, reset: 0,
        format: (v) => `${Math.round(v)}°`, onInput: (v) => set({ rotation: v }),
        disabled: solid || !slot.allowRotation,
      })],
      ['ox', slider({
        id: id('ox'), label: 'Deslocamento X', min: 0, max: 1, step: 0.01, value: cfg.ox, reset: 0,
        format: (v) => `${Math.round(v * 100)}%`, onInput: (v) => set({ ox: v }),
        disabled: solid || !slot.allowOffset,
      })],
      ['oy', slider({
        id: id('oy'), label: 'Deslocamento Y', min: 0, max: 1, step: 0.01, value: cfg.oy, reset: 0,
        format: (v) => `${Math.round(v * 100)}%`, onInput: (v) => set({ oy: v }),
        disabled: solid || !slot.allowOffset,
      })],
    ];
    this.updaters.push((s) => {
      const c = s.slots[slot.id]!;
      for (const [k, sl] of sliders) sl.set(c[k] as number);
    });

    const quick = h('div', { class: 'quick-rot', role: 'group', 'aria-label': 'Rotação rápida' });
    for (const deg of [0, 45, 90]) {
      const b = h('button', { class: 'chip', type: 'button', disabled: solid || !slot.allowRotation, onclick: () => set({ rotation: deg }) }, `${deg}°`);
      quick.append(b);
      this.updaters.push((s) => b.classList.toggle('is-active', s.slots[slot.id]!.rotation === deg));
    }
    const reset = h(
      'button',
      { class: 'link-btn', type: 'button', disabled: solid, onclick: () => set({ scale: 1, rotation: 0, ox: 0, oy: 0 }) },
      icon(ICONS.reset, 15),
      'Restaurar',
    );
    const body = h(
      'div',
      { class: 'controls' },
      sliders[0]![1].el,
      h('div', { class: 'rot-wrap' }, sliders[1]![1].el, quick),
      h('div', { class: 'two-col' }, sliders[2]![1].el, sliders[3]![1].el),
      solid ? h('p', { class: 'muted-note' }, 'Cor sólida: escala e rotação não se aplicam.') : null,
    );
    const sec = this.section(3, 'Ajuste da textura', body);
    sec.querySelector('.sec-title')!.append(reset);
    return sec;
  }

  // 04 — Iluminação (LightMix)
  private sectionLights(st: ConfigState): HTMLElement {
    const cam = this.catalog.cameras.find((c) => c.id === st.cam)!;
    if (!cam.lightGroups.length) {
      return this.section(4, 'Iluminação', h('p', { class: 'muted-note' }, 'Esta câmera não tem grupos de luz.'));
    }
    const list = h('div', { class: 'lights' });
    for (const g of cam.lightGroups) {
      const l = st.lights[g.id]!;
      const [kmin, kmax] = kelvinBounds(g.kelvin);
      const stops = [kmin, (kmin + kmax) / 2, kmax].map((k) => kelvinToCss(k)).join(', ');
      const dot = h('span', { class: 'light-dot' });
      const inten = slider({
        id: `lg-${g.id}-i`, label: 'Intensidade', min: g.range[0], max: g.range[1], step: 0.05, value: l.intensity,
        reset: g.intensity, format: (v) => `${num(v)}×`, onInput: (v) => this.store.setLight(g.id, { intensity: v }),
      });
      const temp = slider({
        id: `lg-${g.id}-k`, label: 'Temperatura', min: kmin, max: kmax, step: 50, value: l.kelvin, reset: g.kelvin,
        format: (v) => `${Math.round(v)} K`, onInput: (v) => this.store.setLight(g.id, { kelvin: v }),
        track: `linear-gradient(90deg, ${stops})`,
      });
      this.updaters.push((s) => {
        const c = s.lights[g.id]!;
        inten.set(c.intensity);
        temp.set(c.kelvin);
        dot.style.background = kelvinToCss(c.kelvin);
        dot.style.opacity = String(0.35 + 0.65 * Math.min(1, c.intensity / Math.max(g.range[1], 1e-6) * 1.5));
      });
      list.append(
        h(
          'div',
          { class: 'light' },
          h('div', { class: 'light-head' }, h('span', { class: 'light-icon' }, icon(/sun|sol/i.test(g.id + g.name) ? ICONS.sun : ICONS.bulb, 16)), h('span', { class: 'light-name' }, g.name), dot),
          inten.el,
          temp.el,
        ),
      );
    }
    const reset = h(
      'button',
      {
        class: 'link-btn',
        type: 'button',
        onclick: () =>
          this.store.update((d) => {
            for (const g of cam.lightGroups) d.lights[g.id] = { intensity: g.intensity, kelvin: g.kelvin };
          }),
      },
      icon(ICONS.reset, 15),
      'Original',
    );
    const sec = this.section(4, 'Iluminação', list);
    sec.querySelector('.sec-title')!.append(reset);
    return sec;
  }

  // 05 — Orçamento
  private sectionBudget(): HTMLElement {
    const box = h('div', { class: 'budget', 'aria-live': 'polite' });
    this.updaters.push((s) => {
      const b = budget(this.catalog, s);
      const rows = this.catalog.slots.map((slot) => {
        const line = b.lines.find((l) => l.slotId === slot.id);
        const opt = slot.options.find((o) => o.id === s.slots[slot.id]?.option);
        return h(
          'div',
          { class: 'bud-row' },
          h('div', { class: 'bud-what' }, h('span', { class: 'bud-slot' }, slot.name), h('span', { class: 'bud-opt' }, opt?.name ?? '')),
          line
            ? h('div', { class: 'bud-calc' }, h('span', { class: 'bud-formula' }, `${num(line.area)} m² × ${money(line.unitPrice, line.currency)}`), h('span', { class: 'bud-val' }, money(line.total, line.currency)))
            : h('div', { class: 'bud-calc' }, h('span', { class: 'bud-formula' }, 'sem preço cadastrado')),
        );
      });
      box.replaceChildren(
        ...rows,
        h('div', { class: 'bud-total' }, h('span', { class: 'bud-total-label' }, 'Total estimado'), h('span', { class: 'bud-total-val' }, money(b.total, b.currency))),
        h('p', { class: 'bud-note' }, 'Valores de referência. Área calculada a partir do modelo 3D.'),
      );
    });
    return this.section(5, 'Orçamento', box);
  }
}
