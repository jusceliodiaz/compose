import numpy as np
import pytest

import exr_io
import make_test_assets as mta


@pytest.fixture(scope="module")
def cam_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("assets")
    scene = mta.build_scene(640, 360)
    d = out / "cam"
    mta.write_scene(d, scene)
    return d


def test_reconstrucao_bate_com_beauty(cam_dir):
    beauty = exr_io.read_exr(cam_dir / "beauty.exr")
    dc = exr_io.read_exr(cam_dir / "diff_color.exr")
    dl = exr_io.read_exr(cam_dir / "diff_light.exr")
    gl = exr_io.read_exr(cam_dir / "glossy.exr")
    err = np.abs(dc * dl + gl - beauty)
    assert err.max() < 1e-3


def test_light_groups_somam_beauty(cam_dir):
    beauty = exr_io.read_exr(cam_dir / "beauty.exr")
    s = exr_io.read_exr(cam_dir / "lg_sun.exr") + exr_io.read_exr(cam_dir / "lg_ceiling.exr")
    assert np.abs(s - beauty).max() < 2e-3


def test_faixas_fisicas(cam_dir):
    dl = exr_io.read_exr(cam_dir / "diff_light.exr")
    gl = exr_io.read_exr(cam_dir / "glossy.exr")
    mask = exr_io.read_png(cam_dir / "masks_a.png")[..., 0] > 127
    assert 2.0 < dl[mask].max() <= 3.1          # HDR até ~3
    assert gl.min() >= 0 and gl.max() <= 0.2     # reflexo fraco
    dc = exr_io.read_exr(cam_dir / "diff_color.exr")
    assert np.allclose(dc[mask], 0.35, atol=1e-3)


def test_uv_range_perto_do_piso():
    scene = mta.build_scene(1920, 1080)
    uv, valid = scene["uv"], scene["mask"] > 0.5
    u, v = uv[..., 0][valid], uv[..., 1][valid]
    assert u.min() == pytest.approx(0, abs=0.05)
    assert v.min() == pytest.approx(0, abs=0.05)
    assert u.max() == pytest.approx(6.2, abs=0.05)
    assert v.max() == pytest.approx(4.8, abs=0.1)


def test_mascara_e_uv_coerentes(cam_dir):
    uv = exr_io.read_exr(cam_dir / "uv.exr")
    mask = exr_io.read_png(cam_dir / "masks_a.png")
    assert mask.dtype == np.uint8 and mask.shape[2] == 3
    assert np.array_equal(uv[..., 3] > 0.5, mask[..., 0] > 127)
    assert mask[..., 1].max() == 0 and mask[..., 2].max() == 0


def test_beauty_webp_igual_tonemap(cam_dir):
    beauty = exr_io.read_exr(cam_dir / "beauty.exr")
    webp = exr_io.read_png(cam_dir / "beauty.webp")
    ref = exr_io.to_u8(exr_io.linear_to_srgb(exr_io.tonemap(beauty)))
    assert np.abs(webp.astype(int) - ref.astype(int)).max() <= 1


def test_materiais_sem_emenda():
    for mid, (fn, size) in mta.MATERIALS.items():
        img = fn().astype(float)
        # a diferença entre a última e a primeira coluna/linha deve ser típica de vizinhos
        inner = np.abs(np.diff(img, axis=1)).mean()
        wrap = np.abs(img[:, -1] - img[:, 0]).mean()
        assert wrap < inner * 3 + 2, mid
        h, w = img.shape[:2]
        assert w / h == pytest.approx(size[0] / size[1], rel=0.01), mid
