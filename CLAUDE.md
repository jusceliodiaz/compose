# CLAUDE.md — Construção do Configurador 2.5D (estilo ZYcompose)

Este arquivo é a especificação de construção do projeto. Leia-o inteiro antes de qualquer ação e siga os marcos **na ordem**. A referência técnica completa está em `docs/Guia_ZYcompose_Unificado.md`. Em caso de conflito, este arquivo vence.

---

## 1. Objetivo

Construir um configurador fotorrealista para navegador que troca materiais (piso, parede, sofá…) sobre renders pré-calculados. A técnica é composição 2.5D com passes (AOVs) e re-projeção por UV pass num fragment shader WebGL2.

**Entregável do MVP:**
- uma página web que carrega uma câmera;
- troca o material do piso entre pelo menos 2 opções;
- tem sliders de escala, rotação e LightMix;
- tem comparador antes/depois e estado na URL;
- exporta a imagem em alta resolução.

Além disso, as ferramentas Python e Blender que geram os assets dessa página.

**Importante:** o projeto precisa funcionar **antes** de existir qualquer render do Blender. Para isso, o Marco 1 gera assets sintéticos de teste.

---

## 2. Stack e decisões fixas (não mude sem perguntar)

| Item | Decisão |
| :--- | :--- |
| Web | Vite + TypeScript (strict) + `three` (versão estável atual, fixada no `package.json`) |
| WebGL | **WebGL2 / GLSL ES 3.00** com `RawShaderMaterial` + `glslVersion: THREE.GLSL3`. Sem fallback WebGL1 no MVP |
| UI | HTML/CSS puro + TypeScript (sem React no MVP) |
| Testes web | Vitest (funções puras) + Playwright (screenshot/smoke) |
| Ferramentas | Python 3.10+, `numpy`, `opencv-python` (com `OPENCV_IO_ENABLE_OPENEXR=1`), `pytest` |
| 3D (principal) | **3ds Max + Corona Renderer**. Passes via Render Elements do Corona, salvos como EXR separados (um arquivo por elemento). Automação via `pymxs` (Python dentro do 3ds Max) |
| 3D (opcional) | Blender 4.x, Cycles, scripts `bpy` executáveis com `blender -b arquivo.blend -P script.py` |
| EXR multilayer | Se algum EXR vier multilayer, ler com o pacote `OpenEXR` (permitido) |
| Unidade de UV | **metros** (1 UV = 1 m) |
| Codificação do UV | `u16_hilo`: 2× PNG 8-bit RGB (`_uv_hi.png`, `_uv_lo.png`) + `_uv_meta.json` com `uv_range` |
| Luz HDR | EXR half-float (PIZ ou ZIP) carregado via `EXRLoader` |
| Máscaras | PNG RGB lossless, 3 slots por arquivo |
| Tone mapping | Configurável no JSON (`standard` padrão no MVP; `aces` e `agx` como opções). Aplicado **só no final**, em linear até lá |
| Render | **Sob demanda** (só quando algo muda), nunca em loop contínuo |

---

## 3. Estrutura do repositório

```text
/
├─ CLAUDE.md
├─ docs/
│  └─ Guia_ZYcompose_Unificado.md
├─ tools/                      # Python
│  ├─ requirements.txt
│  ├─ make_test_assets.py      # Marco 1
│  ├─ pack_uv.py               # Marco 2
│  ├─ pack_masks.py
│  ├─ reconstruct_check.py
│  ├─ validate_catalog.py
│  ├─ make_checker.py
│  └─ tests/
├─ max/                        # 3ds Max + Corona (pymxs) — Marco 3
│  ├─ setup_corona_elements.py
│  ├─ render_data_pass.py
│  └─ README_corona.md
├─ tools/import_corona.py      # Marco 3: EXRs do Corona → estrutura web
├─ blender/                    # bpy (opcional, Marco 3b)
│  ├─ setup_passes.py
│  ├─ render_data_pass.py
│  └─ export_camera.py
├─ web/
│  ├─ package.json, vite.config.ts, tsconfig.json, index.html
│  ├─ public/assets/
│  │  ├─ scenes/<project_id>/<camera>/...   # passes
│  │  ├─ materials/...                      # albedos + thumbs
│  │  └─ catalog/<project_id>.json
│  ├─ src/
│  │  ├─ main.ts
│  │  ├─ engine/
│  │  │  ├─ Compositor.ts      # renderer, quad, uniforms, render()
│  │  │  ├─ loaders.ts         # loadData / loadHDR / loadAlbedo
│  │  │  ├─ shaders/composite.vert.glsl
│  │  │  ├─ shaders/composite.frag.glsl
│  │  │  └─ export.ts          # export em alta resolução
│  │  ├─ catalog/
│  │  │  ├─ schema.ts          # tipos + validação + fallbacks
│  │  │  └─ loadCatalog.ts
│  │  ├─ state/
│  │  │  ├─ store.ts           # estado da configuração
│  │  │  └─ urlState.ts        # serializar/deserializar URL
│  │  ├─ ui/                   # painel, sliders, comparador
│  │  └─ util/
│  │     ├─ kelvin.ts          # Kelvin → RGB linear normalizado
│  │     └─ uvDecode.ts        # espelho JS do decodeUV (para testes)
│  └─ tests/                   # vitest + playwright
└─ README.md
```

