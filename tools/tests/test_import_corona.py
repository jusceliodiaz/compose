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
              "uv_meta.json", "masks_0.png", "lg_sol.exr", "lg_teto.exr", "thumb_original_piso.webp"]:
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


def test_import_corona_display_referred_reconstroi_curva(tmp_path):
    """Passes já com tone mapping (beauty ≤ 1): reconstrói a curva, grava a LUT e deslineariza os passes."""
    import tone_curve

    d = tmp_path / "r"
    h, w = 160, 200
    rng = np.random.default_rng(1)
    albedo = np.clip(0.3 + 0.12 * rng.standard_normal((h, w)), 0.05, 0.9)
    light = np.tile(np.linspace(0.3, 3.0, w), (h, 1))
    true = lambda x: x / (x + 0.6)                                    # curva "do renderizador" (Reinhard)
    beauty = true(albedo * light)
    rgb = lambda a: np.repeat(a[..., None], 3, -1).astype(np.float32)
    exr_io.write_exr(d / "c_beauty.exr", rgb(beauty), half=False)
    exr_io.write_exr(d / "c_diff_color.exr", rgb(albedo), half=False)
    # como no Corona, o diff_light também sai com a curva aplicada
    exr_io.write_exr(d / "c_diff_light.exr", rgb(true(light)), half=False)
    uv = np.zeros((h, w, 3), np.float32)
    uv[..., 0], uv[..., 1] = np.meshgrid(np.linspace(0, 4, w), np.linspace(0, 3, h))
    exr_io.write_exr(d / "c_uv.exr", uv, half=False)
    exr_io.write_exr(d / "c_masks_a.exr", rgb(np.ones((h, w))) * np.array([1, 0, 0], np.float32))
    public = tmp_path / "public"
    rc = import_corona.main([str(d), "p", "c", "--prefix", "c_", "--slot", "r:piso:Piso:floor",
                             "--light-from-beauty", "--web-root", str(public)])
    assert rc == 0
    cat = json.loads((public / "assets/catalog/p.json").read_text(encoding="utf-8"))
    tm = cat["tone_mapping"]
    assert tm["operator"] == "lut" and len(tm["lut"]["values"]) == tone_curve.LUT_SIZE
    assert validate_catalog.validate(cat, public).errors == []

    # a curva reconstruída prevê a troca de albedo como a curva verdadeira (até um fator de escala)
    cam = public / "assets/scenes/p/c"
    lin = exr_io.read_exr(cam / "beauty.exr")[..., 0]
    lut = tm["lut"]
    fwd = lambda x: np.interp(np.log2(np.maximum(x, 1e-12)),
                              np.linspace(lut["log2_min"], lut["log2_max"], len(lut["values"])), lut["values"])
    assert np.abs(fwd(lin) - beauty).max() < 0.01                    # identidade com o material original
    light_rec = exr_io.read_exr(cam / "diff_light.exr")[..., 0]
    pred = fwd(0.6 * light_rec)                                       # novo albedo 0.6
    expected = true(0.6 * light)
    assert np.median(np.abs(pred - expected)) < 0.03


def test_import_corona_falha_claro_sem_mascara(corona_dir, tmp_path, capsys):
    d = tmp_path / "vazio"
    d.mkdir()
    for f in corona_dir.glob("cam1_*.exr"):
        (d / f.name).write_bytes(f.read_bytes())
    exr_io.write_exr(d / "cam1_masks_a.exr", np.zeros((270, 480, 3), np.float32))
    rc = import_corona.main([str(d), "x", "cam1", "--web-root", str(tmp_path / "pub")])
    assert rc == 1
    assert "nenhum slot com máscara" in capsys.readouterr().err


def test_import_corona_recusa_mascara_desalinhada(corona_dir, tmp_path, capsys):
    """Máscara deslocada (outra câmera/resolução) → importação recusada com mensagem clara."""
    d = tmp_path / "desalinhada"
    d.mkdir()
    for f in corona_dir.glob("cam1_*.exr"):
        (d / f.name).write_bytes(f.read_bytes())
    m = exr_io.read_exr(corona_dir / "cam1_masks_a.exr")[..., :3]
    exr_io.write_exr(d / "cam1_masks_a.exr", np.roll(m, (40, 70), axis=(0, 1)))
    args = [str(d), "x", "cam1", "--slot", "r:piso:Piso:floor", "--web-root", str(tmp_path / "pub")]
    assert import_corona.main(args) == 1
    assert "não coincide com a geometria" in capsys.readouterr().err
    assert import_corona.main(args + ["--ignorar-alinhamento"]) == 0


def test_import_corona_reempacota_mascaras_de_varios_arquivos(corona_dir, tmp_path):
    """Um objeto por arquivo (masks_a, masks_b…, como no render da sala) → PNGs da web com 3 slots cada."""
    d = tmp_path / "multi"
    d.mkdir()
    for f in corona_dir.glob("cam1_*.exr"):
        if "masks" not in f.name:
            (d / f.name).write_bytes(f.read_bytes())
    m = exr_io.read_exr(corona_dir / "cam1_masks_a.exr")[..., 0]
    h, w = m.shape
    left = m * (np.arange(w)[None, :] < w // 2)
    right = m * (np.arange(w)[None, :] >= w // 2)
    for name, part in [("a", left), ("b", right)]:
        exr_io.write_exr(d / f"cam1_masks_{name}.exr", np.repeat(part[..., None], 3, -1).astype(np.float32))
    pub = tmp_path / "pub"
    rc = import_corona.main([str(d), "m", "cam1", "--slot", "masks_a.r:esq:Esquerda:floor",
                             "--slot", "masks_b.r:dir:Direita:rug", "--web-root", str(pub), "--ignorar-alinhamento"])
    assert rc == 0
    cat = json.loads((pub / "assets/catalog/m.json").read_text(encoding="utf-8"))
    assert cat["base_passes"]["masks_packed"] == [
        {"file": "assets/scenes/m/cam1/masks_0.png", "channels": {"r": "esq", "g": "dir"}}]
    refs = {s["id"]: s["mask_ref"] for s in cat["configurable_slots"]}
    assert refs == {"esq": {"file": 0, "channel": "r"}, "dir": {"file": 0, "channel": "g"}}
    png = exr_io.read_png(pub / "assets/scenes/m/cam1/masks_0.png")
    # cada slot contém a sua máscara original; o preenchimento de frestas só acrescenta poucos pixels
    for ch, orig in [(0, left), (1, right)]:
        got = png[..., ch] > 127
        assert got[orig > 0.5].all()
        assert got.sum() - (orig > 0.5).sum() <= 0.001 * got.size
