# pyxpo-image-cropper

[![CI](https://github.com/pyxpo/pyxpo-image-cropper/actions/workflows/ci.yml/badge.svg)](https://github.com/pyxpo/pyxpo-image-cropper/actions/workflows/ci.yml) [![PyPI](https://img.shields.io/pypi/v/pyxpo-image-cropper)](https://pypi.org/project/pyxpo-image-cropper/) [![Python](https://img.shields.io/pypi/pyversions/pyxpo-image-cropper)](https://pypi.org/project/pyxpo-image-cropper/) [![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

A full-featured image cropper for [pyxpo](https://github.com/pyxpo/pyxpo) apps written in Python: free or fixed aspect
ratio, a circle guide for avatars, rotate, flip and pinch zoom. Use it two ways: open a ready full-screen cropper with
one call, or put a `CropView` in your own screen and drive it with your own buttons. iOS uses
[TOCropViewController](https://github.com/TimOliver/TOCropViewController), Android the CanHub
[Android-Image-Cropper](https://github.com/CanHub/Android-Image-Cropper). The cropped photo is a new file; the source is
never changed.

<p align="center">
  <img src="https://raw.githubusercontent.com/pyxpo/pyxpo-image-cropper/main/docs/images/hero.png" width="820" alt="The inline CropView with a 1:1 box and ratio chips on Android and iOS">
</p>

```python
from pyxpo_image_cropper import ImageCropper

res = await ImageCropper.open_cropper_async(path, aspectRatio=(1, 1), circle=True)
if not res["canceled"]:
    avatar = res["uri"]
```

## Features

- **Full-screen cropper:** `open_cropper_async(uri, ...)` shows the native cropper and returns the new file.
- **Inline editor:** `CropView` sits in your layout. `ref.current` gives `rotate()`, `flip()`, `reset()` and `crop_async()`.
- **Aspect ratio:** free, or any `(width, height)` pair such as `(16, 9)`. Lock it, or use it only as the start frame.
- **Circle guide** for profile photos (the saved file stays square; round it with `borderRadius`).
- **Rotate** in quarter turns, **flip** left to right or top to bottom, **pinch zoom**, thirds **grid**.
- **Output:** JPEG with a quality from 0 to 1, or PNG. Width, height, size and MIME type come back with the path.
- **Typed:** ships `py.typed`. camelCase (`openCropperAsync`) and snake_case names both work.

## Contents

| If you are... | Start here |
| --- | --- |
| Cropping a picked photo in one call | [Quick start](#quick-start) |
| Building your own crop screen | [CropView](#cropview) |
| Making a round avatar | [Recipe: avatar](#recipe-avatar) |
| Exact signatures | [API reference](#api-reference) · [Errors](#errors) |
| Stuck | [Testing](#testing) · [Troubleshooting](#troubleshooting) · [FAQ](#faq) |

## Platform support

| Target | What works |
| --- | --- |
| Android, API 24+ | Everything. |
| iOS 15+ | Everything, except flip in the full-screen cropper (TOCropViewController has no flip). `CropView.flip()` works. |
| Web page and desktop window | Not supported. Calls raise `NotSupportedError`. |

Requires Python 3.9+ and `pyxpo>=0.1.0a4`. It needs no permissions and no Info.plist keys. To pick the photo first,
use [pyxpo-image-picker](https://github.com/pyxpo/pyxpo-image-picker).

## Install

```sh
pip install pyxpo-image-cropper
```

```toml
[tool.pyxpo]
modules = ["image-cropper"]
```

Rebuild the app. The build adds the native croppers (Swift package on iOS, Gradle dependency on Android).

## Quick start

```python
from pyxpo import Button, Image, View, component, use_async, use_state
from pyxpo_image_cropper import ImageCropper


@component
def CropButton(path: str = ""):
    taps, set_taps = use_state(0)
    out, set_out = use_state(None)

    async def run():
        if taps == 0 or not path:
            return
        res = await ImageCropper.open_cropper_async(path, aspectRatio=(4, 5), lockAspectRatio=False, title="Crop photo")
        if not res["canceled"]:
            set_out(res)

    use_async(run, [taps])

    return View(
        Image(source=out["uri"], style={"height": 240, "aspectRatio": out["width"] / out["height"]}) if out else None,
        Button("Crop", lambda: set_taps(taps + 1)),
    )
```

> **Tip:** Start async work from a button with a counter in state and `use_async(fn, [counter])`. A
> `lambda: coroutine()` is never awaited.

`open_cropper_async` returns `{"canceled", "uri", "width", "height", "fileSize", "mimeType"}`. When the user cancels,
`canceled` is True and `uri` is None. Only one full-screen cropper can be open at a time.

## CropView

Put the editor in your own screen when you want your own buttons, ratio chips or colors.

```python
from pyxpo import Button, View, component, use_ref, use_state
from pyxpo.apis import _bridge
from pyxpo_image_cropper import CropView

RATIOS = [None, (1, 1), (4, 5), (16, 9)]


@component
def Editor(path: str, on_done=None):
    ratio, set_ratio = use_state(None)
    ref = use_ref(None)

    def crop():
        async def go():
            res = await ref.current.crop_async(format="jpeg", quality=0.85)
            if on_done:
                on_done(res)
        _bridge.spawn(go())

    return View(
        CropView(source=path, aspect_ratio=ratio, ref=ref, style={"flex": 1}),
        View(*[Button(str(r or "Free"), lambda r=r: set_ratio(r)) for r in RATIOS], style={"flexDirection": "row"}),
        View(
            Button("Rotate", lambda: ref.current.rotate()),
            Button("Flip", lambda: ref.current.flip()),
            Button("Reset", lambda: ref.current.reset()),
            style={"flexDirection": "row"},
        ),
        Button("Crop", crop),
        style={"flex": 1},
    )
```

<p align="center">
  <img src="https://raw.githubusercontent.com/pyxpo/pyxpo-image-cropper/main/docs/images/result.png" width="720" alt="The circle guide in the CropView, then the cropped photo with its size, on Android and iOS">
</p>

| Prop | Default | Description |
| --- | --- | --- |
| `source` | required | A local path or `file://`; on Android also `content://`. Pass it by name: a positional argument becomes a child. |
| `aspect_ratio` | `None` | A `(width, height)` pair that locks the box, or None for a free box. Changing it reshapes the box. |
| `circle` | `False` | A round guide; locks 1:1. |
| `grid` | `True` | The thirds grid. |
| `on_change` | `None` | `on_change({"resettable": bool})` when the crop moves away from, or back to, the whole photo. |
| `on_error` | `None` | `on_error({"message"})` when the photo cannot be opened. |
| `style` | `None` | Size the view here, for example `{"flex": 1}`. |
| `ref` | `None` | `ref.current` is a [`CropViewHandle`](#cropviewhandle). |

## Recipe: avatar

Pick a photo, crop it round, show it.

```python
from pyxpo import Button, Image, View, component, use_async, use_state
from pyxpo_image_cropper import ImageCropper
from pyxpo_image_picker import ImagePicker


@component
def Avatar():
    taps, set_taps = use_state(0)
    uri, set_uri = use_state(None)

    async def run():
        if taps == 0:
            return
        picked = await ImagePicker.launch_image_library_async()
        if picked["canceled"]:
            return
        res = await ImageCropper.open_cropper_async(picked["assets"][0]["uri"], circle=True, quality=0.8)
        if not res["canceled"]:
            set_uri(res["uri"])

    use_async(run, [taps])
    return View(
        Image(source=uri, style={"width": 120, "height": 120, "borderRadius": 60}) if uri else None,
        Button("Choose photo", lambda: set_taps(taps + 1)),
    )
```

To make the file smaller before upload, pass the result to
[pyxpo-image-manipulator](https://github.com/pyxpo/pyxpo-image-manipulator).

## Errors

| Error | When | What to do |
| --- | --- | --- |
| `ValueError` | Empty `uri` or `source`, a bad `aspectRatio`, a `format` other than "jpeg" or "png", `quality` outside 0 to 1. | Fix the call. |
| `NotSupportedError` | Called on the web page or desktop window. | Crop on iOS or Android only. |
| `ModuleNotLinkedError` (from `pyxpo.module_api`) | Built without `"image-cropper"` in `modules`. | Add it and rebuild. |
| `RuntimeError: the CropView is not mounted` | `ref.current` used before the view is on screen. | Call it from a button. |
| A native error (file missing, not an image) | Bad path. | Check the path. |

## Production checklist

- [ ] You handle `canceled` (the user can always back out).
- [ ] You size the `CropView` with `flex` or a height. It has no size of its own.
- [ ] You delete cropped files when finished (they are in the app cache).
- [ ] For avatars you round the image with `borderRadius` (the file is square).
- [ ] You tested a large photo (12 MP and up) on a real phone.

## Testing

The plain Python parts need no device:

```python
import asyncio

import pyxpo_image_cropper as mod


def test_ratio_is_reduced():
    assert mod._ratio((1.5, 1)) == (3, 2)
    assert mod._ratio(None) == (0, 0)


def test_cropper_with_fake(monkeypatch):
    async def fake_call(native, method, uri, opts, reply=True):
        assert opts["ratioX"] == 1 and opts["circle"]
        return {"canceled": False, "uri": "/c.jpg", "width": 500, "height": 500, "fileSize": 9, "mimeType": "image/jpeg"}

    monkeypatch.setattr(mod, "platform", lambda: "android")
    monkeypatch.setattr(mod, "require_linked", lambda *a, **k: None)
    monkeypatch.setattr(mod, "call", fake_call)
    out = asyncio.run(mod.ImageCropper.open_cropper_async("/a.jpg", circle=True))
    assert out["width"] == 500 and not out["canceled"]
```

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `NotSupportedError: the image cropper needs iOS or Android` | You are in the web or desktop target. |
| `ModuleNotLinkedError` | Add `"image-cropper"` to `modules` and rebuild. |
| The `CropView` is empty | Give it a size (`{"flex": 1}`), and check `on_error`. |
| No flip button in the iOS full-screen cropper | TOCropViewController has no flip. Use `CropView` if you need it. |
| Android build fails on `minSdk` | The cropper needs API 24 or higher. |

## FAQ

**Is the original changed?** No. A new file is written to the app cache.

**Is the circle crop a round PNG?** No, the file is square. Round it on screen with `borderRadius`.

**Can I crop a remote URL?** Download it first, for example with pyxpo-file-system, then pass the local path.

## API reference

### `ImageCropper`

| Method (camelCase name) | Returns |
| --- | --- |
| `open_cropper_async(uri, aspectRatio=None, lockAspectRatio=True, circle=False, rotate=True, flip=True, format="jpeg", quality=0.9, title="")` (`openCropperAsync`) | `{canceled, uri, width, height, fileSize, mimeType}` |

### `CropView`

`CropView(source=..., aspect_ratio=None, circle=False, grid=True, on_change=None, on_error=None, style=None, ref=None)`.
See [CropView](#cropview).

### `CropViewHandle`

| Method | Description |
| --- | --- |
| `rotate(clockwise=True)` | A quarter turn. |
| `flip(horizontal=True)` | Mirror left to right, or top to bottom with `horizontal=False`. |
| `reset()` | Back to the whole photo: no rotation, flip or zoom. |
| `crop_async(format="jpeg", quality=0.9)` (`cropAsync`) | Saves the box as a new file. Same dict as `open_cropper_async`, `canceled` always False. |

## License

MIT
