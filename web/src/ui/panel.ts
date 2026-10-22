// Painel: janela flutuante compacta (design system do Amalfi). Cabeçalho com a superfície atual → acabamentos →
// ajustar textura / iluminação (recolhíveis) → total + export. As superfícies ficam num dock embaixo da imagem.
import type { MaterialOption, NormalizedCatalog, Slot } from '../catalog/schema';
import { budget, type ConfigState, type Store } from '../state/store';
import { EV_RANGE, kelvinBounds } from '../state/urlState';
import { kelvinToCss } from '../util/kelvin';
import { h, icon, ICONS, money, num } from './dom';
import { slider, type Slider } from './slider';

export interface PanelEvents {
  /** Cursor sobre uma aba de superfície (destaca na imagem); null = saiu. */
  onSurfaceHover?(slotId: string | null): void;
  /** Pré-carrega o albedo ao passar o mouse/focar a miniatura. */
  preload(slotId: string, option: MaterialOption): void;
  onExport(): void;
  /** Clique numa superfície do dock: a janela deve abrir. */
  onReveal?(): void;
  /** Botão × da janela (ou clique de novo na superfície ativa). */
  onClose?(): void;
}

const srgb = (c: number) => (c <= 0.0031308 ? c * 12.92 : 1.055 * Math.pow(c, 1 / 2.4) - 0.055);
const linToCss = (c: readonly number[]) =>
  `rgb(${c.map((x) => Math.round(Math.min(1, Math.max(0, srgb(x))) * 255)).join(' ')})`;
