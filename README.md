# Compose — configurador 2.5D

Troca materiais (piso, parede, sofá…) sobre renders pré-calculados, direto no navegador.
A técnica é composição 2.5D: o render offline gera passes (beauty, luz difusa, reflexo, UV em
metros, máscaras) e um fragment shader WebGL2 re-projeta a textura nova sobre a imagem.

- Especificação de construção: [CLAUDE.md](CLAUDE.md)
- Referência técnica: [docs/Guia_ZYcompose_Unificado.md](docs/Guia_ZYcompose_Unificado.md)
- Descobertas e versões: [docs/NOTAS_IMPLEMENTACAO.md](docs/NOTAS_IMPLEMENTACAO.md)
- Protótipo antigo (só referência, não usar): [legacy/](legacy/)

## Requisitos

- Node 20+ e Python 3.10+.

## Comandos

```bash
# Python (uma vez)
python -m pip install -r tools/requirements.txt

# Web (uma vez)
cd web
npm install
npx playwright install chromium   # só para os testes e2e

# Desenvolvimento
npm run dev        # abre em http://localhost:5173
npm test           # testes unitários (Vitest)
npm run test:e2e   # testes de navegador (Playwright)
npm run lint       # checagem de tipos
npm run build      # build estático em web/dist

# Ferramentas
pytest tools
```

No Windows, `abrir_configurador.bat` e `gerar_assets_teste.bat` fazem o mesmo com dois cliques.

## Ver funcionando em 2 passos

```bash
python tools/make_test_assets.py   # gera a sala de teste + materiais + catálogo (~5 s)
cd web && npm run dev              # abre http://localhost:5173
```

Na tela: a sala sintética com piso de carvalho. No painel da direita, troque o acabamento,
a tonalidade, a escala/rotação e as luzes. Na barra de baixo: **Antes / depois** (arraste a
cortina), **Grade de teste** (checker 1 m), **Copiar link** (a URL guarda tudo) e **Baixar imagem**.

Atalhos: `C` comparador · `T` grade de teste · `D` painel de depuração (UV, máscaras, luz difusa,
costuras, albedo e memória de GPU estimada).

Os assets gerados não vão para o git (são reprodutíveis); rode o gerador depois de clonar.

## Como funciona (resumo)

| Peça | Arquivo |
| :--- | :--- |
| Shader de composição (WebGL2) | `web/src/engine/shaders/composite.frag.glsl` |
| Motor (texturas, uniforms, render sob demanda) | `web/src/engine/Compositor.ts` |
| Catálogo: tipos, validação, fallbacks | `web/src/catalog/schema.ts` |
| Estado + URL + orçamento | `web/src/state/` |
| Interface | `web/src/ui/` |
| Export PNG | `web/src/engine/export.ts` |
| Gerador da sala de teste | `tools/make_test_assets.py` |
| Empacotar UV / máscaras, validar | `tools/pack_uv.py`, `pack_masks.py`, `reconstruct_check.py`, `validate_catalog.py` |

## Biblioteca de materiais

`tools/material_library.json` define os materiais de cada tipo de superfície (piso, pedra, parede/tinta,
tecido, tapete, marcenaria). As texturas vêm da [Poly Haven](https://polyhaven.com) e da
[ambientCG](https://ambientcg.com), ambas CC0 (uso livre, inclusive comercial):

```bash
python tools/fetch_textures.py      # baixa (2K, ou 4K para texturas ≥ 2,5 m), converte e gera créditos
```

Para adicionar um material: inclua uma entrada em `materials` (id da Poly Haven ou ambientCG, nome, preço)
e o id na lista do tipo em `kinds`; rode o `fetch_textures.py` e reimporte a cena com o `import_corona.py`.
Tecidos com `"tintable"` perdem a cor da foto e ganham as cores da paleta (`palettes`).
