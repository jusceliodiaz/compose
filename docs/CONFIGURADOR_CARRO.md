# Configurador de Carro 2.5D — Especificação-base

Documento-base para um projeto novo: um configurador de carro no navegador, com imagens fotorrealistas
pré-renderizadas no **3ds Max + Corona** e troca de materiais/opções em tempo real.

Herda a técnica e as lições do configurador de ambientes (projeto `compose`). Pode ser usado como o
`CLAUDE.md` do novo repositório. Itens marcados **[verificar]** dependem da versão do Corona e precisam ser
confirmados no primeiro protótipo.

---

## 1. Objetivo

Uma página web onde o cliente:

- **gira o carro** arrastando (giro externo de 360°);
- abre **closes** de rodas, acessórios e interior;
- troca **pintura, rodas, pinça de freio, acabamentos e interior** com resultado fotorrealista;
- vê o **orçamento** e baixa a **imagem em alta resolução**;
- compartilha a configuração por **link**.

Volume previsto: **~360 imagens/vistas**, metade de giro externo e metade de closes. Nos closes de acessório
há **desfoque de profundidade (DoF)**; no giro, não.

---

## 2. Decisão central: três maneiras de variar uma opção

Cada opção do configurador entra em **uma** destas categorias. Decidir isso por opção, antes de renderizar,
é o que define o custo do projeto.

| Tipo | Quando usar | Como funciona | Exemplos |
| :--- | :--- | :--- | :--- |
| **A. Troca de material (2.5D)** | Mesma geometria, superfície mais fosca ou de reflexo simples | Passes de luz + máscara + UV em metros; o shader reilumina a textura nova | Couro/tecido dos bancos, costura, painel, carpete, pinça, cor da roda, pintura **sólida** |
| **B. Camada (layer)** | A opção muda a **geometria** | Cada opção é renderizada isolada (com alfa e sombra) e empilhada | Desenho de roda, aerofólio, rack, estribo, retrovisor |
| **C. Variante pré-renderizada** | Material de reflexo complexo, ou poucas combinações | Render completo de cada variante | Pinturas **metálicas/perolizadas/foscas especiais** (se o tipo A não ficar bom), faróis acesos |

Regra prática: **tipo A sempre que der**, porque não multiplica renders. **Tipo B** para geometria. **Tipo C**
só para o que o protótipo provar que não fica bom no A.

---

## 3. Stack (reaproveitar do `compose`)

| Item | Decisão |
| :--- | :--- |
| Web | Vite + TypeScript (strict) + `three` (WebGL2, `RawShaderMaterial`, GLSL3) |
| UI | HTML/CSS + TS, sem framework; mesmo design system (tela cheia, cartões claros, Host Grotesk) |
| Testes | Vitest (funções puras) + Playwright (screenshots, export, interação) |
| Ferramentas | Python 3.10+, `numpy`, `opencv-python<5` (o 5.0 do pip veio **sem** EXR), `pytest` |
| 3D | 3ds Max + Corona; automação por `pymxs`/MAXScript (e MCP do Max, se disponível) |
| Texturas | Poly Haven / ambientCG (CC0), baixadas por script com a medida física real |

Reaproveitar do `compose` (copiar e adaptar): motor de composição (`Compositor.ts`, shader), loaders,
`schema.ts`, estado/URL, `import_corona.py`, `edge_clean.py`, `tone_curve.py`, `fetch_textures.py`,
`pack_uv.py`, `validate_catalog.py`, `replace_beauty.py`, leque de opções e seleção clicando na imagem.

---

## 4. Vistas e câmeras

### 4.1 Giro externo
- **36 quadros (10°) já giram suave** arrastando; **72 (5°)** para giro premium. 180 quadros só se houver
  motivo forte: o custo de render, peso e memória cresce linearmente.
- Rig no Max: câmera presa a um *dummy* no centro do carro, girando em torno do eixo vertical; mesma altura,
  mesma lente, mesma luz em todos os quadros. **Animação de 1 quadro por vista** = render em lote simples.
