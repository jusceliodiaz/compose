import copy
import json

import numpy as np
import pytest

import build_test_catalog
import exr_io
import make_test_assets as mta
import pack_masks
import pack_uv
import reconstruct_check
import validate_catalog


@pytest.fixture(scope="module")
def assets(tmp_path_factory):
    """Sala de teste em resolução reduzida + materiais + catálogo, numa pasta temporária."""
    out = tmp_path_factory.mktemp("public") / "assets"
    cam = out / "scenes" / "test_room" / "cam_main"
    mta.write_scene(cam, mta.build_scene(480, 270))
    mta.write_materials(out / "materials")
    build_test_catalog.build_all(out)
    return out


# --- pack_uv -------------------------------------------------------------------------

def test_pack_uv_ida_e_volta(tmp_path):
    rng = np.random.default_rng(0)
    uv = np.zeros((64, 96, 4), np.float32)
    uv[..., 0] = rng.uniform(0.0, 6.2, (64, 96))
    uv[..., 1] = rng.uniform(0.0, 4.8, (64, 96))
    uv[..., 3] = 1
    uv[:5, :, 3] = 0                                   # faixa inválida
    src = tmp_path / "uv.exr"
    exr_io.write_exr(src, uv, half=False)
    assert pack_uv.main([str(src), str(tmp_path / "cam1")]) == 0

    hi = exr_io.read_png(tmp_path / "cam1_uv_hi.png")
    lo = exr_io.read_png(tmp_path / "cam1_uv_lo.png")
    meta = json.loads((tmp_path / "cam1_uv_meta.json").read_text())
    assert meta["uv_encoding"] == "u16_hilo"
    r = meta["uv_range"]
    dec = pack_uv.decode_uv(hi, lo, r)
    valid = uv[..., 3] > 0.5
    tol = max(r[2] - r[0], r[3] - r[1]) / 65535
    src_uv = exr_io.read_exr(src)
    assert np.abs(dec[valid] - src_uv[..., :2][valid]).max() <= tol
    assert (hi[..., 2][valid] == 255).all() and (hi[..., 2][~valid] == 0).all()
    assert hi.dtype == np.uint8 and hi.shape[2] == 3   # 8-bit RGB, sem alfa


def test_pack_uv_erros_claros(tmp_path, capsys):
    assert pack_uv.main([str(tmp_path / "nao_existe.exr"), str(tmp_path / "x")]) == 1
    flat = np.ones((8, 8, 3), np.float32)
    exr_io.write_exr(tmp_path / "flat.exr", flat)
    assert pack_uv.main([str(tmp_path / "flat.exr"), str(tmp_path / "x")]) == 1
    assert "degenerado" in capsys.readouterr().err


def test_png_sem_icc_gama(assets):
    data = (assets / "scenes/test_room/cam_main/uv_hi.png").read_bytes()
    for chunk in (b"iCCP", b"gAMA", b"sRGB"):
        assert chunk not in data


# --- pack_masks ----------------------------------------------------------------------

def test_pack_masks(tmp_path):
    a = np.zeros((10, 10, 3), np.uint8); a[:5] = 255
    b = np.zeros((10, 10, 3), np.uint8); b[:, :5] = 255
    exr_io.write_png(tmp_path / "a.png", a)
    exr_io.write_png(tmp_path / "b.png", b)
    out = tmp_path / "masks_a.png"
    assert pack_masks.main(["-o", str(out), "--r", f"floor={tmp_path/'a.png'}", "--b", f"wall={tmp_path/'b.png'}"]) == 0
    m = exr_io.read_png(out)
    assert (m[..., 0] == a[..., 0]).all() and (m[..., 2] == b[..., 0]).all() and m[..., 1].max() == 0
    assert json.loads(out.with_suffix(".json").read_text())["channels"] == {"r": "floor", "b": "wall"}
    assert pack_masks.main(["-o", str(out), "--r", f"x={tmp_path/'a.png'}", "--g", f"x={tmp_path/'b.png'}"]) == 1


# --- reconstruct_check ---------------------------------------------------------------

def test_reconstruct_check_assets(assets):
    cam = assets / "scenes/test_room/cam_main"
    args = [str(cam / "beauty.exr"), "--mul", str(cam / "diff_color.exr"), str(cam / "diff_light.exr"),
            "--add", str(cam / "glossy.exr")]
    assert reconstruct_check.main(args) == 0
    assert reconstruct_check.main([str(cam / "beauty.exr"), "--add", str(cam / "lg_sun.exr"),
                                   "--add", str(cam / "lg_ceiling.exr")]) == 0
    # sem o glossy a reconstrução tem que falhar
    assert reconstruct_check.main(args[:4]) == 1


# --- validate_catalog ----------------------------------------------------------------

def test_catalogo_de_teste_valido(assets):
    cat = assets / "catalog" / "test_room.json"
    assert validate_catalog.main([str(cat), "--root", str(assets.parent)]) == 0


@pytest.mark.parametrize("mutate,expect", [
    (lambda c: c.update(schema_version=1), "schema_version"),
    (lambda c: c["base_passes"].update(uv_range=[0, 0, 9, 9]), "difere do meta"),
    (lambda c: c["base_passes"].update(glossy="assets/nao_existe.exr"), "não existe"),
    (lambda c: c["configurable_slots"].append(copy.deepcopy(c["configurable_slots"][0]) | {"id": "x"}), "já usado"),
    (lambda c: c["configurable_slots"][0].update(default_texture="zzz"), "default_texture"),
])
def test_validador_pega_erros(assets, mutate, expect):
    cat = json.loads((assets / "catalog" / "test_room.json").read_text(encoding="utf-8"))
    mutate(cat)
    c = validate_catalog.validate(cat, assets.parent)
    assert any(expect in e for e in c.errors), c.errors
