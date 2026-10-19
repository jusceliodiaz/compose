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

## Motor / web

- **Orientação (regra 7):** o `EXRLoader` do three 0.186 grava as linhas de baixo para cima com
  `flipY = false`; os PNGs usam `flipY = true` (padrão do `TextureLoader`). Resultado: mesma
  orientação. Provado no e2e `orientação` (361 pontos de `probes.json`) e no teste do checker
  (erro 3× menor que as hipóteses espelhadas/escala errada).
- **Sampler arrays:** GLSL ES 3.00 só aceita índice constante em `sampler2D[]`; por isso os 3 albedos e
  os 4 light groups são samplers separados, e o código por slot é chamado 3 vezes explicitamente.
- **Derivadas:** `dFdx/dFdy` do UV são calculadas em fluxo uniforme (fora dos `if`) e transformadas
  por slot (`R·(duv·S)`); a amostragem usa `textureGrad`. A GPU calcula derivadas em blocos 2×2,
  então pixels na borda da máscara têm "derivada de costura" — o teste de costuras olha só pixels com
  vizinhança 3×3 inteira dentro do piso.
- **LightMix neutro:** quando todos os grupos estão no valor do JSON, o shader usa o beauty direto
  (`u_lightMixOn = false`) — a identidade com o beauty fica exata, sem o erro de soma dos grupos.
- **Modo debug 5 (albedo):** mostra só o albedo do slot 0 em sRGB, sem luz; usado no teste do checker.
- **Escala no UI:** multiplicador sobre o tamanho físico (2× = textura 2× maior → `tiling / escala`).
  Offset em frações de tile (0–1).
- **Export:** sem `export_passes_prefix`, o PNG sai na resolução dos passes e a UI avisa que não é a
  resolução nativa. Com prefixo, cada passe é carregado como `prefixo + nome_do_arquivo`.
- Fontes da interface vêm do Google Fonts (Instrument Serif, Hanken Grotesk, IBM Plex Mono), com
  fallback de sistema se estiver offline.
