// Liga catálogo, estado, motor, URL e interface.
import { loadCatalog } from '../catalog/loadCatalog';
import type { NormalizedCatalog } from '../catalog/schema';
import { Compositor } from '../engine/Compositor';
import { downloadBlob, exportImage, type ExportResult } from '../engine/export';
import { type ConfigState, Store } from '../state/store';
import { deserializeState, serializeState } from '../state/urlState';
import { h, icon, ICONS } from './dom';
import { Panel } from './panel';
import { Picker } from './picker';
import { QuickPick } from './quickpick';
import { Stage } from './stage';

const BASE = import.meta.env.BASE_URL;

export interface ProjectEntry {
  id: string;
  name: string;
  catalog: string;
}

/** Projeto atual: ?project= na URL → padrão do index.json → sala de teste. */
async function resolveProject(): Promise<{ id: string; url: string; projects: ProjectEntry[] }> {
  let projects: ProjectEntry[] = [];
  let def = 'test_room';
  try {
    const r = await fetch(`${BASE}assets/catalog/index.json`);
    if (r.ok) {
      const idx = (await r.json()) as { default?: string; projects?: ProjectEntry[] };
      projects = idx.projects ?? [];
      def = idx.default ?? def;
    }
  } catch {
    /* sem índice: segue com a sala de teste */
  }
  const asked = new URLSearchParams(location.search).get('project');
  // ?project= abre qualquer catálogo existente; a lista do índice só define o que aparece no menu
  const id = asked && /^[\w-]+$/.test(asked) ? asked : def;
  const entry = projects.find((p) => p.id === id);
  return { id, url: `${BASE}${entry?.catalog ?? `assets/catalog/${id}.json`}`, projects };
}

export interface ComposeDebugHandle {
  compositor: Compositor;
  store: Store;
  catalog: NormalizedCatalog;
  ready: Promise<void>;
  lastExport: ExportResult | null;
}

declare global {
  interface Window {
    __compose?: ComposeDebugHandle;
  }
}

