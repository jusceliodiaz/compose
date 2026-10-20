import numpy as np

import edge_clean


def test_bordas_sem_cor_vizinha():
    """Parede branca (esq.) e piso marrom (dir.) com antialiasing na divisa: após a limpeza, cada lado só
    tem a cor do próprio lado e os pixels-fonte são da mesma região."""
    h, w = 40, 60
    x = np.arange(w)[None, :].repeat(h, 0).astype(np.float32)
    cov = np.clip(30.5 - x, 0, 1)                      # cobertura da parede, com 1 px de transição
    wall_c, floor_c = np.array([0.9, 0.9, 0.9]), np.array([0.3, 0.15, 0.08])
    beauty = cov[..., None] * wall_c + (1 - cov[..., None]) * floor_c
    beauty[..., 1] += np.linspace(0, 0.01, h)[:, None]  # gradiente vertical: a fonte tem que ser a da mesma linha
    wall = (x < 30).astype(np.float32)
    floor = 1 - wall
    labels = edge_clean.region_labels([wall, floor])
    dst, src = edge_clean.nearest_interior(labels, width=2)
    assert dst.size > 0
    assert (labels.ravel()[dst] == labels.ravel()[src]).all()
    out = edge_clean.apply(beauty, dst, src)
    assert np.abs(out[:, :30] - wall_c).max(axis=-1).max() < 0.02
    assert np.abs(out[:, 30:] - floor_c).max(axis=-1).max() < 0.02
    # fonte na mesma linha (pixel interior mais próximo é horizontal)
    assert (dst // w == src // w).all()
    # pixels interiores intocados
    untouched = np.ones(h * w, bool)
    untouched[dst] = False
    assert np.array_equal(out.reshape(-1, 3)[untouched], beauty.reshape(-1, 3)[untouched])


def test_fundo_conta_como_regiao():
    m = np.zeros((20, 20), np.float32)
    m[5:15, 5:15] = 1
    labels = edge_clean.region_labels([m])
    assert set(np.unique(labels)) == {0, 1}
    dst, src = edge_clean.nearest_interior(labels, width=1)
    assert (labels.ravel()[dst] == labels.ravel()[src]).all()


def test_fresta_de_1px_vira_superficie_vizinha():
    labels = np.zeros((20, 20), np.int32)
    labels[:, :9] = 1
    labels[:, 10:] = 2                                   # coluna 9 sem máscara (fresta)
    labels[15:, :] = 0                                   # fundo de verdade (largo) embaixo
    out = edge_clean.fill_gaps(labels)
    assert set(np.unique(out[:15, 9])) <= {1, 2}         # fresta preenchida
    assert (out[16:, :] == 0).all()                      # fundo largo continua fundo
