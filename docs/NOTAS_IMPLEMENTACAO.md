# Notas de implementação

Descobertas feitas durante a construção (versões, APIs que não se comportaram como nos docs, decisões).

## Ambiente (2026-10-19)

- Python 3.14.4, Node 24.15, npm 11.12.
- **opencv-python 5.0.0 (pip) não tem escritor de OpenEXR** (`could not find a writer for the specified extension`).
  Fixado `opencv-python>=4.8,<5` em `tools/requirements.txt`; a 4.14 lê e grava EXR half com
  `OPENCV_IO_ENABLE_OPENEXR=1`.
- Web: three 0.186.1, vite 8.3.4, vitest 5.0.5, TypeScript 7.0.2, @playwright/test 1.64.1.
- `npm run lint` usa `tsc --noEmit` (sem ESLint, para não adicionar dependências fora do CLAUDE.md §2).
- Playwright roda o Chromium com `--use-angle=swiftshader` para ter WebGL2 em headless.

## Catálogo — extensões ao schema v2 (todas opcionais)

- `option.albedo_color: [r, g, b]` (linear): material de cor sólida, sem textura. O motor usa uma
  textura branca 1×1 e passa a cor como tint. Usado pela opção "Original do render" (0.35) e serve
  para tintas.
- `option.gloss_keep`: sobrescreve o `gloss_keep` do slot para aquela opção (ex.: mármore polido).
- `option.is_test: true`: a opção não aparece na grade; é acessada pelo botão "Material de teste".
- `option.finish`, `project_name`, `camera_name`: só texto para a interface.
- `light_groups[].kelvin` = temperatura **com que a luz foi renderizada**. O slider desloca a cor
  relativa a ela: `tint = RGB(T) / RGB(T_render)`, normalizado em luminância. Assim, com os valores
  do JSON, o LightMix é neutro e a imagem bate com o beauty.
- `pack_uv.py <exr> <pasta>/` (prefixo terminado em barra) grava `uv_hi.png`, `uv_lo.png`, `uv_meta.json`.
- `reconstruct_check.py`: PSNR calculado em linear com pico 1.0 (branco da tela).