- Iluminação **fixa no mundo** (o carro gira em relação à luz → reflexos "andam", que é o realismo esperado).
  Alternativa: girar o carro e manter câmera e luz fixas — decidir no protótipo.

### 4.2 Closes
- Rodas, acessórios, detalhes de interior: câmeras nomeadas (`close_roda_dianteira`, `close_aerofolio`…).
- DoF **não** é renderizado (ver seção 7). O foco e a intensidade do desfoque ficam no catálogo, por close.

### 4.3 Nomenclatura
```
renders/<carro>/<vista>/<vista>_<elemento>.exr
  ex.: renders/suv_x/spin_000/spin_000_beauty.exr, spin_000_masks_a.exr, spin_000_uv.exr …
       renders/suv_x/close_roda_d/close_roda_d_layer_roda_aro20_beauty.exr …
```

---

## 5. Render no 3ds Max + Corona — regras obrigatórias

Estas regras vêm de erros reais do projeto `compose`. Quebrar qualquer uma delas custou um re-render.

1. **Tone mapping NEUTRO no Corona**: exposição 0, highlight compression 1, sem Filmic, ACES, LUT,
   contraste, saturação ou curvas. Os EXRs têm que sair **lineares**. Sinal de erro: beauty e passes
   **parando em ~1,0** e a reconstrução abaixo de 40 dB. O "look" (contraste, cor) é aplicado na web,
   igual para tudo.
2. **EXR half float** (o `uv` e o `zdepth` em **full float**), ZIP ou PIZ, **um arquivo por elemento**,
   todos na mesma resolução e sem crop/região de render.
3. **Desligar** DoF e motion blur em todos os renders (beleza e dados).
4. **Máscaras por Object ID**: `Object Properties → G-Buffer → Object ID` em cada peça trocável, e o
   `CMasking_Mask` **no modo Object ID** com R/G/B = os IDs. Lição: o elemento estava em modo ID com objetos
   na lista de "nós" → máscara **toda preta**. Testar num render pequeno antes do lote.
5. **UV em metros no canal 2** (`UVW Map` no topo da pilha, nome `UV_config`, Map Channel 2). Planar:
   tiles = medida em metros. Box: 100 cm, tile 1. O canal 1 é das texturas originais — não mexer.
   Conferir no configurador com a **grade de teste** (1 quadrado = 1 m).
6. **Material override desligado** (render "clay" só para teste).
7. **Dois renders por vista**: (a) beleza e luz com qualidade final e denoiser; (b) dados (UV, máscaras,
   Z) com filtro de imagem mínimo, ~16 passes, sem denoiser.
8. **Grupos de luz (LightSelect)**: cada luz em exatamente um grupo, mesma exposição; a soma deve bater
   com o beauty.
9. **Nada de pós-processamento por IA no beauty** que for usado na troca (Magnific etc.): a IA move bordas
   e muda materiais. Se usar, é como imagem base retocada, aceitando os limites (ver 12.9).

### 5.1 Elementos de render por vista (tipo A)

| Nome | Elemento Corona | Uso |
| :--- | :--- | :--- |
| `beauty` | saída principal | imagem base (linear) |
| `diff_light` | `CShading_RawComponent` → Diffuse | luz difusa (reiluminação) |
| `diff_color` | `CShading_SourceColor` → Diffuse | albedo original (validação, curva) |
| `reflect` | `CShading_Components` → Reflection | reflexo |
| `refract`, `transl`, `emission`, `sss`, `volum` | `CShading_Components` | reconstrução (vidro, faróis) |
| `uv` | `CGeometry_UvwCoords`, canal 2 | UV em metros |
| `masks_a`, `masks_b`… | `CMasking_Mask` (Object ID) | onde está cada peça trocável |
| `zdepth` | Z-depth do Corona **[verificar nome]** | desfoque na web (closes) |
| `lg_<grupo>` | `CShading_LightSelect` | LightMix (opcional) |

