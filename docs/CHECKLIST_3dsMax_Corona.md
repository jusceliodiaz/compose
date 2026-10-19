# Checklist para o agente (MCP do 3ds Max): preparar e renderizar a cena para o configurador 2.5D

Você é um agente com acesso ao 3ds Max por MCP (MAXScript e/ou pymxs). Sua tarefa é preparar a cena aberta, configurar os Render Elements do Corona e gerar os EXRs que o configurador web vai usar. Trabalhe **na ordem**, marque cada item e **pare para perguntar** quando algo não bater com o esperado.

---

## 0. Configuração (o usuário preenche antes de começar)

```text
PASTA_SAIDA      = C:\Users\saant\Desktop\compose\renders\cam1\
PREFIXO          = cam1_
CAMERA           = (nome da câmera; se vazio, use a câmera ativa da viewport)
RESOLUCAO        = 2000 x 1500   (manter a proporção da imagem de teste, 4:3)
SLOTS (objeto → máscara/canal):
  piso            → masks_a / R
  bancada_marmore → masks_a / G   (tampo + laterais da ilha)
  parede_fundo    → masks_a / B
  frente_ilha     → masks_b / R   (opcional)
  assento_banquetas → masks_b / G (opcional)
GRUPOS DE LUZ:
  lg_sol     → sol + céu/ambiente
  lg_interno → luzes internas (se houver)
```

Se algum nome de objeto não existir na cena, **liste os objetos parecidos e pergunte** qual usar. Não adivinhe.

---

## 1. Regras (não violar)

- **Não apague nem altere materiais, geometria ou luzes** do usuário. Pode adicionar modificadores UVW Map no canal 2, Render Elements e ajustes de render.
- **Antes de mexer, salve uma cópia** da cena: `<nome>_backup_configurador.max`, na mesma pasta do arquivo.
- **Antes de usar qualquer classe ou propriedade do Corona, confirme que ela existe.** Os nomes mudam entre versões. Use `showClass "CShading*"`, `showClass "CGeometry*"`, `showClass "CMasking*"`, `showClass "CESSENTIAL*"` e `showProperties <obj>`. Se não encontrar, pare e informe a classe que faltou e a versão do Corona.
- Toda saída de dados ou luz vai em **EXR half-float, linear, sem tone mapping**.
- Um arquivo por elemento, com o nome `PREFIXO + nome_do_elemento + .exr`.
- Ao final, entregue o **relatório da seção 12**.

---

## 2. Descoberta (só leitura)

- [ ] Registrar as versões do 3ds Max (`maxVersion()`) e do Corona.
- [ ] Confirmar que o renderer ativo é o Corona (`classOf renderers.current`). Se não for, pare e pergunte.
- [ ] Listar câmeras, luzes (com tipo), objetos dos slots e os materiais deles.
- [ ] Verificar as unidades (`units.SystemType`). O esperado é `#meters`. Se for outra, **não converta a cena**: informe e use o fator de conversão nos passos de UV.
- [ ] Listar os Render Elements que já existem (`maxOps.GetCurRenderElementMgr()`).
- [ ] Mostrar ao usuário um resumo do que encontrou e do que vai criar. **Aguarde o OK.**

---

## 3. Câmera

- [ ] Selecionar a câmera indicada e travar a posição e a rotação (Hierarchy → Link Info → Locks, ou `setTransformLockFlags`).
- [ ] Desligar **profundidade de campo** e **motion blur** na câmera e no Corona. Confira os nomes reais com `showProperties`.
- [ ] Anotar a posição, a rotação e o FOV da câmera no relatório.

---

## 4. UV em metros no canal 2 (para cada objeto de slot)

O canal 1 é o das texturas do usuário e **não pode ser tocado**. Use sempre o **map channel 2**.

- [ ] **Piso e parede do fundo** (superfícies planas): adicionar `Uvwmap` com
  - `maptype = 0` (Planar), `mapChannel = 2`;
  - `length` e `width` = dimensões reais da superfície em metros;
  - `utile = width` e `vtile = length`, para que 1 unidade de UV = 1 m;
  - gizmo alinhado à superfície (normal do piso para cima, da parede para frente).
- [ ] **Bancada, frente da ilha e assentos:** `Uvwmap` com `maptype = 4` (Box), `mapChannel = 2` e `realWorldMapSize = true`. Confirme no render de teste (passo 10) que o UV fica em metros.
- [ ] Os modificadores ficam no topo da pilha, com o nome `UV_config`.
- [ ] Registrar no relatório as dimensões usadas por objeto.

---

## 5. Máscaras (IDs)

- [ ] Confirmar a classe `CMasking_Mask`.
- [ ] Criar o elemento **`masks_a`**: piso no canal **R**, bancada no **G**, parede do fundo no **B**.
- [ ] Criar o elemento **`masks_b`**: frente da ilha no **R**, assentos no **G** (B vazio), se esses slots forem usados.
- [ ] Se `CMasking_Mask` não aceitar objetos diretamente na sua versão, use G-Buffer IDs (`obj.gbufferChannel`: piso=1, bancada=2, parede=3, frente=4, assento=5) e configure a máscara por ID. Registre qual método foi usado.

---

## 6. Render Elements de shading

Crie com o nome exato (é ele que vira o nome do arquivo). Para cada um, confirme a propriedade de "componente" com `showProperties` antes de definir.

| Nome | Classe Corona | Configuração |
| :--- | :--- | :--- |
| `diff_light` | `CShading_RawComponent` | componente = **Diffuse** |
| `diff_color` | `CShading_SourceColor` | componente = **Diffuse** |
| `reflect` | `CShading_Components` | componente = **Reflection** |
| `refract` | `CShading_Components` | componente = **Refraction** |
| `transl` | `CShading_Components` | componente = **Translucency** |
| `emission` | `CShading_Components` | componente = **Emission** |
| `sss` | `CShading_Components` | componente = **SSS** (se existir) |
| `volum` | `CShading_Components` | componente = **Volumetric** (se existir) |
| `uv` | `CGeometry_UvwCoords` | **map channel = 2** |

