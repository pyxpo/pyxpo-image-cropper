from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from pyxpo.apis import _bridge, _env
from pyxpo.module_api import ModuleNotLinkedError, NotSupportedError
from pyxpo_image_cropper import ImageCropper

PKG = Path(__file__).resolve().parents[1] / "pyxpo_image_cropper"


class FakeApp:
    loop = None

    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def call(self, module, method, *args, reply=False):
        self.calls.append((module, method, args))
        fut = asyncio.get_event_loop().create_future()
        fut.set_result(self.answer)
        return fut


@pytest.fixture
def ios(monkeypatch):
    monkeypatch.setattr(_env, "current", _env.Env({"os": "ios", "modules": ["ImageCropper"]}))


def run(answer, coro_fn):
    app = FakeApp(answer)
    old = _bridge.get_app()
    _bridge.set_app(app)
    try:
        return asyncio.run(coro_fn()), app
    finally:
        _bridge.set_app(old)


def test_crop_sends_options_and_returns_photo(ios):
    out = {"canceled": False, "uri": "/c/a.jpg", "width": 900, "height": 1600, "fileSize": 1234, "mimeType": "image/jpeg"}
    res, app = run(out, lambda: ImageCropper.openCropperAsync("/p.jpg", aspectRatio=(9, 16), title="Crop"))
    assert res == out
    assert app.calls[0][:2] == ("ImageCropper", "crop")
    uri, opts = app.calls[0][2]
    assert uri == "/p.jpg"
    assert opts == {"ratioX": 9, "ratioY": 16, "lock": True, "circle": False, "rotate": True, "flip": True,
                    "format": "jpeg", "quality": 0.9, "title": "Crop"}


def test_free_crop_circle_and_fraction_ratios(ios):
    _, app = run(None, lambda: ImageCropper.open_cropper_async("/p.jpg"))
    assert app.calls[0][2][1]["ratioX"] == 0 and app.calls[0][2][1]["lock"] is False
    _, app = run(None, lambda: ImageCropper.openCropperAsync("/p.jpg", aspectRatio=(16, 9), circle=True))
    o = app.calls[0][2][1]
    assert (o["ratioX"], o["ratioY"], o["lock"], o["circle"]) == (1, 1, True, True)
    _, app = run(None, lambda: ImageCropper.openCropperAsync("/p.jpg", aspectRatio=(1.5, 1), lockAspectRatio=False))
    o = app.calls[0][2][1]
    assert (o["ratioX"], o["ratioY"], o["lock"]) == (3, 2, False)


def test_cancel_shape(ios):
    for answer in (None, {"canceled": True}):
        res, _ = run(answer, lambda: ImageCropper.openCropperAsync("/p.jpg"))
        assert res["canceled"] is True and res["uri"] is None


@pytest.mark.parametrize("kw", [{"aspectRatio": (0, 1)}, {"aspectRatio": (1,)}, {"aspectRatio": "4:3"},
                                {"format": "webp"}, {"quality": 2}, {"quality": True}])
def test_bad_options(ios, kw):
    with pytest.raises(ValueError):
        run(None, lambda: ImageCropper.openCropperAsync("/p.jpg", **kw))
    with pytest.raises(ValueError):
        run(None, lambda: ImageCropper.openCropperAsync(""))


def test_needs_mobile_and_linked(monkeypatch):
    monkeypatch.setattr(_env, "current", _env.Env({}))
    with pytest.raises(NotSupportedError):
        run(None, lambda: ImageCropper.openCropperAsync("/p.jpg"))
    monkeypatch.setattr(_env, "current", _env.Env({"os": "android", "modules": []}))
    with pytest.raises(ModuleNotLinkedError, match="image-cropper"):
        run(None, lambda: ImageCropper.openCropperAsync("/p.jpg"))


