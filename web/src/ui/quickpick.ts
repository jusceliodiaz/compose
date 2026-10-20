// Leque rápido: ao clicar numa superfície da imagem, 3 opções de material brotam do ponto clicado.
// Passar o mouse numa opção mostra a prévia na cena; clicar aplica.
import type { MaterialOption, Slot } from '../catalog/schema';
import { h, icon, ICONS, money } from './dom';

export interface QuickPickEvents {
  onPreview(choice: QuickChoice | null): void;
  onSelect(choice: QuickChoice): void;
  onMore(): void;
  onClose(): void;
}

const COUNT = 3;

export interface QuickChoice {
  option: MaterialOption;
  variantId: string | null;
}
const RADIUS = 92;

const srgb = (c: number) => (c <= 0.0031308 ? c * 12.92 : 1.055 * Math.pow(c, 1 / 2.4) - 0.055);
const linToCss = (c: readonly number[]) =>
  `rgb(${c.map((x) => Math.round(Math.min(1, Math.max(0, srgb(x))) * 255)).join(' ')})`;

/** As 3 opções do leque: as escolhidas no catálogo (quick_options). */
export function quickChoices(slot: Slot): QuickChoice[] {
  return slot.quickOptions
    .map((q) => ({ option: slot.options.find((o) => o.id === q.optionId)!, variantId: q.variantId }))
    .filter((c) => c.option)
    .slice(0, COUNT);
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
  open(x: number, y: number, slot: Slot, current: { option: string; variant: string | null }, bounds: { w: number; h: number }): void {
    window.clearTimeout(this.closeTimer);
    this.slot = slot;
    // esfera "voltar ao padrão" (a opção default do slot, normalmente "Original do render") + as 3 do trio
    const def = slot.options.find((o) => o.id === slot.defaultOption);
    const trio = quickChoices(slot).filter((c) => c.option.id !== def?.id);
    const opts: (QuickChoice & { reset?: boolean })[] = def
      ? [{ option: def, variantId: def.tintVariants[0]?.id ?? null, reset: true }, ...trio]
      : trio;
    const radius = opts.length > 3 ? RADIUS + 10 : RADIUS;
    // abre para cima; perto do topo, para baixo. Mantém o leque dentro da tela.
    const up = y > radius + 70;
    const cx = Math.min(bounds.w - radius - 48, Math.max(radius + 48, x));
    const spread = opts.length > 3 ? [-162, -114, -66, -18] : [-150, -90, -30];
    const angles = up ? spread : spread.map((a) => -a);

    const items = opts.map((c, i) => {
      const o = c.option;
      const a = (angles[i]! * Math.PI) / 180;
      const variant = o.tintVariants.find((v) => v.id === c.variantId) ?? null;
      const isReset = 'reset' in c && c.reset === true;
      // textura com a cor da variação (a miniatura é neutra/clara; multiply aplica o tom)
      const swatch = isReset
        ? h('span', { class: 'qp-img qp-img--reset' }, icon(ICONS.reset, 22))
        : o.thumbnail
        ? h('span', {
            class: 'qp-img',
            style: `background-image:url(${o.thumbnail});${variant ? `background-color:${linToCss(variant.tint.map((t) => t * 0.5))};background-blend-mode:multiply;` : ''}`,
          })
        : h('span', { class: 'qp-img', style: `background:${linToCss(o.albedoColor)}` });
      const isCurrent = o.id === current.option && (isReset || c.variantId === null || c.variantId === current.variant);
      const name = isReset ? 'Voltar ao original' : variant ? `${o.name} ${variant.name.toLowerCase()}` : o.name;
      return h(
        'button',
        {
          class: `qp-item${isCurrent ? ' is-current' : ''}${isReset ? ' qp-item--reset' : ''}`,
          type: 'button',
          'aria-label': o.price ? `${name}, ${money(o.price.value, o.price.currency)} por m²` : name,
          'aria-current': isCurrent ? 'true' : null,
          style: `--dx:${Math.cos(a) * radius}px; --dy:${Math.sin(a) * radius}px; --i:${i}`,
          onpointerenter: () => this.events.onPreview(c),
          onpointerleave: () => this.events.onPreview(null),
          onfocus: () => this.events.onPreview(c),
          onblur: () => this.events.onPreview(null),
          onclick: () => {
            this.events.onSelect(c);
            this.close(true);
          },
        },
        swatch,
        h('span', { class: `qp-label ${up ? '' : 'qp-label--below'}` }, h('strong', {}, name),
          isReset ? h('span', {}, o.name) : o.price ? h('span', {}, money(o.price.value, o.price.currency)) : null),
      );
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