export async function startApp(root: HTMLElement): Promise<void> {
  let catalog: NormalizedCatalog;
  const project = await resolveProject();
  try {
    catalog = await loadCatalog(project.url);
  } catch (e) {
    root.replaceChildren(errorScreen(e));
    return;
  }

  const store = new Store(deserializeState(location.search, catalog));
  const cam = catalog.cameras.find((c) => c.id === store.get().cam)!;
  const previousOption = new Map<string, string>();
  let compositor: Compositor;

  const stage = new Stage(
    {
      project: catalog.projectName,
      camera: cam.name,
      projects: project.projects,
      current: project.id,
    },
    {
      onProject: (id) => {
        location.search = `?project=${encodeURIComponent(id)}`;
      },
      onSplit: (x) => compositor?.setSplit(x),
      onTogglePanel: () => togglePanel(),
      onHover: (u, v) => {
        if (quick.isOpen) return null; // o leque está aberto: o destaque fica na superfície dele
        const slot = picker?.slotAt(u, v) ?? null;
        compositor?.setHover(slot?.id ?? null);
        return slot?.name ?? null;
      },
      onPick: (u, v, _touch, x, y) => {
        const slot = picker?.slotAt(u, v);
        if (!slot) {
          quick.close();
          return;
        }
        panel.selectSlot(slot.id, false);
        compositor.setHover(slot.id);
        const r = stage.el.getBoundingClientRect();
        quick.open(x, y, slot, store.get().slots[slot.id]!.option, { w: r.width, h: r.height });
      },
      onChecker: () => toggleChecker(),
      onCopyLink: () => void copyLink(),
      onDebug: (m) => {
        compositor?.setDebug(m);
        void reportMemory();
      },
    },
  );
  const panel = new Panel(catalog, store, {
    preload: (_slot, o) => compositor?.preload(o),
    onExport: () => void doExport(),
    onSurfaceHover: (id) => compositor?.setHover(id),
  });
  let picker: Picker | null = null;

  // leque de 3 opções ao clicar numa superfície (prévia ao vivo no hover)
  const quick = new QuickPick({
    onPreview: (o) => {
      const id = quick.slotId;
      if (!id) return;
      const cfg = store.get().slots[id]!;
      if (o) void compositor.setSlotMaterial(id, o.id, o.tintVariants[0]?.id ?? null);
      else void compositor.setSlotMaterial(id, cfg.option, cfg.variant);
    },
    onSelect: (o) => {
      const id = quick.slotId;
      if (id) store.setSlot(id, { option: o.id, variant: o.tintVariants[0]?.id ?? null });
    },
    onMore: () => {
      if (quick.slotId) panel.selectSlot(quick.slotId);
      togglePanel(true);
    },
    onClose: () => compositor?.setHover(null),
  });
  stage.el.append(quick.el);
  root.replaceChildren(stage.el, panel.el);
  stage.setPoster(cam.passes.beautyDisplay, cam.viewResolution[0], cam.viewResolution[1]);

  try {
    compositor = new Compositor(stage.canvas);
  } catch (e) {
    root.replaceChildren(errorScreen(e));
    return;
  }
  stage.onResize = (w, hh) => compositor.setSize(w, hh);
  stage.layout();

  const handle: ComposeDebugHandle = { compositor, store, catalog, ready: Promise.resolve(), lastExport: null };
  window.__compose = handle;

  // --- Estado → motor ------------------------------------------------------------
  async function apply(s: ConfigState, prev: ConfigState | null): Promise<void> {
    const jobs: Promise<void>[] = [];
    for (const [id, c] of Object.entries(s.slots)) {
      const p = prev?.slots[id];
      if (!p || p.option !== c.option || p.variant !== c.variant) {
        jobs.push(compositor.setSlotMaterial(id, c.option, c.variant));
      }
      if (!p || p.scale !== c.scale || p.rotation !== c.rotation || p.ox !== c.ox || p.oy !== c.oy) {
        compositor.setTransform(id, { scale: c.scale, rotationDeg: c.rotation, offset: [c.ox, c.oy] });
      }
    }
    for (const [id, l] of Object.entries(s.lights)) {
      const p = prev?.lights[id];
      if (!p || p.intensity !== l.intensity || p.kelvin !== l.kelvin) compositor.setLight(id, l);
    }
    if (!prev || prev.ev !== s.ev) compositor.setExposureEV(s.ev);
    syncChecker(s);
    await Promise.all(jobs);
  }

  let urlTimer = 0;
  function writeUrl(s: ConfigState): void {
    window.clearTimeout(urlTimer);
    urlTimer = window.setTimeout(() => {
      const q = `project=${encodeURIComponent(project.id)}&${serializeState(s, catalog)}`;
      history.replaceState(null, '', `${location.pathname}?${q}${location.hash}`);
    }, 120);
  }

  // --- Ações ---------------------------------------------------------------------
  function testOption(slotId: string) {
    return catalog.slots.find((s) => s.id === slotId)?.options.find((o) => o.isTest);
  }

  function toggleChecker(): void {
    const slotId = panel.slotId;
    const cur = store.get().slots[slotId];
    const test = testOption(slotId);
    if (!cur || !test) {
      stage.toast('Este catálogo não tem material de teste.', 'warn');
      return;
    }
    if (cur.option === test.id) {
      const back = previousOption.get(slotId) ?? catalog.slots.find((s) => s.id === slotId)!.defaultOption;
      const opt = catalog.slots.find((s) => s.id === slotId)!.options.find((o) => o.id === back)!;
      store.setSlot(slotId, { option: back, variant: opt.tintVariants[0]?.id ?? null });
    } else {
      previousOption.set(slotId, cur.option);
      store.setSlot(slotId, { option: test.id, variant: null });
      stage.toast('Grade de teste: 1 tile = 1 m, célula = 10 cm.');
    }
  }

  function syncChecker(s: ConfigState): void {
    const test = testOption(panel.slotId);
    stage.setCheckerActive(!!test && s.slots[panel.slotId]?.option === test.id);
  }

  async function copyLink(): Promise<void> {
    writeUrl(store.get());
    const url = `${location.origin}${location.pathname}?project=${encodeURIComponent(project.id)}&${serializeState(store.get(), catalog)}`;
    try {
      await navigator.clipboard.writeText(url);
      stage.toast('Link da configuração copiado.');
    } catch {
      window.prompt('Copie o link da configuração:', url);
    }
  }

  async function doExport(): Promise<void> {
    panel.setBusy(true);
    try {
      const r = await exportImage(compositor);
      handle.lastExport = r;
      const s = store.get();
      const opts = Object.values(s.slots).map((c) => c.option).join('-');
      downloadBlob(r.blob, `${catalog.projectId}_${s.cam}_${opts}_${r.width}x${r.height}.png`);
      if (r.note) stage.toast(r.note, 'warn', 6500);
      else stage.toast(`Imagem exportada em ${r.width}×${r.height}.`);
    } catch (e) {
      console.error(e);
      stage.toast(`Não foi possível exportar: ${(e as Error).message}`, 'warn', 6500);
    } finally {
      panel.setBusy(false);
      void reportMemory();
    }
  }

  async function reportMemory(): Promise<void> {
    stage.setMemory(await compositor.gpuMemoryMB(), compositor.renders);
  }

  function togglePanel(force?: boolean): void {
    const open = force ?? panel.el.classList.contains('is-hidden');
    panel.el.classList.toggle('is-hidden', !open);
    document.getElementById('app')?.classList.toggle('panel-hidden', !open);
    stage.setPanelOpen(open);
  }

  // --- Atalhos ---------------------------------------------------------------------
  window.addEventListener('keydown', (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const t = e.target as HTMLElement;
    if (t.tagName === 'INPUT' && (t as HTMLInputElement).type !== 'range') return;
    const k = e.key.toLowerCase();
    if (k === 'd') stage.toggleDebug();
    else if (k === 'c') stage.setCompare(!stage.isComparing);
    else if (k === 't') toggleChecker();
    else if (k === 'p') togglePanel();
    else if (k === 'escape') stage.toggleDebug(false);
  });

  // --- Carregamento ----------------------------------------------------------------
  handle.ready = (async () => {
    await compositor.setCamera(catalog, store.get().cam, (n, total) => stage.setProgress(n, total));
    await apply(store.get(), null);
    compositor.render();
    const pk = new Picker(catalog);
    pk.load().then(() => (picker = pk), (e) => console.warn('[compose] seleção por clique indisponível:', e));
    stage.setReady();
    store.subscribe((s, prev) => {
      void apply(s, prev);
      writeUrl(s);
    });
    const mb = await compositor.gpuMemoryMB();
    console.info(`[compose] memória de GPU estimada (texturas): ${mb.toFixed(1)} MB`);
    stage.setMemory(mb, compositor.renders);
  })();
  handle.ready.catch((e) => {
    console.error(e);
    root.replaceChildren(errorScreen(e));
  });
}

function errorScreen(e: unknown): HTMLElement {
  const msg = e instanceof Error ? e.message : String(e);
  const missing = /catálogo|404|Failed to fetch/i.test(msg);
  return h(
    'div',
    { class: 'empty' },
    h(
      'div',
      { class: 'empty-card' },
      h('span', { class: 'empty-icon' }, icon(ICONS.alert, 22)),
      h('h1', { class: 'empty-title' }, missing ? 'Nenhuma cena encontrada' : 'Algo deu errado'),
      h('p', { class: 'empty-text' }, missing ? 'Gere a sala de teste sintética e recarregue a página:' : msg),
      missing ? h('pre', { class: 'empty-code' }, 'python tools/make_test_assets.py') : null,
      missing ? h('p', { class: 'empty-small' }, msg) : null,
      h('button', { class: 'btn btn--primary', type: 'button', onclick: () => location.reload() }, icon(ICONS.rotate, 16), h('span', { class: 'btn-label' }, 'Recarregar')),
    ),
  );
}
