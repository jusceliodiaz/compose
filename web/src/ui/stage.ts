// Palco: o render ocupa a janela inteira; marca, projeto e ferramentas flutuam por cima.
import { DebugMode } from '../engine/Compositor';
import type { PanoView } from '../engine/panoramaView';
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

/** Vista 360°: o palco lê e muda a direção/zoom (arrastar, roda do mouse, pinça, setas). */
export interface PanoControl {
  get(): PanoView;
  set(v: Partial<PanoView>): void;
  /** O usuário começou a girar a vista. */
  onStart?(): void;
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
  private pano: PanoControl | null = null;
  /** O último gesto girou a vista: o clique que vem junto não seleciona superfície. */
  private dragged = false;
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
            'div',
            { class: 'project-tabs', role: 'tablist', 'aria-label': 'Vistas' },
            ...title.projects.map((p) =>
              h(
                'button',
                {
                  type: 'button',
                  role: 'tab',
                  'aria-selected': p.id === title.current ? 'true' : 'false',
                  class: `project-tab ${p.id === title.current ? 'project-tab--active' : ''}`,
                  onclick: () => {
                    if (p.id !== title.current) actions.onProject(p.id);
                  },
                },
                p.id === 'sala_estar_360' ? 'Panorama 360°' : (p.id === 'sala_estar' ? 'Câmera Principal' : p.name),
              ),
            ),
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
    if (!this.pano) this.el.style.setProperty('--aspect', `${width} / ${height}`);
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
    if (this.pano) {
      // 360: a "janela" para o panorama é a tela inteira
      this.frame.style.width = `${Math.round(r.width)}px`;
      this.frame.style.height = `${Math.round(r.height)}px`;
      this.onResize?.(Math.round(r.width), Math.round(r.height));
      return;
    }
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
      // no 360 arrastar a imagem gira a vista: a cortina só se move pela alça
      if (this.pano && !(e.target as Element).closest('.cmp-handle')) return;
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
      if (e.buttons) return hide(); // girando a vista
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
      if (this.dragged) {
        this.dragged = false;
        return;
      }
      if (this.comparing) return;
      hide(); // o rótulo do hover sai de cena quando o leque abre
      const [u, v] = uvOf(e);
      const s = this.el.getBoundingClientRect();
      this.actions.onPick(u, v, (e as PointerEvent).pointerType === 'touch', e.clientX - s.left, e.clientY - s.top);
    });
  }

  // --- Panorama 360° ------------------------------------------------------------------

  /** Liga o modo 360°: a imagem ocupa a tela e arrastar olha em volta. Chamar antes de setPoster. */
  enablePanorama(ctrl: PanoControl): void {
    if (this.pano) return;
    this.pano = ctrl;
    this.el.classList.add('is-pano');
    this.el.style.setProperty('--aspect', '4 / 3');
    this.bindPano(ctrl);
    this.layout();
  }

  private bindPano(ctrl: PanoControl): void {
    const pts = new Map<number, { x: number; y: number }>();
    let travel = 0;
    let pinch = 0;
    const spread = () => {
      const [a, b] = [...pts.values()];
      return a && b ? Math.hypot(a.x - b.x, a.y - b.y) : 0;
    };
    this.frame.addEventListener('pointerdown', (e) => {
      if (e.button !== 0 && e.pointerType === 'mouse') return;
      if ((e.target as Element).closest('.cmp-handle')) return;
      pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
      this.frame.setPointerCapture(e.pointerId);
      if (pts.size === 1) travel = 0;
      pinch = spread();
    });
    this.frame.addEventListener('pointermove', (e) => {
      const prev = pts.get(e.pointerId);
      if (!prev) return;
      const dx = e.clientX - prev.x;
      const dy = e.clientY - prev.y;
      pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
      const v = ctrl.get();
      if (pts.size >= 2) {
        const d = spread();
        if (pinch > 0 && d > 0) ctrl.set({ fov: v.fov * (pinch / d) });
        pinch = d;
        travel += 99;
        return;
      }
      // "agarrar a imagem": o ponto sob o dedo acompanha o dedo
      const radPerPx = ((v.fov * Math.PI) / 180) / Math.max(1, this.frame.clientHeight);
      travel += Math.abs(dx) + Math.abs(dy);
      if (travel > 5 && !this.dragged) {
        this.dragged = true;
        this.frame.classList.add('is-grabbing');
        ctrl.onStart?.();
      }
      if (this.dragged) ctrl.set({ yaw: v.yaw - dx * radPerPx, pitch: v.pitch + dy * radPerPx });
    });
    const end = (e: PointerEvent) => {
      if (!pts.delete(e.pointerId)) return;
      if (this.frame.hasPointerCapture(e.pointerId)) this.frame.releasePointerCapture(e.pointerId);
      pinch = spread();
      if (!pts.size) {
        this.frame.classList.remove('is-grabbing');
        // o click chega logo depois do pointerup; sem arrasto, ele seleciona a superfície normalmente
        if (!this.dragged) return;
        window.setTimeout(() => (this.dragged = false), 0);
      }
    };
    this.frame.addEventListener('pointerup', end);
    this.frame.addEventListener('pointercancel', end);
    this.frame.addEventListener(
      'wheel',
      (e) => {
        e.preventDefault();
        ctrl.set({ fov: ctrl.get().fov * Math.exp(e.deltaY * 0.0012) });
      },
      { passive: false },
    );
    window.addEventListener('keydown', (e) => {
      const t = e.target as HTMLElement;
      if (e.ctrlKey || e.metaKey || e.altKey || /^(INPUT|SELECT|TEXTAREA)$/.test(t.tagName) || t.getAttribute('role') === 'slider') return;
      const step = e.shiftKey ? 0.25 : 0.08;
      const v = ctrl.get();
      if (e.key === 'ArrowLeft') ctrl.set({ yaw: v.yaw - step });
      else if (e.key === 'ArrowRight') ctrl.set({ yaw: v.yaw + step });
      else if (e.key === 'ArrowUp') ctrl.set({ pitch: v.pitch + step });
      else if (e.key === 'ArrowDown') ctrl.set({ pitch: v.pitch - step });
      else if (e.key === '+' || e.key === '=') ctrl.set({ fov: v.fov / 1.15 });
      else if (e.key === '-') ctrl.set({ fov: v.fov * 1.15 });
      else return;
      e.preventDefault();
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