---

## 4. Regras técnicas obrigatórias

Violar qualquer uma destas regras é bug.

1. **Passes de dados** (UV hi/lo, máscaras):
   - `colorSpace = NoColorSpace`, `NearestFilter` em min e mag, `generateMipmaps = false`;
   - PNG sem ICC e sem gAMA (gravar com OpenCV);
   - nunca usar formato com perdas.
2. **Albedo dos materiais:** `SRGBColorSpace`, `RepeatWrapping`, mipmaps ligados e anisotropia máxima.
3. **Passes de luz** (beauty linear, diffuse light, glossy, light groups): EXR half-float, `LinearFilter`, sem mipmaps.
4. **Nada de `fract()`** na amostragem do albedo. Use `REPEAT` + `textureGrad` com derivadas zeradas acima de `u_seamThreshold`.
5. **Ordem da transformação:** `tuv = R(θ) · (uv · S) + O`, com `mat2(c, s, -s, c)`.
6. **Composição em linear:** `shaded = albedo * diffLight + glossy * glossKeep`, depois `mix(beauty, shaded, mask)`. Em seguida exposição → tone map → sRGB, nessa ordem e só no final. `renderer.outputColorSpace = LinearSRGBColorSpace`, porque o shader já converte.
7. **`flipY` consistente:** o `EXRLoader` vem com `flipY = false`. Garanta que todos os passes fiquem na mesma orientação e prove isso com um teste visual (checker).
8. **Fallbacks do catálogo** (ver docs, Seção 6.3):
   - sem `uv_hi`/`uv_lo` → usar `uv_map` 8-bit;
   - sem `texture_size_m` → usar `default_tiling`;
   - sem `diffuse_light` → `shaded = albedo * shadow_ao * (cor média do beauty)`, com uma nota de modo "simplificado" no console.
9. **Memória:** `dispose()` de texturas ao trocar de câmera e depois do export; `setPixelRatio(Math.min(devicePixelRatio, 2))`.
10. **Export:**
    - checar `renderer.capabilities.maxTextureSize` antes;
    - se houver `export_passes_prefix`, carregar os passes de export sob demanda;
    - renderizar num `WebGLRenderTarget`, ler com `readRenderTargetPixels`, copiar para um canvas 2D, gerar com `toBlob()`.

---

## 5. Marcos (execute em ordem; ao fim de cada um, rode os testes e faça um commit)

### Marco 0 — Esqueleto
- Criar a estrutura do item 3, `web/` com Vite + TS + three, `tools/requirements.txt` e o README com os comandos.
- Scripts npm: `dev`, `build`, `test`, `test:e2e`, `lint`.
- **Aceite:** `npm run dev` abre uma página com um canvas preto e o `npm test` passa (com 1 teste trivial).

### Marco 1 — Assets sintéticos de teste (`tools/make_test_assets.py`)
Gerar uma "câmera falsa" fisicamente coerente, sem Blender. O resultado é uma vista em perspectiva de um piso plano:

- **Cena:** câmera em (0, 1.6, 0), olhando para baixo a 35°, FOV vertical de 50°, imagem 1920×1080. Piso no plano y=0, retângulo de 6.2 m × 4.8 m à frente da câmera.
- **Por pixel:** interseção raio–plano.
  - Dentro do retângulo: `mask = 1` e `uv = (x - x0, z - z0)` em metros.
  - Fora: `mask = 0`, e o beauty recebe um gradiente de "parede/céu".
- **`diff_light` (EXR):**
  - luz de "janela" com queda suave a partir de uma das bordas;
  - uma sombra suave em forma de blob (sofá imaginário);
  - um termo indireto constante;
  - valores HDR de até ~3.0.
- **`glossy` (EXR):** reflexo fraco e alongado da janela (0–0.2).
- **`diff_color`:** albedo original constante (cinza-bege linear ~0.35).
- **`beauty` (EXR linear):** `diff_color * diff_light + glossy`, e o fundo onde `mask = 0`. Gerar também o `beauty.webp` com o mesmo tone mapping do JSON, para a exibição inicial.
- **2 light groups** (`lg_sun`, `lg_ceiling`), cuja soma seja exatamente igual ao beauty.
- **UV:** salvar `uv.exr` (R = U, G = V) para alimentar o `pack_uv.py`.
- **Máscaras:** `masks_a.png` com R = piso.
- **Materiais:** gerar `make_checker.py` (grade numerada, 1 célula = 10 cm, 1 m por tile) e 2 albedos procedurais (madeira em régua de 1.2 × 0.2 m e "mármore" de 1.2 × 1.2 m), com thumbs de 256 px.
- Saída em `web/public/assets/scenes/test_room/cam_main/` e `.../materials/`.
- **Aceite:**
  - `pytest` confirma que a reconstrução bate (erro máximo < 1e-3);
  - os light groups somam ≈ beauty;
  - o `uv_range` fica perto de `[0, 0, 6.2, 4.8]`.

### Marco 2 — Ferramentas de conversão e validação
- `pack_uv.py <uv.exr> <prefixo>`: gera `_uv_hi.png`, `_uv_lo.png` e `_uv_meta.json`. Partir do script da Seção 5.4 dos docs, adicionando argparse, validação de entrada e mensagens claras.
- `pack_masks.py`: junta até 3 máscaras P/B num PNG RGB e grava o mapeamento de canais.
- `reconstruct_check.py`: recebe os EXRs e calcula o erro entre a reconstrução e o Combined (máximo, médio, PSNR). Sai com código ≠ 0 se o PSNR for menor que 40 dB.
- `validate_catalog.py`: valida o JSON (arquivos existem, canais únicos, `uv_range` coerente com o meta, `schema_version`).
- Gerar `web/public/assets/catalog/test_room.json` no schema v2 (docs, Seção 6.2).
- **Aceite:**
  - teste de ida e volta do `pack_uv`: decodificar hi/lo em numpy reproduz o UV com erro ≤ (range/65535);
  - todos os validadores passam nos assets sintéticos.

### Marco 3 — Pipeline 3ds Max + Corona (`max/` e `tools/import_corona.py`)

Mapa de Render Elements do Corona → arquivos do projeto. Os nomes de arquivo usam o **nome dado ao elemento** no 3ds Max, então padronize os nomes abaixo:

| Nome do elemento (renomear assim) | Tipo de elemento Corona | Arquivo/uso no projeto |
| :--- | :--- | :--- |
| (beauty, saída principal) | — | `beauty.exr` (linear) + `beauty.webp` |
| `diff_light` | `CShading_RawComponent` → Diffuse | `diff_light.exr` (luz sem a cor) |
| `diff_color` | `CShading_SourceColor` → Diffuse | `diff_color.exr` (albedo original; validação) |
| `reflect` | `CShading_Components` → Reflection | `glossy.exr` |
| `refract`, `transl`, `emission`, `sss`, `volum` | `CShading_Components` → Refraction / Translucency / Emission / SSS / Volumetric | Só para o teste de reconstrução |
| `uv` | `CGeometry_UvwCoords`, map channel **2** (o `UV_config`) | `uv.exr` → `pack_uv.py` |
| `masks_a` (`masks_b`…) | `CMasking_Mask`, com objetos nos canais R/G/B | `masks_a.png` (já empacotada, 3 slots) |
| `lg_<nome>` | `CESSENTIAL_LightSelect` (um por grupo do LightMix) | `lg_<nome>.exr` |