- [ ] Se o elemento tiver uma opção de denoise, ligue em `diff_light` e `reflect`. Deixe desligada em `uv`, `diff_color` e nas máscaras.
- [ ] Não duplicar: se já existir um elemento com o mesmo nome, reutilize.

---

## 7. LightMix (grupos de luz)

- [ ] Confirmar as classes `CESSENTIAL_LightMix` / `CESSENTIAL_LightSelect`.
- [ ] Criar um LightSelect por grupo da seção 0 (`lg_sol`, `lg_interno`), incluindo as luzes de cada grupo. Sol e céu ficam em `lg_sol`.
- [ ] Toda luz da cena deve estar em **exatamente um** grupo. Liste as que sobraram e pergunte.
- [ ] Todos os grupos com a mesma exposição (nenhum multiplicador extra).

---

## 8. Tone mapping e saída

- [ ] Anotar os valores atuais de tone mapping do Corona (para restaurar depois).
- [ ] Deixar o tone mapping **neutro**: exposição 0, highlight compression 1, sem filmic, sem LUT, sem contraste/saturação/curvas. Se o usuário quiser manter um look, pergunte; ele vai ter que ser replicado na web.
- [ ] Configurar a saída **EXR half-float**, com compressão ZIP ou PIZ, sem pós-processamento.
- [ ] Definir o caminho de cada Render Element com `re.SetRenderElementFilename i (PASTA_SAIDA + PREFIXO + nome + ".exr")`. A saída principal (beauty) vai para `PREFIXO + "beauty.exr"`.
- [ ] Resolução = RESOLUCAO para **todos** os renders.

---

## 9. Render 1 — beleza e luz

- [ ] Habilitar todos os elementos das seções 6 e 7.
- [ ] Desabilitar `uv`, `masks_a` e `masks_b` neste render (eles saem no render 2).
- [ ] Qualidade: o limite de ruído e as passes que o usuário já usa, ou um noise limit em torno de 2–3%.
- [ ] Renderizar e confirmar que os arquivos foram gravados em PASTA_SAIDA:
  - `beauty`, `diff_light`, `diff_color`, `reflect`, `refract`, `transl`, `emission`, (`sss`, `volum`);
  - `lg_sol`, (`lg_interno`).

---

## 10. Render 2 — dados (UV e máscaras)

- [ ] Anotar as configurações atuais do filtro de imagem e das passes.
- [ ] Filtro de imagem com a **menor largura permitida** (o objetivo é não misturar pixels vizinhos). Confira o nome da propriedade com `showProperties renderers.current "*filter*"`.
- [ ] Limite de passes baixo (≈ 16) e denoiser **desligado**.
- [ ] Habilitar só `uv`, `masks_a` e `masks_b` (e o beauty, que pode ser descartado).
- [ ] Gravar como `PREFIXO + "uv.exr"`, `"masks_a.exr"`, `"masks_b.exr"`.
- [ ] **Restaurar** o filtro, as passes, o denoiser e o tone mapping originais.

---

## 11. Verificação (obrigatória)

Faça pelo próprio 3ds Max/MAXScript, ou anote para o usuário conferir no VFB.

- [ ] **UV:** no piso, `uv.R` varia de ~0 até o comprimento do piso em metros e `uv.G` até a largura. Os valores devem ser > 1 numa sala normal: se ficarem entre 0 e 1, a UV não está em metros. Registrar mínimo e máximo de R e G por slot, se possível.
- [ ] **Máscaras:** o piso aparece puro em R no `masks_a`, a bancada em G e a parede em B; nada vaza para os outros objetos. As pernas das banquetas recortam o piso corretamente.
- [ ] **Diffuse light:** sem textura de madeira visível (só luz e sombra). As faixas de sol aparecem claras.
- [ ] **Reconstrução (estimativa):** `diff_color × diff_light + reflect + refract + transl + emission (+ sss + volum)` ≈ beauty. Se der para calcular, informe a diferença média. Senão, avise que a checagem vai ser feita depois pelo `import_corona.py`.
- [ ] **LightMix:** a soma de `lg_*` ≈ beauty.
- [ ] Todos os arquivos com a mesma resolução.

---

## 12. Relatório final (formato)

```text
VERSÕES: 3ds Max ____ / Corona ____
CÂMERA: nome, posição, rotação, FOV
RESOLUÇÃO: ____ x ____
SLOTS:
  piso            → masks_a.R | UV planar L=__ W=__ | uv R:[__,__] G:[__,__]
  bancada_marmore → masks_a.G | UV box real-world  | uv R:[__,__] G:[__,__]
  parede_fundo    → masks_a.B | ...
  ...
GRUPOS DE LUZ: lg_sol = [...], lg_interno = [...]
ARQUIVOS GERADOS: (lista com tamanho)
MÉTODO DE MÁSCARA: objetos diretos | G-Buffer ID
CLASSES/PROPRIEDADES ADAPTADAS: (o que teve nome diferente do checklist)
VERIFICAÇÕES: UV ok/falhou, máscaras ok/falhou, reconstrução ≈ __%, LightMix ok/falhou
PENDÊNCIAS / DÚVIDAS PARA O USUÁRIO:
BACKUP SALVO EM: ____
```

Depois disso, o usuário leva a pasta `renders\cam1\` para o projeto web e roda `tools/import_corona.py renders/cam1 cozinha_ilha cam1` (ver `CLAUDE.md`, Marco 3).
