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
