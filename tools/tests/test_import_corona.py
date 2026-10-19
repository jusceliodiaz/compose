"""Aceite do Marco 3: o import_corona.py roda numa pasta que simula a saída do Corona."""

import json

import numpy as np
import pytest

import exr_io
import import_corona
import make_test_assets as mta
import validate_catalog


@pytest.fixture(scope="module")
def corona_dir(tmp_path_factory):
    """Sala sintética gravada com os nomes do Corona (cam1_<elemento>.exr), sem alfa no UV e
    com a máscara em EXR float, como o CMasking_Mask grava."""
    d = tmp_path_factory.mktemp("renders") / "cam1"
    s = mta.build_scene(480, 270)
    d.mkdir()
    exr_io.write_exr(d / "cam1_beauty.exr", s["beauty"])
    exr_io.write_exr(d / "cam1_diff_light.exr", s["diff_light"])
    exr_io.write_exr(d / "cam1_diff_color.exr", s["diff_color"])
    exr_io.write_exr(d / "cam1_reflect.exr", s["glossy"])
    exr_io.write_exr(d / "cam1_emission.exr", np.zeros_like(s["beauty"]))
    exr_io.write_exr(d / "cam1_uv.exr", s["uv"][..., :3], half=False)
    m = np.zeros(s["mask"].shape + (3,), np.float32)
    m[..., 0] = s["mask"]
    exr_io.write_exr(d / "cam1_masks_a.exr", m)
    exr_io.write_exr(d / "cam1_lg_sol.exr", s["lg_sun"])
    exr_io.write_exr(d / "cam1_lg_teto.exr", s["lg_ceiling"])
    exr_io.write_exr(d / "cam1_lg_vazio.exr", np.zeros_like(s["beauty"]))
    exr_io.write_exr(d / "cam1_output_lg_sol.exr", s["lg_sun"] * 0)  # cópia que não deve ser usada
    return d


def test_import_corona_gera_catalogo_valido(corona_dir, tmp_path, capsys):
    public = tmp_path / "public"
    rc = import_corona.main([str(corona_dir), "sala", "cam1", "--slot", "r:piso:Piso:floor",
                             "--web-root", str(public), "--tone", "standard", "--exposure", "1"])
    out = capsys.readouterr().out
    assert rc == 0, out
    cam = public / "assets/scenes/sala/cam1"
    for f in ["beauty.webp", "beauty.exr", "diff_light.exr", "glossy.exr", "uv_hi.png", "uv_lo.png",
              "uv_meta.json", "masks_a.png", "lg_sol.exr", "lg_teto.exr", "thumb_original_piso.webp"]:
        assert (cam / f).is_file(), f
    assert not (cam / "lg_vazio.exr").exists()          # grupo vazio é ignorado
    assert "reconstrução" in out and "ok" in out

    cat = json.loads((public / "assets/catalog/sala.json").read_text(encoding="utf-8"))
    assert validate_catalog.validate(cat, public).errors == []
    assert [g["id"] for g in cat["light_groups"]] == ["sol", "teto"]
    slot = cat["configurable_slots"][0]
    assert slot["default_texture"] == "original" and slot["options"][0]["keep_original"]
    assert cat["base_passes"]["uv_range"][2] == pytest.approx(6.2, abs=0.05)
    # usa o cam1_lg_sol.exr (e não a cópia zerada cam1_output_lg_sol.exr)
    assert exr_io.read_exr(cam / "lg_sol.exr").max() > 0.1
    idx = json.loads((public / "assets/catalog/index.json").read_text(encoding="utf-8"))
    assert idx["default"] == "sala"


def test_import_corona_display_referred_estima_expoente(tmp_path):
    """Passes já com tone mapping (beauty ≤ 1): estima p da curva e grava relight_power."""
    d = tmp_path / "r"
    h, w = 120, 160
    rng = np.random.default_rng(1)
    albedo = np.clip(0.3 + 0.15 * rng.standard_normal((h, w)), 0.05, 0.9)
    light = np.tile(np.linspace(0.5, 2.0, w), (h, 1))
    beauty = np.clip(0.8 * (albedo * light) ** 0.6, 0, 1)            # curva T(x) = 0.8·x^0.6
    rgb = lambda a: np.repeat(a[..., None], 3, -1).astype(np.float32)
    exr_io.write_exr(d / "c_beauty.exr", rgb(beauty))
    exr_io.write_exr(d / "c_diff_color.exr", rgb(albedo))
    exr_io.write_exr(d / "c_diff_light.exr", rgb(np.clip(light, 0, 1)))
    uv = np.zeros((h, w, 3), np.float32)
    uv[..., 0], uv[..., 1] = np.meshgrid(np.linspace(0, 4, w), np.linspace(0, 3, h))
    exr_io.write_exr(d / "c_uv.exr", uv, half=False)
    exr_io.write_exr(d / "c_masks_a.exr", rgb(np.ones((h, w))) * np.array([1, 0, 0], np.float32))
    public = tmp_path / "public"
    rc = import_corona.main([str(d), "p", "c", "--prefix", "c_", "--slot", "r:piso:Piso:floor",
                             "--light-from-beauty", "--web-root", str(public)])
    assert rc == 0
    cat = json.loads((public / "assets/catalog/p.json").read_text(encoding="utf-8"))
    assert cat["tone_mapping"]["operator"] == "standard"
    assert cat["tone_mapping"]["relight_power"] == pytest.approx(0.6, abs=0.05)


def test_import_corona_falha_claro_sem_mascara(corona_dir, tmp_path, capsys):
    d = tmp_path / "vazio"
    d.mkdir()
    for f in corona_dir.glob("cam1_*.exr"):
        (d / f.name).write_bytes(f.read_bytes())
    exr_io.write_exr(d / "cam1_masks_a.exr", np.zeros((270, 480, 3), np.float32))
    rc = import_corona.main([str(d), "x", "cam1", "--web-root", str(tmp_path / "pub")])
    assert rc == 1
    assert "nenhum slot com máscara" in capsys.readouterr().err
