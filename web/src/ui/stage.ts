// Palco: o render ocupa a janela inteira; marca, projeto e ferramentas flutuam por cima.
import { DebugMode } from '../engine/Compositor';
import type { ProjectEntry } from './App';
import { h, icon, ICONS } from './dom';

export interface StageActions {
  onSplit(x: number): void;
  onChecker(): void;
  onCopyLink(): void;
  onDebug(mode: DebugMode): void;
  onProject(id: string): void;
  onTogglePanel(): void;
  /** Cursor sobre a imagem: devolve o nome da superfície sob (u, v) ou null. (-1, -1) = saiu. */
  onHover(u: number, v: number): string | null;
  /** Clique/toque na imagem. (x, y) = posição em px relativa ao palco. */
  onPick(u: number, v: number, touch: boolean, x: number, y: number): void;
}

export interface StageTitle {
  project: string;
  camera: string;
  projects: ProjectEntry[];
  current: string;
}

const DEBUG_MODES: [DebugMode, string][] = [
  [DebugMode.Off, 'Final'],
  [DebugMode.UV, 'UV'],
  [DebugMode.Masks, 'Máscaras'],
  [DebugMode.DiffuseLight, 'Luz difusa'],
  [DebugMode.Seams, 'Costuras'],
  [DebugMode.Albedo, 'Albedo'],
];

/** Abaixo desta largura a imagem é encaixada (contain) em vez de preencher a janela (cover). */
const MOBILE = '(max-width: 900px)';

export class Stage {
  readonly el: HTMLElement;
  readonly canvas: HTMLCanvasElement;
  private readonly frame: HTMLElement;
  private readonly well: HTMLElement;
  private readonly poster: HTMLImageElement;
  private readonly progress: HTMLElement;
  private readonly progressLabel: HTMLElement;
  private readonly handle: HTMLElement;
  private readonly debugBar: HTMLElement;
  private readonly memLabel: HTMLElement;
  private readonly toastEl: HTMLElement;
  private readonly tip: HTMLElement;
  private readonly btnCompare: HTMLButtonElement;
  private readonly btnChecker: HTMLButtonElement;
  private readonly btnPanel: HTMLButtonElement;
  private aspect = 16 / 9;
  private split = 0.5;
  private comparing = false;
  private toastTimer = 0;
  onResize: ((w: number, h: number) => void) | null = null;