### 5.2 Pintura (o ponto mais delicado)

A pintura de carro = **base colorida** (difusa e/ou metálica) + **verniz** (clearcoat, reflexo quase
incolor). Para trocar a cor:

- **Sólida**: `cor nova × diff_light + reflexo do verniz`. Funciona com os passes da 5.1, desde que o reflexo
  do verniz venha separado do reflexo da base **[verificar se o Corona separa clearcoat em componente
  próprio]**. Se não separar: renderizar o carro com a pintura em **cinza neutro** — o `reflect` passa a ser
  quase só o verniz.
- **Metálica/perolizada**: o brilho da base assume a cor da tinta. Opções, em ordem de preferência:
  1. passe extra só do reflexo da base, renderizado com base **branca** → na web, multiplica pela cor
     (`cor × reflexo_base_branco + verniz`);
  2. variante pré-renderizada (tipo C) por cor metálica.
- Decidir no protótipo comparando lado a lado com um render real de cada pintura.

### 5.3 Camadas (tipo B: rodas, acessórios)

Para cada opção de geometria, em cada vista onde aparece:
- render **só da peça** com **alfa** (fundo transparente), mesma câmera e luz;
- **sombra/oclusão da peça no carro e no chão** num passe próprio (shadow catcher / *matte* com sombra)
  **[verificar recurso exato no Corona]**;
- se a peça tiver troca de material (cor da roda, da pinça), ela recebe também os passes da 5.1 (máscara, UV,
  luz) **da camada**.
- Na web: `base sem a peça` → multiplica a sombra da opção → compõe a peça (alfa pré-multiplicado).
  Isso exige que o beauty base seja renderizado **sem nenhuma opção** daquela categoria (ex.: carro sem
  rodas, ou com a roda "padrão" como mais uma camada).

---

## 6. Formatos e orçamento de dados

Referência medida no `compose`: **uma vista 4K com todos os passes ≈ 100 MB**. Com 360 vistas,
isso não cabe; o plano:

| Uso | Resolução | Formato | Peso alvo |
| :--- | :--- | :--- | :--- |
| Giro (imagens que trocam ao arrastar) | 1600–1920 px | WebP/AVIF da configuração atual | 150–300 KB por quadro |
| Passes da vista parada (troca de material) | 1920×1080 | EXR half ZIP / PNG (dados) | 8–15 MB por vista |
| Export | 4K | passes 4K carregados sob demanda (`export_passes_prefix`) | só no "Baixar imagem" |

Estratégia de carregamento:
1. Ao abrir: quadros do giro **da configuração padrão** (leves), vista inicial com passes completos.
2. Durante o giro: só imagens leves. **Ao parar** numa vista: carrega os passes dela e mostra a configuração
   atual composta.
3. Para o giro já refletir a configuração escolhida sem passes: gerar no navegador uma "miniatura composta"
   por quadro, em segundo plano, a partir de passes de **baixa resolução** (ex.: 640 px).
4. `dispose()` de texturas de vistas que saíram de cena; memória de GPU estimada no painel de debug.

Limite do shader: **16 texturas** por passe de desenho no WebGL2 (mínimo garantido). Planejar slots,
camadas e grupos de luz dentro disso; camadas extras = mais passes de desenho num render target.

---

## 7. Desfoque (DoF) só nos closes de acessório

- **Não** renderizar DoF: ele mistura pixels vizinhos e a máscara/UV deixam de bater (lição do `compose`).
- Renderizar o close **nítido + passe de profundidade (Z)**.
- Na web, **depois** da troca de materiais: desfoque por *círculo de confusão* a partir do Z
  (foco, abertura e distância no catálogo, por close). Implementação: 1 passe de *bokeh* aproximado
  (amostragem em disco com peso pela diferença de profundidade, para não "vazar" o fundo na frente).
