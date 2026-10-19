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