const two = (n: number) => String(n).padStart(2, '0');
const fmtEv = (v: number) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${num(Math.abs(v), 1)} EV`;

type Updater = (s: ConfigState) => void;

export class Panel {
  readonly el: HTMLElement;
  /** Dock de superfícies (fica no palco, fora da janela). */
  readonly dock: HTMLElement;
  private activeSlot: string;
  private readonly head: HTMLElement;
  private readonly body: HTMLElement;
  private readonly exportBtn: HTMLButtonElement;
  private updaters: Updater[] = [];
  private readonly footUpdaters: Updater[] = [];
  /** Seções recolhíveis abertas (sobrevive à reconstrução do painel). */
  private readonly open = new Set<string>();

  constructor(
    private readonly catalog: NormalizedCatalog,
    private readonly store: Store,
    private readonly events: PanelEvents,
  ) {
    this.activeSlot = catalog.slots[0]?.id ?? '';
    this.head = h('div', { class: 'panel-head' });
    this.dock = h('nav', { class: 'dock', role: 'tablist', 'aria-label': 'Superfícies' });
    this.body = h('div', { class: 'panel-body', id: 'panel-body' });
    this.exportBtn = h(
      'button',
      { class: 'btn btn--primary', type: 'button', onclick: () => events.onExport() },
      icon(ICONS.download, 17),
      h('span', { class: 'btn-label' }, 'Baixar imagem'),
    );
    const sheetToggle = h(
      'button',
      {
        class: 'sheet-toggle',
        type: 'button',
        'aria-expanded': 'true',
        'aria-controls': 'panel-body',
        onclick: () => {
          const collapsed = this.el.classList.toggle('is-collapsed');
          sheetToggle.setAttribute('aria-expanded', String(!collapsed));
        },
      },
      h('span', { class: 'sheet-grab', 'aria-hidden': 'true' }),
      h('span', { class: 'sheet-label' }, 'Personalizar'),
      icon(ICONS.chevron, 18),
    );
    this.el = h(
      'aside',
      { class: 'panel', 'aria-label': 'Personalização' },
      sheetToggle,
      this.head,
      this.body,
      this.footer(),
    );
    this.build();
    store.subscribe((s, prev) => {
      if (s.slots[this.activeSlot]?.option !== prev.slots[this.activeSlot]?.option) this.build();
      else this.updaters.forEach((u) => u(s));
      this.footUpdaters.forEach((u) => u(s));
    });
    this.footUpdaters.forEach((u) => u(store.get()));
  }

  get slotId(): string {
    return this.activeSlot;
  }

  /** Mostra uma superfície no painel. reveal = também expande a gaveta (celular). */
  selectSlot(slotId: string, reveal = true): void {
    if (!this.catalog.slots.some((s) => s.id === slotId)) return;
    if (reveal) this.el.classList.remove('is-collapsed');
    if (slotId === this.activeSlot) return;
    this.activeSlot = slotId;
    this.build();
    this.body.scrollTop = 0;
  }

  setBusy(busy: boolean, label = 'Gerando PNG…'): void {
    this.exportBtn.disabled = busy;
    this.exportBtn.classList.toggle('is-busy', busy);
    this.exportBtn.querySelector('.btn-label')!.textContent = busy ? label : 'Baixar imagem';
  }

  private get slot(): Slot {
    return this.catalog.slots.find((s) => s.id === this.activeSlot)!;
  }

  /** (Re)constrói o conteúdo — só quando muda o slot ou a opção; o resto é atualizado no lugar. */
  build(): void {
    const scroll = this.body.scrollTop;
    this.updaters = [];
    const st = this.store.get();
    this.head.replaceChildren(this.header());
    this.surfaces();
    this.body.replaceChildren(this.finishes(st), this.transform(st), this.lights(st));
    this.updaters.forEach((u) => u(st));
    this.body.scrollTop = scroll;
  }

  /** Seção recolhível (<details>) com um resumo do estado ao lado do título. */
  private disclosure(id: string, title: string, summary: (s: ConfigState) => string, ...content: (Node | null)[]): HTMLElement {
    const meta = h('span', { class: 'acc-meta' });
    this.updaters.push((s) => (meta.textContent = summary(s)));
    const det = h(
      'details',
      { class: 'acc', open: this.open.has(id), 'data-id': id },
      h('summary', { class: 'acc-sum' }, h('span', { class: 'acc-title' }, title), meta, h('span', { class: 'acc-chev' }, icon(ICONS.chevron, 16))),
      h('div', { class: 'acc-body' }, ...content),
    );
    det.addEventListener('toggle', () => (det.open ? this.open.add(id) : this.open.delete(id)));
    return det;
  }

  // --- Cabeçalho: superfície atual + fechar --------------------------------------

  private header(): HTMLElement {
    const slots = this.catalog.slots;
    const i = slots.findIndex((s) => s.id === this.activeSlot);
    const slot = this.slot;
    const meta = [slot.areaM2 !== null ? `${num(slot.areaM2, 1)} m²` : null, `${slot.options.filter((o) => !o.isTest).length} acabamentos`]
      .filter(Boolean)
      .join(' · ');
    return h(
      'div',
      { class: 'panel-top' },
      h(
        'div',
        { class: 'panel-id' },
        h('p', { class: 'eyebrow' }, slots.length > 1 ? `Superfície ${two(i + 1)} / ${two(slots.length)}` : 'Superfície'),
        h('h2', { class: 'panel-title' }, slot.name),
        h('p', { class: 'panel-meta' }, meta),
      ),
      this.events.onClose
        ? h('button', { class: 'panel-close', type: 'button', 'aria-label': 'Fechar personalização', onclick: () => this.events.onClose?.() }, icon(ICONS.close, 16))
        : null,
    );
  }

  // --- Dock de superfícies (embaixo da imagem) ----------------------------------------

  private surfaces(): void {
    this.dock.replaceChildren(
      ...this.catalog.slots.map((s) => {
        const on = s.id === this.activeSlot;
        return h(
          'button',
          {
            class: `dock-item${on ? ' is-active' : ''}`,
            role: 'tab',
            type: 'button',
            'aria-selected': String(on),
            'aria-controls': 'panel-body',
            onclick: () => {
              // de novo na superfície ativa com a janela aberta: fecha (como no dock do Amalfi)
              if (on && !this.el.classList.contains('is-hidden')) return this.events.onClose?.();
              this.selectSlot(s.id);
              this.events.onReveal?.();
            },
            onpointerenter: () => this.events.onSurfaceHover?.(s.id),
            onpointerleave: () => this.events.onSurfaceHover?.(null),
          },
          h('span', { class: 'dock-name' }, s.name),
        );
      }),
    );
  }

  // --- Acabamento ----------------------------------------------------------------

  private finishes(st: ConfigState): HTMLElement {
    const slot = this.slot;
    const cfg = st.slots[slot.id]!;
    const visible = slot.options.filter((x) => !x.isTest);
    // 4 opções → 4 colunas (evita um card sozinho na segunda linha)
    const cols = visible.length === 4 ? 4 : 3;
    const grid = h('div', { class: 'swatches', role: 'radiogroup', 'aria-label': `Acabamentos de ${slot.name}`, style: `--cols:${cols}` });
    for (const o of visible) {
      const on = o.id === cfg.option;
      const thumb = o.thumbnail
        ? h('img', { class: 'swatch-img', src: o.thumbnail, alt: '', loading: 'lazy', decoding: 'async', width: 256, height: 256 })
        : h('span', { class: 'swatch-img swatch-img--solid', style: `background:${linToCss(o.albedoColor)}` });
      grid.append(
        h(
          'button',
          {
            class: `mat-card${on ? ' is-active' : ''}`,
            type: 'button',
            role: 'radio',
            'aria-checked': String(on),
            title: o.price ? `${o.name} · ${money(o.price.value, o.price.currency)}/m²` : o.name,
            onclick: () => this.store.setSlot(slot.id, { option: o.id, variant: o.tintVariants[0]?.id ?? null }),
            onpointerenter: () => this.events.preload(slot.id, o),
            onfocus: () => this.events.preload(slot.id, o),
          },
          h('span', { class: 'swatch' }, thumb, on ? h('span', { class: 'swatch-check' }, icon(ICONS.check, 13)) : null),
          h('span', { class: 'mat-name' }, o.name),
          h('span', { class: 'mat-price', title: o.price ? 'por m²' : undefined }, o.price ? money(o.price.value, o.price.currency) : o.keepOriginal ? 'Incluso' : '—'),
        ),
      );
    }

    const opt = slot.options.find((o) => o.id === cfg.option)!;
    const specs: [string, string][] = [];
    if (opt.sizeM) specs.push(['Módulo', `${num(opt.sizeM[0])} × ${num(opt.sizeM[1])} m`]);
    if (opt.sku) specs.push(['SKU', opt.sku]);
    if (!opt.keepOriginal) specs.push(['Reflexo', `${Math.round(opt.glossKeep * 100)}%`]);

    const detail = h(
      'div',
      { class: 'detail' },
      h(
        'div',
        { class: 'detail-head' },
        h('div', {},
          h('p', { class: 'detail-kicker' }, opt.isTest ? 'Material de teste' : opt.keepOriginal ? 'Sem alteração' : 'Selecionado'),
          h('h3', { class: 'detail-title' }, opt.name),
        ),
        opt.price ? h('p', { class: 'detail-price' }, money(opt.price.value, opt.price.currency), h('span', {}, '/m²')) : null,
      ),
      opt.finish ? h('p', { class: 'detail-finish' }, opt.finish) : null,
      specs.length ? h('dl', { class: 'specs' }, ...specs.map(([k, v]) => h('div', { class: 'spec' }, h('dt', {}, k), h('dd', {}, v)))) : null,
    );

    if (opt.tintVariants.length > 1) {
      const vs = h('div', { class: 'tones', role: 'radiogroup', 'aria-label': 'Tonalidade' });
      for (const v of opt.tintVariants) {
        const b = h(
          'button',
          { class: 'tone', type: 'button', role: 'radio', onclick: () => this.store.setSlot(slot.id, { variant: v.id }) },
          h('span', {
            class: 'tone-dot',
            style: `${opt.thumbnail ? `background-image:url(${opt.thumbnail});` : ''}background-color:${linToCss(v.tint)}`,
          }),
          v.name,
        );
        vs.append(b);
        this.updaters.push((s) => {
          const on = s.slots[slot.id]?.variant === v.id;
          b.classList.toggle('is-active', on);
          b.setAttribute('aria-checked', String(on));
        });
      }
      detail.append(h('p', { class: 'field-label' }, 'Tonalidade'), vs);
    }

    return h(
      'section',
      { class: 'block' },
      grid,
      detail,
    );
  }

  // --- Ajustar textura -------------------------------------------------------------

  private transform(st: ConfigState): HTMLElement {
    const slot = this.slot;
    const cfg = st.slots[slot.id]!;
    const opt = slot.options.find((o) => o.id === cfg.option)!;
    const solid = !opt.diffuseMap;
    const id = (k: string) => `${slot.id}-${k}`;
    const [smin, smax] = slot.scaleRange;
    const set = (patch: Parameters<Store['setSlot']>[1]) => this.store.setSlot(slot.id, patch);

    const sliders: ['scale' | 'rotation' | 'ox' | 'oy', Slider][] = [
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
      for (const [k, sl] of sliders) sl.set(c[k]);
    });

    const quick = h('div', { class: 'chips', role: 'group', 'aria-label': 'Rotação rápida' });
    for (const deg of [0, 45, 90]) {
      const b = h('button', { class: 'chip', type: 'button', disabled: solid || !slot.allowRotation, onclick: () => set({ rotation: deg }) }, `${deg}°`);
      quick.append(b);
      this.updaters.push((s) => b.classList.toggle('is-active', s.slots[slot.id]!.rotation === deg));
    }
    const note = opt.keepOriginal
      ? 'Material original do render: não há ajustes de textura.'
      : 'Cor sólida: escala e rotação não se aplicam.';

    return this.disclosure(
      'transform',
      'Ajustar textura',
      (s) => {
        const c = s.slots[slot.id]!;
        return solid ? '—' : `${num(c.scale)}× · ${Math.round(c.rotation)}°`;
      },
      solid ? h('p', { class: 'note' }, note) : null,
      sliders[0]![1].el,
      h('div', {}, sliders[1]![1].el, quick),
      h('div', { class: 'two-col' }, sliders[2]![1].el, sliders[3]![1].el),
      h(
        'button',
        { class: 'text-btn', type: 'button', disabled: solid, onclick: () => set({ scale: 1, rotation: 0, ox: 0, oy: 0 }) },
        icon(ICONS.reset, 15),
        'Restaurar ajustes',
      ),
    );
  }

  // --- Iluminação ------------------------------------------------------------------

  private lights(st: ConfigState): HTMLElement {
    const cam = this.catalog.cameras.find((c) => c.id === st.cam)!;
    const exposure = slider({
      id: 'exposure', label: 'Exposição', min: -EV_RANGE, max: EV_RANGE, step: 0.1, value: st.ev, reset: 0,
      format: fmtEv,
      onInput: (v) => this.store.update((d) => {
        d.ev = Math.round(v * 10) / 10;
      }),
      hint: 'Ajusta a cena inteira. 0 = exposição original do render.',
    });
    this.updaters.push((s) => exposure.set(s.ev));

    const groups = cam.lightGroups.map((g) => {
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
      });
      return h(
        'div',
        { class: 'light' },
        h('div', { class: 'light-head' }, icon(/sun|sol/i.test(g.id + g.name) ? ICONS.sun : ICONS.bulb, 16), h('span', { class: 'light-name' }, g.name), dot),
        inten.el,
        temp.el,
      );
    });

    return this.disclosure(
      'lights',
      'Iluminação',
      (s) => {
        const changed = cam.lightGroups.filter((g) => {
          const c = s.lights[g.id]!;
          return c.intensity !== g.intensity || c.kelvin !== g.kelvin;
        }).length;
        return `${fmtEv(s.ev)}${cam.lightGroups.length ? ` · ${changed ? `${changed} ajustada${changed > 1 ? 's' : ''}` : 'original'}` : ''}`;
      },
      exposure.el,
      ...groups,
      cam.lightGroups.length ? null : h('p', { class: 'note' }, 'Esta câmera não tem grupos de luz.'),
      h(
        'button',
        {
          class: 'text-btn',
          type: 'button',
          onclick: () =>
            this.store.update((d) => {
              d.ev = 0;
              for (const g of cam.lightGroups) d.lights[g.id] = { intensity: g.intensity, kelvin: g.kelvin };
            }),
        },
        icon(ICONS.reset, 15),
        'Voltar à luz original',
      ),
    );
  }

  // --- Rodapé: orçamento + export ----------------------------------------------------

  private footer(): HTMLElement {
    const lines = h('div', { class: 'bud-lines' });
    const total = h('strong', { class: 'bud-total-val' });
    const count = h('span', { class: 'bud-count' });
    this.footUpdaters.push((s) => {
      const b = budget(this.catalog, s);
      lines.replaceChildren(
        ...this.catalog.slots.map((slot) => {
          const line = b.lines.find((l) => l.slotId === slot.id);
          const opt = slot.options.find((o) => o.id === s.slots[slot.id]?.option);
          return h(
            'div',
            { class: 'bud-row' },
            h('span', { class: 'bud-what' }, h('span', { class: 'bud-slot' }, slot.name), h('span', { class: 'bud-opt' }, opt?.name ?? '')),
            h('span', { class: 'bud-val', title: line ? `${num(line.area)} m² × ${money(line.unitPrice, line.currency)}` : '' }, line ? money(line.total, line.currency) : '—'),
          );
        }),
      );
      total.textContent = money(b.total, b.currency);
      const n = this.catalog.slots.filter((sl) => s.slots[sl.id]?.option !== sl.defaultOption).length;
      count.textContent = n ? `${n} ${n === 1 ? 'alterada' : 'alteradas'}` : 'Original';
    });
    return h(
      'footer',
      { class: 'panel-foot' },
      h(
        'details',
        { class: 'bud' },
        h(
          'summary',
          { class: 'bud-sum' },
          h('span', { class: 'bud-label' }, h('span', {}, 'Total estimado', icon(ICONS.chevron, 13)), count),
          total,
        ),
        lines,
        h('p', { class: 'bud-note' }, 'Área × preço por m². Valores de referência.'),
      ),
      this.exportBtn,
    );
  }
}
