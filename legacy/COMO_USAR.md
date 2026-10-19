# Como Replicar o Zytro / ZYcompose (Passo a Passo)

Bem-vindo ao seu projeto base para criar o seu próprio configurador por imagem no navegador!

---

## 🚀 Passo 1: Testar o Protótipo Agora Mesmo

1. Vá até a pasta `c:\Users\saant\Desktop\meu-configurador-zytro`.
2. Dê um **duplo clique no arquivo `abrir_configurador.bat`** (ou dê dois cliques em `index.html`).
3. O configurador abrirá no seu navegador com:
   - Troca de pisos em tempo real (Carvalho, Mármore, Espinha de Peixe, Cimento).
   - Sliders de **Escala/Tiling**, **Rotação** e **Deslocamento** do piso em perspectiva real.
   - Ajuste de **Iluminação da cena**.
   - Abas para inspecionar os passes técnicos (UV Pass, Máscara e Sombras).
   - Botão para exportar o render final em alta qualidade.

---

## 🎨 Passo 2: Como Usar com Suas Próprias Cenas do Blender

Para colocar qualquer quarto, sala ou produto seu no configurador, você só precisa de **3 imagens geradas no Blender** da mesma câmera:

1. **`render_beauty.png`**:
   - A imagem normal renderizada com Cycles (com móveis, paredes e luz bonita).
2. **`pass_mask.png`**:
   - Uma imagem preta e branca onde a área que você quer trocar (ex: piso) fica **branca**, e todo o resto fica **preto**.
   - No Blender, você faz isso usando o passe **Cryptomatte** ou atribuindo um **Pass Index** ao objeto.
3. **`pass_uv.png` (O Mapa Mágico)**:
   - Uma imagem onde o canal Vermelho é a coordenada U e o canal Verde é a coordenada V.
   - No Blender: na aba **View Layer Properties > Passes > Data**, ative a caixinha **UV**.
   - No **Compositor**, conecte a saída **UV** do nó Render Layers diretamente a um nó **File Output** (salvando como PNG 16-bit ou OpenEXR).

---

## 🛠️ O que você precisa daqui para frente:

1. **Texturas Seamless (Tileable)**:
   - Imagens de madeira, mármore, azulejos e tecidos com repetição perfeita (pode baixar em sites gratuitos como *ambientCG* ou *Poly Haven*).
2. **Subir com Servidor Local**:
   - Quando for usar arquivos de imagem reais `.png`, execute `servidor_local.bat` para evitar bloqueios de segurança do navegador (CORS).
