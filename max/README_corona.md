# Passo a passo manual — 3ds Max + Corona → configurador

Guia para preparar uma câmera à mão (sem scripts). Exemplo: sala de estar, câmera `cam7`,
pasta `renders\sala_estar\`. Troque nomes e medidas pelos da sua cena.

O configurador precisa de **duas coisas certas**:
1. **Máscaras** que mostrem onde está cada superfície trocável (piso, sofá, parede…).
2. **UV em metros** dessas superfícies (1 unidade de UV = 1 m).

O resto (beauty, luz) já sai do render normal.

---

## 1. Preparar a cena (uma vez)

1. **Salve uma cópia** da cena (`Arquivo → Salvar como → nome_backup.max`).
2. **Material override desligado:** `Render Setup (F10) → Scene → Material override` desmarcado.
   (Com override ligado tudo sai branco e o "Original do render" fica sem os materiais reais.)
3. **Câmera travada:** selecione a câmera → `Hierarchy → Link Info → Locks` → marque Move e Rotate.
   Desligue profundidade de campo e motion blur da câmera.
4. **Tone mapping neutro** (`Render Setup → Camera/Postprocess` ou na janela do VFB → aba de tone mapping):
   exposição **0**, highlight compression **1**, **sem** Filmic, ACES, LUT, contraste, saturação ou curvas.

## 2. UV em metros (canal 2) em cada superfície trocável

Não mexa no canal 1 (é o das texturas originais). Para cada objeto (piso, sofá, parede):

1. Selecione o objeto → `Modify → Modifier List → UVW Map` (deixe no **topo** da pilha). Renomeie para `UV_config`.
2. `Map Channel` = **2**.
3. **Piso e paredes (planos):** `Planar`, com o gizmo alinhado à superfície.
   - `Length` e `Width` = medidas reais da superfície.
   - `U Tile` = largura **em metros**, `V Tile` = comprimento **em metros**.
   - A cena está em centímetros, então: piso de 840 × 614 cm → `Width 840`, `Length 614`, `U Tile 8,40`, `V Tile 6,14`.
4. **Sofá, bancada e móveis:** `Box`, `Length = Width = Height = 100 cm`, `U/V/W Tile = 1`
   (1 m de material = 1 unidade de UV).

## 3. Render Elements (`Render Setup → Render Elements → Add`)

Renomeie cada elemento **exatamente** como abaixo (o nome vira o nome do arquivo).

| Nome | Tipo do elemento | Configuração |
| :--- | :--- | :--- |
| `diff_light` | `CShading_RawComponent` | componente **Diffuse** |
| `diff_color` | `CShading_SourceColor` | componente **Diffuse** |
| `reflect` | `CShading_Components` | componente **Reflection** |
| `refract`, `transl`, `emission` | `CShading_Components` | Refraction / Translucency / Emission |
| `uv` | `CGeometry_UvwCoords` | **map channel 2** |
| `masks_a` | `CMasking_Mask` | ver passo 4 |
| `lg_sol`, `lg_ceu`… | `CShading_LightSelect` | um por grupo de luz; cada luz em **um** grupo só |

## 4. Máscaras — o jeito à prova de erro (por Object ID)

Foi aqui que os renders anteriores falharam: o elemento estava no modo **por ID**, mas os objetos
tinham sido colocados na lista de **objetos**, que esse modo ignora. Resultado: máscara toda preta.

1. Dê um **Object ID** a cada superfície: clique direito no objeto → `Object Properties` →
   `G-Buffer → Object ID`: **piso = 1**, **sofá = 2**, **parede = 3** (para mais slots: 4, 5, 6 → `masks_b`).
2. No elemento `masks_a`, use o modo **Object ID** e preencha:
   **R = 1**, **G = 2**, **B = 3**, com os três canais **ligados**.
3. Teste rápido: renderize (pode ser em resolução baixa) e veja o `masks_a` no VFB.
   O piso deve aparecer **vermelho puro**, o sofá **verde**, a parede **azul**, o resto preto.
   Se estiver preto, o modo ou os IDs estão errados. **Não siga sem isso funcionar.**

## 5. Saída dos arquivos

1. `Render Setup → Common → Render Output → Save File`:
   `C:\Users\saant\Desktop\compose\renders\sala_estar\cam7_beauty.exr`.
2. Formato **OpenEXR**: tipo **Half Float** (o `uv` pode ser **Full Float**), compressão ZIP ou PIZ,
   **sem** "gamma/LUT", **sem** canal de pós-processamento.
3. Em `Render Elements`, marque **Elements Active** e defina o arquivo de cada um como
   `cam7_<nome>.exr` na mesma pasta (ex.: `cam7_uv.exr`, `cam7_masks_a.exr`).
4. **Importante:** os EXRs precisam sair **lineares e sem corte em 1**. Se depois do render os
   valores ainda pararem em 1, salve pelo VFB do Corona (salvar todos os elementos em EXR) em vez da
   saída do 3ds Max, e confira de novo o tone mapping neutro do passo 1.

## 6. Dois renders

**Render 1 — beleza e luz:** qualidade normal (noise limit ~2–3% ou as passes de sempre), denoiser
ligado. Desative `uv` e `masks_a` só neste render.

**Render 2 — dados:** só `uv` e `masks_a` ativos (o beauty pode ser descartado, salve como
`cam7_beauty_pass2.exr`). `Performance → Image filter` com a **menor largura**, **16 passes**,
**denoiser desligado**. Depois, restaure filtro, passes e denoiser.

## 7. Conferir e importar

```bash
python tools/import_corona.py renders/sala_estar sala_estar cam7 --project-name "Sala de Estar" ^
    --slot r:piso:Piso:floor --slot g:sofa:Sofá:paint --slot b:parede:Parede:paint ^
    --area piso=45 --area sofa=8 --area parede=60 --default
```

(`--area` = áreas reais em m²; sem elas o importador estima só a parte visível.)

O importador confere tudo e mostra:

| Linha | Esperado |
| :--- | :--- |
| `cobertura` de cada slot | maior que 0% (se der 0, a máscara veio preta) |
| `alinhamento máscara×geometria` | **ok** (≥ 75%). "DESALINHADA" = máscara de outra câmera |
| `uv_range` | valores **maiores que 1** (metros). Aviso "UV CORTADO" = EXR com clamp |
| `reconstrução` | **≥ 40 dB**. Abaixo disso, os passes estão com tone mapping ou falta um elemento |

Se o render ainda vier com tone mapping (aviso "o beauty não passa de 1.0"), acrescente
`--light-from-beauty`: funciona, mas a troca de material fica aproximada.

Depois: `cd web && npm run dev` e abra `http://localhost:5173/?project=sala_estar`.