Tarefas:
- `max/setup_corona_elements.py` (pymxs, roda pelo *Scripting → Run Script* do 3ds Max):
  - cria os elementos da tabela com os nomes certos, sem duplicar os que já existem;
  - configura a saída EXR half-float, linear e sem tone mapping, um arquivo por elemento, em `renders/<camera>/`;
  - desliga DoF e motion blur na câmera ativa;
  - recebe parâmetros no topo do script (câmera, pasta, objetos de cada canal da máscara).
- `max/render_data_pass.py`: segundo render só para `uv` e `masks_*`, com o filtro de imagem no mínimo e poucas passes, restaurando a configuração ao final.
- **Os nomes de classe e de propriedade dos elementos variam entre versões do Corona.** O script deve:
  - listar as classes disponíveis (`rt.renderElementManager` / `showClass "CShading*"`);
  - falhar com uma mensagem clara se faltar alguma;
  - registrar a versão encontrada em `docs/NOTAS_IMPLEMENTACAO.md`.
- `tools/import_corona.py <pasta_renders> <projeto> <camera>`:
  1. encontra os EXRs pelo nome;
  2. roda o `pack_uv.py` e converte a máscara para PNG;
  3. gera o `beauty.webp`;
  4. roda o `reconstruct_check.py` com `beauty ≈ Σ Components` (diffuse = diff_color × diff_light);
  5. copia tudo para `web/public/assets/scenes/<projeto>/<camera>/` e atualiza o catálogo JSON.
- `max/README_corona.md`: passo a passo manual equivalente, para quando o script não rodar.
- **Aceite:**
  - `import_corona.py` roda sem erro nos assets sintéticos renomeados no padrão Corona (crie um teste que simula essa pasta);
  - os scripts pymxs compilam (`python -m py_compile`);
  - se o 3ds Max estiver disponível, o usuário roda o script e confirma.

### Marco 3b (opcional) — Scripts Blender (`blender/`)
- `setup_passes.py`, que configura a cena aberta:
  - Cycles; passes UV, Object Index, Diffuse D/I/C, Glossy D/I/C, Emission, Environment e Denoising Data;
  - cria um light group por coleção `LG_*`;
  - um File Output EXR half (multilayer) para os dados e a luz;
  - um nó Denoise nos passes de luz;
  - view transform conforme o argumento (`--view standard|agx`).
- `render_data_pass.py`: render de dados com Pixel Filter 0.01, 16 amostras, DoF e motion blur desligados, restaurando as configurações ao final.
- `export_camera.py`: roda os dois renders, separa os passes, chama `tools/pack_uv.py`/`pack_masks.py` e grava na estrutura de `web/public/assets/scenes/<projeto>/<camera>/`.
- Os scripts precisam detectar `bpy.app.version`. Se for 5.x e algum nome de API mudar, falhe com uma mensagem clara em vez de adivinhar. Comente cada chamada de API que muda entre versões.
- **Aceite:** dá para rodar em modo background sem erro de sintaxe (`blender -b --python-expr "import ast; ..."`, ou pelo menos `python -m py_compile`). Se o Blender estiver instalado, rode `blender -b -P blender/setup_passes.py` numa cena vazia gerada pelo próprio script de teste.

### Marco 4 — Motor de composição (web)
- `loaders.ts` com as três funções da Seção 4.4 dos docs, mais `loadRGBM` (opcional).
- `composite.frag.glsl`: o shader de produção da Seção 4.2 dos docs, com estas extensões:
  - **até 3 slots** num único passe (arrays de uniforms: albedo, tint, tiling, rotation, offset, glossKeep, slotSelect);
  - **LightMix** com até 4 grupos e o método da razão (Seção 4.5);
  - tone mapping selecionável (`standard` = só clamp, `aces`, `agx` — usar a implementação AgX do Three.js como referência).
- `Compositor.ts`:
  - `setCamera(catalog, cameraId)`, `setSlotMaterial(slotId, optionId)`, `setTransform(slotId, {scale, rotationDeg, offset})`, `setLight(groupId, {intensity, kelvin})`, `render()`;
  - `render()` só é chamado quando o estado muda (com debounce por `requestAnimationFrame`).