def test_manifest_and_native_sources():
    from pyxpo.build.autolink import validate

    meta = json.loads((PKG / "pyxpo-module.json").read_text())
    validate(meta, PKG)
    assert (PKG / "ios" / "ImageCropperModule.swift").exists()
    kt = PKG / "android/src/main/java/dev/pyxpo/modules/imagecropper/ImageCropperModule.kt"
    assert 'override val name = "ImageCropper"' in kt.read_text()
    assert "Theme.AppCompat" in (PKG / "android/src/main/AndroidManifest.xml").read_text()


# the inline editor

from pyxpo import LocalChannel, component, create_app, use_ref  # noqa: E402
from pyxpo.module_testing import FakeBridge  # noqa: E402
from pyxpo.renderers.mock import MockRenderer  # noqa: E402
from pyxpo_image_cropper import CropView, CropViewHandle  # noqa: E402


def mount(root):
    ch = LocalChannel()
    r = MockRenderer(ch)
    return create_app(root, ch), r


def test_crop_view_props_and_events():
    got = []

    @component
    def Root():
        return CropView(source="/p.jpg", aspect_ratio=(1.5, 1), grid=False, on_change=got.append, style={"flex": 1})

    app, r = mount(Root)
    (node,) = r.find_all("PxCropView")
    p = node.props
    assert p["source"] == "/p.jpg" and (p["ratio_x"], p["ratio_y"]) == (3, 2)
    assert p["circle"] is False and p["grid"] is False and p["on_change"] is True and "on_error" not in p
    r.emit("change", node, {"value": {"resettable": True}})
    assert got == [{"resettable": True}]


def test_crop_view_free_and_circle():
    @component
    def Root():
        return CropView(source="/p.jpg", circle=True, aspect_ratio=(16, 9))

    app, r = mount(Root)
    p = r.find_all("PxCropView")[0].props
    assert (p["ratio_x"], p["ratio_y"], p["circle"]) == (1, 1, True)

    @component
    def Free():
        return CropView(source="/p.jpg")

    app, r = mount(Free)
    p = r.find_all("PxCropView")[0].props
    assert (p["ratio_x"], p["ratio_y"]) == (0, 0)


@pytest.mark.parametrize("kw", [{"source": ""}, {"source": "/p.jpg", "aspect_ratio": (0, 1)}])
def test_crop_view_bad_props(kw):
    @component
    def Root():
        return CropView(**kw)

    with pytest.raises(ValueError):
        mount(Root)


def test_crop_view_handle_methods():
    refs = []

    @component
    def Root():
        ref = use_ref(None)
        refs.append(ref)
        return CropView(source="/p.jpg", ref=ref)

    app, r = mount(Root)
    with FakeBridge("ios") as fb:
        tag = r.find_all("PxCropView")[0].id
        for m in ("rotate", "flip", "reset"):
            fb.on("ImageCropper", m, lambda *a: None)
        fb.on("ImageCropper", "cropView", lambda t, o: {"canceled": False, "uri": "/c/x.png", "width": 5, "height": 4,
                                                         "fileSize": 9, "mimeType": "image/png"})
        h = refs[-1].current
        assert isinstance(h, CropViewHandle)
        h.rotate()
        h.rotate(clockwise=False)
        h.flip()
        h.flip(horizontal=False)
        h.reset()
        assert fb.calls[:5] == [("ImageCropper", "rotate", (tag, True)), ("ImageCropper", "rotate", (tag, False)),
                                ("ImageCropper", "flip", (tag, True)), ("ImageCropper", "flip", (tag, False)),
                                ("ImageCropper", "reset", (tag,))]
        res = asyncio.run(h.crop_async(format="png", quality=1))
        assert res["uri"] == "/c/x.png" and res["canceled"] is False
        assert fb.calls[-1] == ("ImageCropper", "cropView", (tag, {"format": "png", "quality": 1.0}))
        with pytest.raises(ValueError):
            asyncio.run(h.cropAsync(format="gif"))
