# Changelog

## 0.1.0a2 (2026-11-02)

- iOS: declares the required-reason APIs it uses (`ios.privacyManifest` in `pyxpo-module.json`), so pyxpo 0.1.0a23 and later add them to the app's `PrivacyInfo.xcprivacy` for App Store review.

## 0.1.0a1 (2026-10-30)

- First release.
- `ImageCropper.openCropperAsync(uri, ...)` (`open_cropper_async`) opens a full-screen cropper: free or fixed aspect ratio, circle guide, rotate, flip (Android) and pinch zoom.
- `CropView`, an inline crop editor. Drive it from `ref.current`: `rotate()`, `flip()`, `reset()` and `crop_async()`.
- iOS uses TOCropViewController 3.2.0; Android uses Android-Image-Cropper 4.7.0 (minSdk 24).