- O export usa o mesmo desfoque.
- Aceite: borda de objeto em foco sobre fundo desfocado sem halo; nenhum desfoque nas vistas de giro.

---

## 8. Catálogo (extensão do schema v2 do `compose`)

```jsonc
{
  "schema_version": 3,
  "project_id": "suv_x",
  "views": [
    { "id": "spin_000", "kind": "spin", "angle_deg": 0, "passes": { /* base_passes do v2 */ },
      "preview": "assets/suv_x/spin/spin_000_{config}.webp" },
    { "id": "close_roda_d", "kind": "close", "passes": { /* … */ },
      "dof": { "zdepth": "…/close_roda_d_zdepth.exr", "focus_m": 1.2, "fstop": 2.8 } }
  ],
  "options": {
    "pintura": { "type": "material", "slot": "carroceria", "choices": [ /* sólidas: cor; metálicas: variant */ ] },
    "rodas":   { "type": "layer", "choices": [ { "id": "aro20", "layers": { "spin_000": "…", "close_roda_d": "…" } } ] },
    "pinca":   { "type": "material", "slot": "pinca", "choices": [ /* cores */ ] },
    "banco":   { "type": "material", "slot": "banco", "choices": [ /* couro, tecido… */ ] }
  },
  "rules": [ { "if": { "pacote": "sport" }, "force": { "rodas": "aro21" } } ],
  "price": { "base": 189900, "currency": "BRL" }
}
```

- **`rules`**: dependências entre opções (pacotes, incompatibilidades).
- Preço por **opção** (não por m², como na arquitetura).
- `quick_options` e "voltar ao original" continuam valendo por superfície (leque ao clicar na imagem).

---

## 9. Web — o que muda em relação ao `compose`

1. **Visualizador de giro**: arrastar (mouse/toque) com inércia, teclado ←/→, botão de auto-giro;
   indicador de ângulo; troca de quadro sem piscar (manter o anterior até o próximo carregar).
2. **Pilha de camadas** (tipo B) no motor: base → sombras das opções → peças (alfa) → troca de materiais
   dentro de cada camada.
3. **Shader de pintura**: `cor × diff_light + reflexo_base × cor (metálica) + verniz × gloss`.
4. **DoF por profundidade** (seção 7).
5. **Painel por categoria** (Exterior, Rodas, Interior, Acessórios, Pacotes) em vez de por superfície;
   clique na imagem continua abrindo o leque da peça.
6. **Resumo/orçamento** com preço por opção, regras aplicadas e link compartilhável.
7. Mantém: render sob demanda, estado na URL, export em alta, debug (tecla D), tema claro em tela cheia.

---

## 10. Ferramentas (Python) — pipeline

| Ferramenta | Função |
| :--- | :--- |
| `max/rig_spin.ms` / `.py` | cria o rig de giro (N câmeras/quadros), configura elementos, saída e nomes |
| `max/render_batch` | render em lote por vista (beleza+luz; dados), restaura configurações |
| `tools/import_view.py` | `import_corona.py` por vista (máscaras, UV, luz, bordas, curva), em lote e em paralelo |
| `tools/import_layer.py` | camadas de opção (alfa pré-multiplicado, sombra) |
| `tools/build_previews.py` | quadros leves do giro por configuração padrão |
| `tools/validate_*` | resolução igual, máscaras não vazias e alinhadas, UV em metros, tone mapping linear, soma dos grupos |
| `tools/fetch_textures.py` | biblioteca CC0 (couro, tecido, carbono, alumínio escovado…) com medida física |

Validações automáticas que **recusam** a importação (já existem no `compose`): máscara vazia;
máscara desalinhada da geometria (< 60% da borda nos saltos do UV); resoluções diferentes. Avisos: UV
cortado em 1,0; passes com tone mapping (beauty ≈ 0–1 e reconstrução < 25 dB).

---

## 11. Marcos

