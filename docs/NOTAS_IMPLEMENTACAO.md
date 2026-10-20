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

## Primeira importação do Corona (cozinha_ilha / cam1) — 2026-10-19

3ds Max 2025.2, Corona (classes: CShading_RawComponent, CShading_SourceColor, CShading_Components,
CGeometry_UvwCoords, CMasking_Mask, CShading_LightSelect). Unidades da cena em cm; UV_config no canal 2
em metros (piso 8,41 × 6,14 m; parede 9,26 × 3,59 m). Resolução 2000×1500.

Problemas encontrados nos EXRs de `renders/cam1`:
- **masks_a preto**: o CMasking_Mask estava em `mode = 0` com os objetos nas listas `nodesR/G/B`
  (que só valem no modo por nós). Contorno: `tools/derive_masks.py` (máscara PROVISÓRIA: parede = albedo
  constante do reboco; piso = resto do UV abaixo de 60% da altura).
- **passes com tone mapping**: beauty máx 0,996, diff_light máx 0,977; reconstrução = 15 dB. Os EXRs
  saíram display-referred. Contorno: `--light-from-beauty` grava `luz = beauty / albedo^p`, com `p`
  (expoente da curva) estimado pelos detalhes finos do albedo (p = 0,572 nesta cena), e o shader faz
  `albedo_novo^p × luz` (`tone_mapping.relight_power`). Para o material original é identidade exata.
- **lg_interno vazio** (a malha LIGHT não contribui); Σ lg = 33 dB. O importador ignora grupos vazios.
- **ilha de mármore sem UV no canal 2** (preta no uv.exr): não dá para criar o slot.
- `cam1_output_*.exr` são cópias idênticas; o importador prefere `PREFIXO + elemento`.

Para um render definitivo: modo do CMasking_Mask por nós (ou G-Buffer ID), tone mapping neutro de verdade
(exposição 0, sem filmic/ACES/LUT, highlight compression 1) e UV_config na ilha.

## Sala de estar (sala_estar / cam7) — 2026-10-20

Renders em `renders/sala_estar` (3840×2160). Problemas:
- `masks_a/b/c.exr` **pretas** de novo (CMasking_Mask sem objetos efetivos no modo atual).
- A máscara substituta `renders/sala_estar/masks_a.png` **não é desta câmera**: só 39% (piso) e 49% (sofá)
  da borda coincidem com bordas da geometria (máscaras corretas: 78–98%). Resultado na tela: madeira sobre
  a base do sofá e a mesa de centro.
- `uv.exr` **cortado em [0, 1]** (p99 = 1,0 exato): escala de textura e áreas erradas (catálogo com
  `uv_range` [0,0,1,1] e área 0 m²).
- Todos os passes ≤ 0,99 (clamp/tone mapping) e `diff_color` constante ≈ 0,78 (material override "clay").

O importador agora mede o alinhamento máscara × geometria (`mask_alignment`: fração da borda do slot que
cai num SALTO do UV) e recusa abaixo de 60% (`--ignorar-alinhamento` para forçar), avisa abaixo de 75%,
e avisa quando o UV vem cortado em 1,0.
