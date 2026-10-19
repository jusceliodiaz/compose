// Palco: barra superior (projeto + ações do render), o render emoldurado, comparador, carregamento e debug.
import { DebugMode } from '../engine/Compositor';
import type { ProjectEntry } from './App';
import { h, icon, ICONS } from './dom';

export interface StageActions {
  onSplit(x: number): void;
  onChecker(): void;
  onCopyLink(): void;
  onDebug(mode: DebugMode): void;
  onProject(id: string): void;
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
  private readonly btnCompare: HTMLButtonElement;
  private readonly btnChecker: HTMLButtonElement;
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
      h('span', { class: 'cmp-tag cmp-tag--before' }, 'Antes'),
      h('span', { class: 'cmp-tag cmp-tag--after' }, 'Depois'),
      this.handle,
      h('div', { class: 'loader', role: 'status', 'aria-live': 'polite' }, this.progress, this.progressLabel),
    );
    this.well = h('div', { class: 'stage-well' }, this.frame);

    const tool = (ic: string, label: string, shortcut: string, onclick: () => void) =>
      h(
        'button',
        { class: 'tool', type: 'button', title: `${label} (${shortcut})`, 'aria-pressed': 'false', onclick },
        icon(ic, 17),
        h('span', { class: 'tool-label' }, label),
        h('kbd', { class: 'tool-kbd', 'aria-hidden': 'true' }, shortcut),
      );
    this.btnCompare = tool(ICONS.split, 'Antes / depois', 'C', () => this.setCompare(!this.comparing));
    this.btnChecker = tool(ICONS.checker, 'Grade de teste', 'T', () => actions.onChecker());
    const btnLink = h(
      'button',
      { class: 'tool', type: 'button', title: 'Copiar link da configuração', onclick: () => actions.onCopyLink() },
      icon(ICONS.link, 17),
      h('span', { class: 'tool-label' }, 'Copiar link'),
    );

    this.memLabel = h('span', { class: 'dbg-mem' });
    const seg = h('div', { class: 'dbg-seg', role: 'radiogroup', 'aria-label': 'Modo de depuração' });
    for (const [mode, label] of DEBUG_MODES) {
      seg.append(
        h('button', { type: 'button', role: 'radio', 'aria-checked': String(mode === DebugMode.Off), 'data-mode': mode, onclick: () => this.setDebug(mode) }, label),
      );
    }
    this.debugBar = h(
      'div',
      { class: 'dbg', hidden: true },
      h('span', { class: 'dbg-title' }, icon(ICONS.scan, 15), 'Depuração'),
      seg,
      this.memLabel,
      h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Fechar depuração', onclick: () => this.toggleDebug(false) }, icon(ICONS.close, 15)),
    );

    this.toastEl = h('div', { class: 'toast', role: 'status', 'aria-live': 'polite' });

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
            icon(ICONS.chevron, 16),
          )
        : h('h1', { class: 'project-name' }, title.project);

    this.el = h(
      'main',
      { class: 'stage' },
      h(
        'header',
        { class: 'topbar' },
        h(
          'div',
          { class: 'topbar-id' },
          h('span', { class: 'logo', 'aria-hidden': 'true' }, h('span'), h('span')),
          h('span', { class: 'logo-word' }, 'Compose'),
          h('span', { class: 'topbar-sep', 'aria-hidden': 'true' }, '/'),
          projectEl,
          h('span', { class: 'cam-chip' }, icon(ICONS.camera, 14), title.camera),
        ),
        h('nav', { class: 'tools', 'aria-label': 'Ações do render' }, this.btnCompare, this.btnChecker, btnLink),
      ),
      this.well,
      this.debugBar,
      this.toastEl,
    );

    this.bindCompare();
    new ResizeObserver(() => this.layout()).observe(this.well);
  }

  setPoster(url: string, width: number, height: number): void {
    this.aspect = width / height;
    this.el.style.setProperty('--aspect', `${width} / ${height}`);
    this.poster.src = url;
    this.layout();
  }

  /** Encaixa o quadro no espaço disponível mantendo a proporção dos passes. */
  layout(): void {
    const r = this.well.getBoundingClientRect();
    if (!r.width || !r.height) return;
    let w = r.width;
    let hh = w / this.aspect;
    if (hh > r.height) {
      hh = r.height;
      w = hh * this.aspect;
    }
    this.frame.style.width = `${Math.floor(w)}px`;
    this.frame.style.height = `${Math.floor(hh)}px`;
    this.onResize?.(Math.floor(w), Math.floor(hh));
  }

  setProgress(loaded: number, total: number): void {
    const pct = total ? (loaded / total) * 100 : 0;
    this.progress.style.setProperty('--pct', `${pct}%`);
    this.progressLabel.textContent = total ? `Carregando passes ${loaded} de ${total}` : 'Preparando a cena…';
  }

  setReady(): void {
    this.frame.classList.remove('is-loading');
    this.frame.classList.add('is-ready');
  }

  setCheckerActive(on: boolean): void {
    this.btnChecker.setAttribute('aria-pressed', String(on));
  }

  // --- Comparador ----------------------------------------------------------------

  setCompare(on: boolean): void {
    this.comparing = on;
    this.frame.classList.toggle('is-comparing', on);
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
