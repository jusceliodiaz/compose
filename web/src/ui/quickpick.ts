// Leque rápido: ao clicar numa superfície da imagem, 3 opções de material brotam do ponto clicado.
// Passar o mouse numa opção mostra a prévia na cena; clicar aplica.
import type { MaterialOption, Slot } from '../catalog/schema';
import { h, money } from './dom';

export interface QuickPickEvents {
  onPreview(option: MaterialOption | null): void;
  onSelect(option: MaterialOption): void;
  onMore(): void;
  onClose(): void;
}

const COUNT = 3;
const RADIUS = 92;

const srgb = (c: number) => (c <= 0.0031308 ? c * 12.92 : 1.055 * Math.pow(c, 1 / 2.4) - 0.055);
const linToCss = (c: readonly number[]) =>
  `rgb(${c.map((x) => Math.round(Math.min(1, Math.max(0, srgb(x))) * 255)).join(' ')})`;

/** As próximas opções depois da atual (ciclando), sem a de teste. */
export function nextOptions(slot: Slot, currentId: string, n = COUNT): MaterialOption[] {
  const list = slot.options.filter((o) => !o.isTest);
  const i = Math.max(0, list.findIndex((o) => o.id === currentId));
  const out: MaterialOption[] = [];
  for (let k = 1; k < list.length && out.length < n; k++) out.push(list[(i + k) % list.length]!);
  return out;
}

export class QuickPick {
  readonly el: HTMLElement;
  private slot: Slot | null = null;
  private closeTimer = 0;
  private settleTimer = 0;
  /** true quando a última interação foi pelo teclado */
  private keyboard = false;

  constructor(private readonly events: QuickPickEvents) {
    this.el = h('div', { class: 'qp', role: 'dialog', 'aria-modal': 'false', hidden: true });
    this.el.addEventListener('pointerdown', (e) => e.stopPropagation());
    this.el.addEventListener('click', (e) => e.stopPropagation());
    document.addEventListener('pointerdown', () => this.isOpen && this.close());
    document.addEventListener('keydown', (e) => {
      this.keyboard = true;
      if (e.key === 'Escape' && this.isOpen) this.close();
    });
    document.addEventListener('pointerdown', () => (this.keyboard = false), true);
  }

  get isOpen(): boolean {
    return !this.el.hidden && this.el.classList.contains('is-open');
  }

  get slotId(): string | null {
    return this.slot?.id ?? null;
  }

  /** (x, y) em px relativos ao contêiner do leque. */
  open(x: number, y: number, slot: Slot, currentId: string, bounds: { w: number; h: number }): void {
    window.clearTimeout(this.closeTimer);
    this.slot = slot;
    const opts = nextOptions(slot, currentId);
    // abre para cima; perto do topo, para baixo. Mantém o leque dentro da tela.
    const up = y > RADIUS + 70;
    const cx = Math.min(bounds.w - RADIUS - 48, Math.max(RADIUS + 48, x));
    const angles = up ? [-150, -90, -30] : [150, 90, 30];

    const items = opts.map((o, i) => {
      const a = (angles[i]! * Math.PI) / 180;
      const swatch = o.thumbnail
        ? h('img', { class: 'qp-img', src: o.thumbnail, alt: '', decoding: 'async' })
        : h('span', { class: 'qp-img', style: `background:${linToCss(o.albedoColor)}` });
      const b = h(
        'button',
        {
          class: 'qp-item',
          type: 'button',
          'aria-label': o.price ? `${o.name}, ${money(o.price.value, o.price.currency)} por m²` : o.name,
          style: `--dx:${Math.cos(a) * RADIUS}px; --dy:${Math.sin(a) * RADIUS}px; --i:${i}`,
          onpointerenter: () => this.events.onPreview(o),
          onpointerleave: () => this.events.onPreview(null),
          onfocus: () => this.events.onPreview(o),
          onblur: () => this.events.onPreview(null),
          onclick: () => {
            this.events.onSelect(o);
            this.close(true);
          },
        },
        swatch,
        h('span', { class: `qp-label ${up ? '' : 'qp-label--below'}` }, h('strong', {}, o.name),
          o.price ? h('span', {}, money(o.price.value, o.price.currency)) : null),
      );
      return b;
    });

    const more = h(
      'button',
      {
        class: 'qp-more',
        type: 'button',
        style: `--i:${COUNT}`,
        onclick: () => {
          this.close(true);
          this.events.onMore();
        },
      },
      `Todas as opções · ${slot.name}`,
    );

    this.el.replaceChildren(h('span', { class: 'qp-dot' }), ...items, more);
    this.el.classList.toggle('qp--down', !up);
    this.el.style.left = `${cx}px`;
    this.el.style.top = `${y}px`;
    this.el.setAttribute('aria-label', `Trocar ${slot.name}`);
    this.el.hidden = false;
    this.el.classList.remove('is-open', 'is-closing', 'is-settled');
    void this.el.offsetWidth; // reinicia a animação
    this.el.classList.add('is-open');
    // as bolinhas nascem sob o cursor: só aceitam hover depois de chegar ao lugar (senão uma delas
    // "pega" o hover no caminho e dispara a prévia sem o usuário apontar)
    window.clearTimeout(this.settleTimer);
    this.settleTimer = window.setTimeout(() => this.el.classList.add('is-settled'), 420);
    // foco só quando o leque foi aberto pelo teclado (no mouse, o rótulo da 1ª opção ficaria preso)
    if (this.keyboard) items[0]?.focus({ preventScroll: true });
  }

  close(selected = false): void {
    if (this.el.hidden) return;
    window.clearTimeout(this.settleTimer);
    this.el.classList.remove('is-open', 'is-settled');
    this.el.classList.add('is-closing');
    if (!selected) this.events.onPreview(null);
    this.events.onClose();
    this.closeTimer = window.setTimeout(() => {
      this.el.hidden = true;
      this.el.classList.remove('is-closing');
      this.slot = null;
    }, 220);
  }
}
