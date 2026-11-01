"""Image cropper: free or fixed aspect ratio, a circle guide, rotate, flip and pinch zoom.

Two ways to crop: `ImageCropper.openCropperAsync` opens a full-screen cropper, and `CropView` is a crop editor you
place in your own screen and drive with your own buttons. iOS uses TOCropViewController, Android the CanHub
Android-Image-Cropper. The cropped photo is written to the app cache as a new file, so `uri` is a local path; the
source file is never changed."""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, Optional, Sequence

from pyxpo import component, use_imperative_handle, use_ref
from pyxpo.module_api import NotSupportedError, call, native_view, platform, require_linked, snake_aliases, view_tag

__version__ = "0.1.0a2"

_FORMATS = {"jpeg": "image/jpeg", "png": "image/png"}


def _linked() -> None:
    if platform() not in ("ios", "android"):
        raise NotSupportedError("the image cropper needs iOS or Android")
    require_linked("ImageCropper", "image-cropper", package="pyxpo-image-cropper")


def _output(format: str, quality: float) -> None:
    if format not in _FORMATS:
        raise ValueError("format must be 'jpeg' or 'png', got %r" % (format,))
    if isinstance(quality, bool) or not isinstance(quality, (int, float)) or not 0 <= quality <= 1:
        raise ValueError("quality must be a number from 0 to 1")


def _ratio(aspect: Optional[Sequence[float]]) -> "tuple[int, int]":
    """(w, h) as positive whole numbers, or (0, 0) for a free crop. 1.5:1 becomes 3:2."""
    if aspect is None:
        return 0, 0
    try:
        w, h = aspect
    except (TypeError, ValueError):
        raise ValueError("aspectRatio must be a (width, height) pair like (16, 9), or None for a free crop") from None
    for v in (w, h):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
            raise ValueError("aspectRatio values must be positive numbers, got %r" % (aspect,))
    x, y = int(round(w * 1000)), int(round(h * 1000))
    for scale in (1, 10, 100):  # the native croppers take whole numbers
        if float(w * scale).is_integer() and float(h * scale).is_integer():
            x, y = int(w * scale), int(h * scale)
            break
    d = math.gcd(x, y)
    return x // d, y // d


def _result(res: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    res = res or {}
    if res.get("canceled", True) or not res.get("uri"):
        return {"canceled": True, "uri": None, "width": 0, "height": 0, "fileSize": 0, "mimeType": None}
    return {"canceled": False, "uri": res["uri"], "width": int(res.get("width") or 0), "height": int(res.get("height") or 0),
            "fileSize": int(res.get("fileSize") or 0), "mimeType": res.get("mimeType")}


@snake_aliases
class ImageCropper:
    @staticmethod
    async def openCropperAsync(uri: str, aspectRatio: Optional[Sequence[float]] = None, lockAspectRatio: bool = True,
                               circle: bool = False, rotate: bool = True, flip: bool = True, format: str = "jpeg",
                               quality: float = 0.9, title: str = "") -> Dict[str, Any]:
        """Opens the cropper on the photo at `uri` (a local path, `file://` or, on Android, `content://`).

        `aspectRatio` is a `(width, height)` pair such as `(16, 9)`; None starts a free crop. With `lockAspectRatio`
        the user cannot change a given ratio; without it the ratio is only the starting frame. `circle` shows a round
        guide and forces 1:1 (the saved photo stays square; round it with `borderRadius`). `rotate` shows the rotate
        buttons, `flip` the flip actions (Android only; iOS has no flip). `format` is "jpeg" or "png", `quality` the
        JPEG quality from 0 to 1. `title` is the screen title.

        Returns `{"canceled": bool, "uri", "width", "height", "fileSize", "mimeType"}`; `uri` is None when canceled.
        Only one cropper can be open at a time."""
        if not isinstance(uri, str) or not uri:
            raise ValueError("uri must be the path of a photo")
        _output(format, quality)
        rx, ry = (1, 1) if circle else _ratio(aspectRatio)
        _linked()
        opts = {"ratioX": rx, "ratioY": ry, "lock": bool(circle or (rx and lockAspectRatio)), "circle": bool(circle),
                "rotate": bool(rotate), "flip": bool(flip), "format": format, "quality": float(quality), "title": str(title or "")}
        return _result(await call("ImageCropper", "crop", uri, opts, reply=True))


# the inline editor

_View = native_view("PxCropView")


class CropViewHandle:
    """`ref.current` of a mounted `CropView`."""

    def __init__(self, view_ref: Any) -> None:
        self._view = view_ref

    def _tag(self) -> int:
        _linked()
        tag = view_tag(self._view)
        if tag is None:
            raise RuntimeError("the CropView is not mounted")
        return tag

    def rotate(self, clockwise: bool = True) -> None:
        """Turns the photo a quarter turn."""
        call("ImageCropper", "rotate", self._tag(), bool(clockwise))

    def flip(self, horizontal: bool = True) -> None:
        """Mirrors the photo left to right, or top to bottom with `horizontal=False`. The crop box follows."""
        call("ImageCropper", "flip", self._tag(), bool(horizontal))

    def reset(self) -> None:
        """Back to the whole photo: no rotation, no flip, no zoom."""
        call("ImageCropper", "reset", self._tag())

    async def crop_async(self, format: str = "jpeg", quality: float = 0.9) -> Dict[str, Any]:
        """Saves what is inside the crop box as a new file. Returns the same dict as `openCropperAsync`
        (`canceled` is always False)."""
        _output(format, quality)
        tag = self._tag()
        return _result(await call("ImageCropper", "cropView", tag, {"format": format, "quality": float(quality)}, reply=True))

    cropAsync = crop_async


@component
def CropView(source: str, aspect_ratio: Optional[Sequence[float]] = None, circle: bool = False, grid: bool = True,
             on_change: Optional[Callable[[Dict[str, Any]], Any]] = None,
             on_error: Optional[Callable[[Dict[str, Any]], Any]] = None, style: Any = None, **props: Any):
    """A crop editor for the photo at `source` (a local path or `file://`; on Android also `content://`), sized by
    `style`. The user drags the crop box and pinches to zoom; drive the rest from `ref.current`, a `CropViewHandle`.

    `aspect_ratio` is a `(width, height)` pair that locks the box, or None for a free box; changing it reshapes the
    box. `circle` shows a round guide and locks 1:1 (the saved photo stays square). `grid` shows the thirds grid.
    `on_change({"resettable": bool})` runs when the crop moves away from or back to the whole photo.
    `on_error({"message"})` runs when the photo cannot be opened."""
    if not isinstance(source, str) or not source:
        raise ValueError("source must be the path of a photo")
    ref = props.pop("ref", None)
    inner = use_ref(None)
    use_imperative_handle(ref, lambda: CropViewHandle(inner), [])
    rx, ry = (1, 1) if circle else _ratio(aspect_ratio)
    wire: Dict[str, Any] = {"source": source, "ratio_x": rx, "ratio_y": ry, "circle": bool(circle), "grid": bool(grid)}
    if on_change is not None:
        wire["on_change"] = on_change
    if on_error is not None:
        wire["on_error"] = on_error
    return _View(ref=inner, style=style, **wire, **props)


__all__ = ["CropView", "CropViewHandle", "ImageCropper", "NotSupportedError"]