| # | Marco | Aceite |
| :--- | :--- | :--- |
| 0 | **Protótipo**: 1 carro, 8 vistas de giro, 2 closes, 3 pinturas (1 sólida, 1 metálica, 1 perolizada), 2 rodas | Decisão documentada: o que fica no tipo A, B ou C; pintura metálica aprovada lado a lado com render real |
| 1 | Pipeline Max: rig, elementos, nomes, render em lote, checklist automático | 8 vistas renderizadas sem retrabalho; validadores passam |
| 2 | Importador por vista e camada, em lote | Todas as vistas do protótipo importadas; reconstrução ≥ 40 dB |
| 3 | Visualizador de giro + carregamento progressivo | Giro fluido a 60 fps com 36 quadros; vista parada carrega passes em < 2 s (1080p, rede local) |
| 4 | Pintura (sólida + metálica) | Diferença < 2/255 contra render real de referência em 3 cores |
| 5 | Camadas de roda/acessório com sombra | Troca de roda sem borda/halo em todas as vistas |
| 6 | DoF por profundidade nos closes | Sem halo na borda em foco; export igual à tela |
| 7 | UI (categorias, regras, orçamento, leque) | Testes e2e de configuração completa e link compartilhado |
| 8 | Escala (36–72 vistas + closes) e publicação estática | Peso inicial < 5 MB; memória de GPU estável girando |

---

## 12. Lições aprendidas no `compose` (não repetir)

1. **Máscara preta**: modo do `CMasking_Mask` errado. Testar num render pequeno antes do lote.
2. **Máscara de outra câmera/resolução**: troca "vaza" para outros objetos. O importador mede o alinhamento
   e recusa < 60%.
3. **UV cortado em 0–1** ou fora de metros: escala de textura e áreas erradas. Grade de teste na primeira vista.
4. **Passes com tone mapping** (≤ 1,0): exigiu reconstruir a curva do Corona (erro 2–8%). Com passes
   lineares, a conta é exata.
5. **Luz = beauty ÷ albedo** deixa materiais neutros **azulados** (o canal fraco do albedo amplifica) e conta
   **reflexo como luz** (chão estourado). Usar o `diff_light` do Corona como luz e o `reflect` como reflexo.
6. **Fio claro nas divisas**: o beauty tem antialiasing e a máscara é dura. Limpar faixa de 2 px nas bordas
   (`edge_clean.py`) e fechar frestas de 1 px entre máscaras.
7. **Texturas**: conferir miniatura por miniatura (um "mármore" era ladrilho bege). Tecidos coloridos precisam
   ser neutralizados para as variações de cor funcionarem.
8. **16 texturas por shader**: planejar slots e grupos de luz com isso em mente.
9. **Beauty refeito por IA**: dá para usar como imagem base (registro por estrutura/ECC), mas o que a IA
   redesenhou não bate com máscaras/UV, e os materiais trocados mantêm a luz do render original.
10. **Arquivos sumindo/sendo sobrescritos** por outro agente ou script: cada render numa pasta própria e
    versionada (`renders/<carro>/<data>_<vista>/`), nunca sobrescrever uma pasta já importada.
11. **Commits só com testes verdes** (`pytest`, `npm test`, `npm run test:e2e`).

---

## 13. Checklist por vista (antes de mandar para o lote)

- [ ] Câmera travada; DoF e motion blur desligados.
- [ ] Tone mapping neutro; EXR linear (valores acima de 1 nas luzes fortes).
- [ ] `masks_*` com cada peça no canal certo (teste rápido no VFB).
- [ ] `UV_config` canal 2 em metros em todas as peças trocáveis.
- [ ] Material override desligado.
- [ ] Mesma resolução e sem região/crop em todos os elementos.
- [ ] Camadas: peça isolada com alfa + passe de sombra.
- [ ] Closes: passe de profundidade (Z) salvo.
- [ ] Nomes no padrão `<vista>_<elemento>.exr`, pasta nova por rodada.