- `uvDecode.ts`: espelho em JS do `decodeUV`, com teste no Vitest.
- **Aceite:**
  - com o material = albedo original (cor constante 0.35) e o LightMix neutro, a imagem final é igual à do beauty sem alteração (teste Playwright com diferença de pixel < 2/255);
  - o checker aparece com 1 tile por metro, sem espelhamento e sem costuras.

### Marco 5 — Interface
- Painel lateral: lista de slots → miniaturas dos materiais → variantes de tint.
- Sliders: escala (multiplicador 0.5–2.0, respeitando `allow_user_transform`), rotação 0–360°, offset X/Y.
- Sliders de LightMix: intensidade (`range` do JSON) e Kelvin (2700–6500 K).
- Comparador antes/depois: cortina arrastável no próprio shader (uniform `u_splitX`).
- Estado na URL, por exemplo `?cam=cam_main&floor=marble&floor.rot=90&floor.s=1.2&sun=1.4&sun.k=5600`. Restaurar ao carregar e atualizar com `history.replaceState`.
- Orçamento: `area_m2 × price.value` por slot, com total.
- Botão "Material de teste (checker)".
- Funcionar bem em celular (painel recolhível, toque na cortina).
- **Aceite:** testes do `urlState` (ida e volta) e do `kelvin.ts` no Vitest; teste Playwright que muda o material pela URL e confere o screenshot.

### Marco 6 — Export em alta resolução
- Botão "Baixar imagem". Resolução de `resolution.export`, limitada por `maxTextureSize` (com fallback de 2K).
- Se houver `export_passes_prefix`, carregar esses passes, renderizar e depois `dispose()`. Caso contrário, renderizar na resolução dos passes e avisar na UI que não é 4K nativo.
- **Aceite:** o arquivo PNG gerado tem a resolução esperada e o conteúdo é igual ao canvas (Playwright).

### Marco 7 — Polimento e performance
- Carregamento progressivo: beauty WebP primeiro, com indicador de carregamento; o restante em paralelo; albedos só quando o slot é aberto.
- Cache com nomes versionados no build.
- Overlay de debug (tecla `D`): mostra o UV decodificado, a máscara, a diffuse light e as derivadas/costuras.
- README final: como gerar assets sintéticos, como exportar do Blender, como adicionar um material e como fazer o deploy estático.
- **Aceite:** Lighthouse/perf sem erros graves; memória de GPU estimada no console (somar texturas).

---

## 6. Como trabalhar

- **Um marco por vez.** No início de cada marco, escreva um plano curto (arquivos, funções, testes). No fim, mostre o resultado dos testes e um resumo de 3–5 linhas.
- **Não pule testes.** Se um aceite não for automatizável, descreva como verificar manualmente e peça confirmação ao usuário.
- **Dependências:** só as do item 2. Para adicionar qualquer outra, pergunte antes.
- **Erros:** se uma API (three, bpy) não se comportar como descrito aqui ou nos docs, verifique a versão instalada e a documentação. Ajuste o código, não as regras do item 4, e registre a descoberta em `docs/NOTAS_IMPLEMENTACAO.md`.
- **Commits** pequenos, com mensagens em português (`M1: gerador de assets sintéticos`).
- **Não use** `fract()` na amostragem, nem PNG 16-bit para UV, nem matemática de cor em sRGB, nem loop de render contínuo.
- O usuário está aprendendo. Ao terminar cada marco, explique em linguagem simples o que foi construído e como ele pode ver o resultado (comando + o que deve aparecer na tela).

---

## 7. Definição de pronto do MVP

- [ ] `python tools/make_test_assets.py` e `npm run dev` mostram a sala de teste.
- [ ] O piso troca entre checker, madeira e mármore na hora, com a escala física correta.
- [ ] Sliders de escala, rotação, offset e LightMix funcionando; comparador antes/depois; URL compartilhável; orçamento.
- [ ] A imagem com o material original é idêntica ao beauty (teste automático).
- [ ] O export gera um PNG na resolução configurada.
- [ ] Os scripts do Blender existem, compilam e estão documentados.
- [ ] `npm test`, `npm run test:e2e` e `pytest tools` passam.