  constructor(title: StageTitle, private readonly actions: StageActions) {
    this.canvas = h('canvas', { class: 'frame-canvas', 'aria-label': 'Render configurado do ambiente', role: 'img' });
    this.poster = h('img', { class: 'frame-poster', alt: '', decoding: 'async' });
    this.progress = h('div', { class: 'loader-bar' });
    this.progressLabel = h('span', { class: 'loader-label' }, 'Preparando a cena…');
    this.handle = h(
      'div',
      {
        class: 'cmp-handle',
        role: 'slider',
        tabindex: 0,
        'aria-label': 'Posição da cortina antes/depois',
        'aria-valuemin': 0,
        'aria-valuemax': 100,
        'aria-valuenow': 50,
      },
      h('span', { class: 'cmp-line' }),
      h('span', { class: 'cmp-knob' }, icon(ICONS.grip, 16)),
    );
    this.frame = h(
      'div',
      { class: 'frame is-loading' },
      this.poster,
      this.canvas,
      this.handle,
    );
    this.well = h('div', { class: 'stage-well' }, this.frame);

    const tool = (ic: string, label: string, shortcut: string | null, onclick: () => void, pressable = true) =>
      h(
        'button',
        {
          class: 'tool',
          type: 'button',
          'aria-label': label,
          'data-tip': shortcut ? `${label} · ${shortcut}` : label,
          'aria-pressed': pressable ? 'false' : null,
          onclick,
        },
        icon(ic, 18),
      );
    this.btnCompare = tool(ICONS.split, 'Antes / depois', 'C', () => this.setCompare(!this.comparing));
    this.btnChecker = tool(ICONS.checker, 'Grade de teste', 'T', () => actions.onChecker());
    const btnLink = tool(ICONS.link, 'Copiar link', null, () => actions.onCopyLink(), false);
    this.btnPanel = tool(ICONS.sliders, 'Painel de personalização', 'P', () => actions.onTogglePanel());
    this.btnPanel.setAttribute('aria-pressed', 'true');

    this.memLabel = h('span', { class: 'dbg-mem' });
    const seg = h('div', { class: 'dbg-seg', role: 'radiogroup', 'aria-label': 'Modo de depuração' });
    for (const [mode, label] of DEBUG_MODES) {
      seg.append(
        h('button', { type: 'button', role: 'radio', 'aria-checked': String(mode === DebugMode.Off), 'data-mode': mode, onclick: () => this.setDebug(mode) }, label),
      );
    }
    this.debugBar = h(
      'div',
      { class: 'dbg glass', hidden: true },
      h('span', { class: 'dbg-title' }, icon(ICONS.scan, 15), 'Depuração'),
      seg,
      this.memLabel,
      h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Fechar depuração', onclick: () => this.toggleDebug(false) }, icon(ICONS.close, 15)),
    );

    this.toastEl = h('div', { class: 'toast', role: 'status', 'aria-live': 'polite' });
    this.tip = h('div', { class: 'pick-tip', 'aria-hidden': 'true' });

    const projectEl =
      title.projects.length > 1
        ? h(
            'label',
            { class: 'project-switch' },
            h('span', { class: 'sr-only' }, 'Projeto'),
            h(
              'select',
              { class: 'project-name project-select', onchange: (e: Event) => actions.onProject((e.target as HTMLSelectElement).value) },
              ...title.projects.map((p) => h('option', { value: p.id, selected: p.id === title.current }, p.name)),
            ),
            icon(ICONS.chevron, 15),
          )
        : h('h1', { class: 'project-name' }, title.project);

    this.el = h(
      'main',
      { class: 'stage' },
      this.well,
      h(
        'header',
        { class: 'hud' },
        h(
          'div',
          { class: 'hud-id glass' },
          h('span', { class: 'logo', 'aria-hidden': 'true' }, h('span'), h('span')),
          projectEl,
          h('span', { class: 'cam-name' }, title.camera),
        ),
        h('nav', { class: 'tools glass', 'aria-label': 'Ações do render' }, this.btnCompare, this.btnChecker, btnLink, h('span', { class: 'tools-sep', 'aria-hidden': 'true' }), this.btnPanel),
      ),
      h('span', { class: 'cmp-tag cmp-tag--before' }, 'Antes'),
      h('span', { class: 'cmp-tag cmp-tag--after' }, 'Depois'),
      h('div', { class: 'loader glass', role: 'status', 'aria-live': 'polite' }, this.progressLabel, this.progress),
      this.debugBar,
      this.toastEl,
      this.tip,
    );

    this.bindCompare();
    this.bindPick();
    new ResizeObserver(() => this.layout()).observe(this.well);
    window.matchMedia(MOBILE).addEventListener('change', () => this.layout());
  }

  setPoster(url: string, width: number, height: number): void {
    this.aspect = width / height;
    this.el.style.setProperty('--aspect', `${width} / ${height}`);
    this.poster.src = url;
    this.layout();
  }

  /**
   * Desktop: a imagem PREENCHE a janela (cover, as bordas excedentes ficam fora da tela).
   * Celular: a imagem é ENCAIXADA na largura (contain), com o painel embaixo.
   */
  layout(): void {
    const r = this.well.getBoundingClientRect();
    if (!r.width || !r.height) return;
    const cover = !window.matchMedia(MOBILE).matches;
    const byWidth = r.width / this.aspect;
    const fitHeight = cover ? byWidth < r.height : byWidth > r.height;
    const w = fitHeight ? r.height * this.aspect : r.width;
    const hh = fitHeight ? r.height : byWidth;
    this.frame.style.width = `${Math.round(w)}px`;
    this.frame.style.height = `${Math.round(hh)}px`;
    this.onResize?.(Math.round(w), Math.round(hh));
  }

  setProgress(loaded: number, total: number): void {
    const pct = total ? (loaded / total) * 100 : 0;
    this.progress.style.setProperty('--pct', `${pct}%`);
    this.progressLabel.textContent = total ? `Carregando a cena · ${loaded} de ${total}` : 'Preparando a cena…';
  }

  setReady(): void {
    this.frame.classList.remove('is-loading');
    this.frame.classList.add('is-ready');
    this.el.classList.add('is-ready');
  }

  setCheckerActive(on: boolean): void {
    this.btnChecker.setAttribute('aria-pressed', String(on));
  }

  setPanelOpen(open: boolean): void {
    this.btnPanel.setAttribute('aria-pressed', String(open));
  }

  // --- Comparador ----------------------------------------------------------------

  setCompare(on: boolean): void {
    this.comparing = on;
    this.frame.classList.toggle('is-comparing', on);
    this.el.classList.toggle('is-comparing', on);
    this.btnCompare.setAttribute('aria-pressed', String(on));
    this.applySplit();
  }

