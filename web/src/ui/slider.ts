import { h } from './dom';

export interface SliderOptions {
  id: string;
  label: string;
  min: number;
  max: number;
  step: number;
  value: number;
  /** Valor ao dar duplo clique (reset). */
  reset?: number;
  format: (v: number) => string;
  onInput: (v: number) => void;
  /** CSS do trilho (ex.: gradiente de temperatura). */
  track?: string;
  disabled?: boolean;
  hint?: string;
}

export interface Slider {
  el: HTMLElement;
  set(value: number): void;
  setDisabled(d: boolean): void;
}

/** Slider acessível: label visível, valor legível, aria-valuetext, duplo clique para resetar. */
export function slider(o: SliderOptions): Slider {
  const out = h('output', { class: 'sl-value', for: o.id });
  const input = h('input', {
    type: 'range',
    id: o.id,
    min: o.min,
    max: o.max,
    step: o.step,
    value: o.value,
    class: 'sl-input',
  });
  const paint = (v: number) => {
    out.textContent = o.format(v);
    input.setAttribute('aria-valuetext', o.format(v));
    const pct = ((v - o.min) / (o.max - o.min)) * 100;
    input.style.setProperty('--pct', `${pct}%`);
  };
  input.addEventListener('input', () => {
    const v = Number(input.value);
    paint(v);
    o.onInput(v);
  });
  if (o.reset !== undefined) {
    input.addEventListener('dblclick', () => {
      input.value = String(o.reset);
      paint(o.reset!);
      o.onInput(o.reset!);
    });
  }
  if (o.track) input.style.setProperty('--track', o.track);
  const el = h(
    'div',
    { class: `sl${o.track ? ' sl--custom' : ''}` },
    h('div', { class: 'sl-row' }, h('label', { for: o.id, class: 'sl-label' }, o.label), out),
    input,
    o.hint ? h('p', { class: 'sl-hint' }, o.hint) : null,
  );
  paint(o.value);
  const api: Slider = {
    el,
    set(v) {
      if (document.activeElement === input && Number(input.value) === v) return;
      input.value = String(v);
      paint(v);
    },
    setDisabled(d) {
      input.disabled = d;
      el.classList.toggle('is-disabled', d);
    },
  };
  if (o.disabled) api.setDisabled(true);
  return api;
}