  get isComparing(): boolean {
    return this.comparing;
  }

  private applySplit(): void {
    this.handle.style.left = `${this.split * 100}%`;
    this.handle.setAttribute('aria-valuenow', String(Math.round(this.split * 100)));
    this.actions.onSplit(this.comparing ? this.split : 0);
  }

  private bindCompare(): void {
    let dragging = false;
    const move = (e: PointerEvent) => {
      const r = this.frame.getBoundingClientRect();
      this.split = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
      this.applySplit();
    };
    this.frame.addEventListener('pointerdown', (e) => {
      if (!this.comparing) return;
      dragging = true;
      this.frame.setPointerCapture(e.pointerId);
      this.frame.classList.add('is-dragging');
      move(e);
    });
    this.frame.addEventListener('pointermove', (e) => dragging && move(e));
    const end = (e: PointerEvent) => {
      if (!dragging) return;
      dragging = false;
      this.frame.classList.remove('is-dragging');
      if (this.frame.hasPointerCapture(e.pointerId)) this.frame.releasePointerCapture(e.pointerId);
    };
    this.frame.addEventListener('pointerup', end);
    this.frame.addEventListener('pointercancel', end);
    this.handle.addEventListener('keydown', (e) => {
      const step = e.shiftKey ? 0.1 : 0.02;
      if (e.key === 'ArrowLeft') this.split = Math.max(0, this.split - step);
      else if (e.key === 'ArrowRight') this.split = Math.min(1, this.split + step);
      else if (e.key === 'Home') this.split = 0;
      else if (e.key === 'End') this.split = 1;
      else return;
      e.preventDefault();
      this.applySplit();
    });
  }

  // --- Clique nas superfícies -----------------------------------------------------

  private bindPick(): void {
    const uvOf = (e: PointerEvent | MouseEvent) => {
      const r = this.frame.getBoundingClientRect();
      return [(e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height] as const;
    };
    const hide = () => {
      this.tip.classList.remove('is-visible');
      this.frame.classList.remove('is-pickable');
    };
    this.frame.addEventListener('pointermove', (e) => {
      if (this.comparing || e.pointerType !== 'mouse') return;
      const [u, v] = uvOf(e);
      const label = this.actions.onHover(u, v);
      if (!label) return hide();
      const s = this.el.getBoundingClientRect();
      this.tip.replaceChildren(h('strong', {}, label), h('span', {}, 'clique para trocar'));
      this.tip.style.transform = `translate(${e.clientX - s.left + 14}px, ${e.clientY - s.top + 16}px)`;
      this.tip.classList.add('is-visible');
      this.frame.classList.add('is-pickable');
    });
    this.frame.addEventListener('pointerleave', () => {
      this.actions.onHover(-1, -1);
      hide();
    });
    this.frame.addEventListener('click', (e) => {
      if (this.comparing) return;
      const [u, v] = uvOf(e);
      const s = this.el.getBoundingClientRect();
      this.actions.onPick(u, v, (e as PointerEvent).pointerType === 'touch', e.clientX - s.left, e.clientY - s.top);
    });
  }

  // --- Debug ---------------------------------------------------------------------

  toggleDebug(force?: boolean): void {
    const show = force ?? this.debugBar.hidden;
    this.debugBar.hidden = !show;
    if (!show) this.setDebug(DebugMode.Off);
  }

  setDebug(mode: DebugMode): void {
    this.debugBar.querySelectorAll<HTMLButtonElement>('[data-mode]').forEach((b) => {
      b.setAttribute('aria-checked', String(Number(b.dataset.mode) === mode));
    });
    this.actions.onDebug(mode);
  }

  setMemory(mb: number, renders: number): void {
    this.memLabel.textContent = `GPU ≈ ${mb.toFixed(1)} MB · ${renders} ${renders === 1 ? 'render' : 'renders'}`;
  }

  // --- Mensagens -----------------------------------------------------------------

  toast(msg: string, kind: 'ok' | 'warn' = 'ok', ms = 3200): void {
    window.clearTimeout(this.toastTimer);
    this.toastEl.replaceChildren(icon(kind === 'ok' ? ICONS.check : ICONS.alert, 16), h('span', {}, msg));
    this.toastEl.className = `toast is-visible toast--${kind}`;
    this.toastTimer = window.setTimeout(() => this.toastEl.classList.remove('is-visible'), ms);
  }
}
