import Foundation
import UIKit
import TOCropViewController

/// Full-screen cropper on TOCropViewController, and the inline `PxCropView` editor on TOCropView: free or fixed
/// aspect ratio, circle guide, rotate, flip and pinch zoom. The cropped photo is written to the app cache as a new
/// file, so `uri` is a local path.
final class ImageCropperModule: NSObject, PxViewModule, TOCropViewControllerDelegate {
    static let moduleName = "ImageCropper"
    static let viewTypes = ["PxCropView"]

    private var reply: PxReply?
    private var done: (() -> Void)?
    private var format = "jpeg"
    private var quality: CGFloat = 0.9
    private static let queue = DispatchQueue(label: "pyxpo.imagecropper")

    required override init() { super.init() }

    func makeView(_ ctx: PxModuleContext, _ type: String, _ emit: @escaping (String, Any?) -> Void) -> PxNativeView {
        PxCropView(emit)
    }

    func call(_ ctx: PxModuleContext, _ method: String, _ args: [Any], _ reply: @escaping PxReply) {
        func view() -> PxCropView? {
            guard let tag = (args.first as? NSNumber)?.intValue, let v = ctx.view(tag) as? PxCropView else {
                reply(nil, "the CropView is not mounted")
                return nil
            }
            return v
        }
        let flag = args.count > 1 ? (args[1] as? Bool) ?? true : true
        switch method {
        case "crop": crop(ctx, args, reply)
        case "rotate": if let v = view() { v.rotate(clockwise: flag); reply(nil, nil) }
        case "flip": if let v = view() { v.flip(horizontal: flag); reply(nil, nil) }
        case "reset": if let v = view() { v.reset(); reply(nil, nil) }
        case "cropView":
            guard let v = view() else { return }
            let o = (args.count > 1 ? args[1] as? [String: Any] : nil) ?? [:]
            guard let image = v.croppedImage() else { reply(nil, "no photo in the CropView"); return }
            Self.save(image, png: (o["format"] as? String) == "png",
                      quality: CGFloat((o["quality"] as? NSNumber)?.doubleValue ?? 0.9)) { value, error in reply(value, error) }
        default: reply(nil, "unknown native call ImageCropper.\(method)")
        }
    }

    private func crop(_ ctx: PxModuleContext, _ args: [Any], _ reply: @escaping PxReply) {
        if self.reply != nil { reply(nil, "a cropper is already open"); return }
        guard let top = ctx.presenter() else { reply(nil, "no view controller to present the cropper"); return }
        let raw = (args.first as? String) ?? ""
        let path = raw.hasPrefix("file://") ? (URL(string: raw)?.path ?? raw) : raw
        guard let image = UIImage(contentsOfFile: path) else { reply(nil, "cannot open the photo at \(raw)"); return }
        let o = (args.count > 1 ? args[1] as? [String: Any] : nil) ?? [:]
        let rx = (o["ratioX"] as? NSNumber)?.intValue ?? 0, ry = (o["ratioY"] as? NSNumber)?.intValue ?? 0
        let lock = (o["lock"] as? Bool) ?? false, circle = (o["circle"] as? Bool) ?? false
        format = (o["format"] as? String) ?? "jpeg"
        quality = CGFloat((o["quality"] as? NSNumber)?.doubleValue ?? 0.9)

        let vc = TOCropViewController(croppingStyle: circle ? .circular : .default, image: image)
        vc.delegate = self
        if rx > 0 && ry > 0 && !circle { vc.aspectRatioPreset = CGSize(width: rx, height: ry) }
        vc.aspectRatioLockEnabled = lock
        vc.aspectRatioPickerButtonHidden = lock
        vc.resetAspectRatioEnabled = !lock
        vc.rotateButtonsHidden = !((o["rotate"] as? Bool) ?? true)
        if let t = o["title"] as? String, !t.isEmpty { vc.title = t }
        vc.modalPresentationStyle = .fullScreen

        self.reply = reply
        let token = ctx.retain(self)
        done = { ctx.release(token) }
        top.present(vc, animated: true)
    }

    private func finish(_ value: Any?, _ error: String?) {
        let r = reply
        reply = nil
        let d = done
        done = nil
        r?(value, error)
        d?()
    }

    // MARK: TOCropViewControllerDelegate

    // A circular crop also lands here (the circular delegate method is not implemented): the photo stays square.
    func cropViewController(_ cropViewController: TOCropViewController, didCropTo image: UIImage, with cropRect: CGRect, angle: Int) {
        cropViewController.dismiss(animated: true)
        Self.save(image, png: format == "png", quality: quality) { value, error in self.finish(value, error) }
    }

    func cropViewController(_ cropViewController: TOCropViewController, didFinishCancelled cancelled: Bool) {
        cropViewController.dismiss(animated: true)
        finish(["canceled": true], nil)
    }

    /// Writes `image` on the cropper queue, then calls `done` on the main thread with the result dict or an error.
    private static func save(_ image: UIImage, png: Bool, quality: CGFloat, _ done: @escaping (Any?, String?) -> Void) {
        queue.async {
            do {
                let url = try write(image, png: png, quality: quality)
                let size = (try? FileManager.default.attributesOfItem(atPath: url.path)[.size] as? NSNumber)?.intValue ?? 0
                let value: [String: Any] = ["canceled": false, "uri": url.path, "width": Int(image.size.width * image.scale),
                                            "height": Int(image.size.height * image.scale), "fileSize": size,
                                            "mimeType": png ? "image/png" : "image/jpeg"]
                DispatchQueue.main.async { done(value, nil) }
            } catch {
                DispatchQueue.main.async { done(nil, "\(error)") }
            }
        }
    }

    private static func write(_ image: UIImage, png: Bool, quality: CGFloat) throws -> URL {
        let dir = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0].appendingPathComponent("pyxpo-cropped")
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        guard let data = png ? image.pngData() : image.jpegData(compressionQuality: quality) else {
            throw NSError(domain: "ImageCropper", code: 1, userInfo: [NSLocalizedDescriptionKey: "cannot encode the cropped photo"])
        }
        let url = dir.appendingPathComponent(UUID().uuidString + (png ? ".png" : ".jpg"))
        try data.write(to: url, options: .atomic)
        return url
    }
}

/// Lays the crop view out once it has a size: TOCropView needs real bounds before its first layout.
private final class PxCropContainer: UIView {
    var onLayout: (() -> Void)?

    override func layoutSubviews() {
        super.layoutSubviews()
        onLayout?()
    }
}

/// The inline editor: a TOCropView the app drives with its own buttons. TOCropView has no flip, so a flip swaps in
/// a mirrored copy of the photo and mirrors the crop box with it.
final class PxCropView: NSObject, PxNativeView, TOCropViewDelegate {
    private let container = PxCropContainer()
    var view: UIView { container }

    private let emit: (String, Any?) -> Void
    private var source = ""
    private var original: UIImage?
    private var flipX = false  // the photo is mirrored left to right (in photo space, before rotation)
    private var flipY = false
    private var ratio = CGSize.zero
    private var circle = false
    private var grid = true
    private var crop: TOCropView?
    private var ready = false
    private var laidOut = CGSize.zero
    private var resettable = false

    init(_ emit: @escaping (String, Any?) -> Void) {
        self.emit = emit
        super.init()
        container.clipsToBounds = true
        container.backgroundColor = .black
        container.onLayout = { [weak self] in self?.layout() }
    }

    func update(_ props: [String: Any], _ removed: [String]) {
        var rebuild = false
        if let s = props["source"] as? String, s != source {
            source = s
            let path = s.hasPrefix("file://") ? (URL(string: s)?.path ?? s) : s
            original = UIImage(contentsOfFile: path)
            flipX = false
            flipY = false
            rebuild = true
            if original == nil { emit("error", ["message": "cannot open the photo at \(s)"]) }
        }
        if let c = props["circle"] as? Bool, c != circle { circle = c; rebuild = true }
        let rx = (props["ratio_x"] as? NSNumber)?.doubleValue ?? Double(ratio.width)
        let ry = (props["ratio_y"] as? NSNumber)?.doubleValue ?? Double(ratio.height)
        let newRatio = CGSize(width: rx, height: ry)
        let ratioChanged = newRatio != ratio
        ratio = newRatio
        if let g = props["grid"] as? Bool { grid = g; crop?.setGridOverlayHidden(!g, animated: true) }
        if rebuild { build(angle: 0, frame: .zero) } else if ratioChanged { applyRatio(animated: true) }
    }

    func dispose() {
        crop?.removeFromSuperview()
        crop = nil
    }

    // MARK: actions

    func rotate(clockwise: Bool) {
        crop?.rotateImageNinetyDegrees(animated: true, clockwise: clockwise, completion: nil)
    }

    func flip(horizontal: Bool) {
        guard let c = crop, ready else { return }
        let angle = c.angle, f = c.imageCropFrame
        let size = c.image.size
        let turned = abs(angle) % 180 != 0
        let shown = turned ? CGSize(width: size.height, height: size.width) : size  // imageCropFrame is in this space
        var g = f
        if horizontal { g.origin.x = shown.width - f.maxX } else { g.origin.y = shown.height - f.maxY }
        // A left-right flip on screen mirrors the photo top to bottom when it is turned a quarter.
        if horizontal != turned { flipX.toggle() } else { flipY.toggle() }
        build(angle: angle, frame: g)
    }

    func reset() {
        if flipX || flipY {
            flipX = false
            flipY = false
            build(angle: 0, frame: .zero)
        } else {
            crop?.resetLayoutToDefault(animated: true)
        }
    }

    func croppedImage() -> UIImage? {
        guard let c = crop, ready else { return nil }
        return c.image.croppedImage(withFrame: c.imageCropFrame, angle: c.angle, circularClip: false)
    }

    // MARK: layout

    private func build(angle: Int, frame: CGRect) {
        crop?.removeFromSuperview()
        crop = nil
        ready = false
        guard let image = mirrored() else { report(); return }
        let c = TOCropView(croppingStyle: circle ? .circular : .default, image: image)
        c.delegate = self
        c.frame = container.bounds
        c.autoresizingMask = []
        c.gridOverlayHidden = !grid
        c.backgroundColor = .black
        if !circle && ratio.width > 0 && ratio.height > 0 {  // read by the first layout; a restored frame wins after
            c.aspectRatio = ratio
            c.aspectRatioLockEnabled = true
            c.resetAspectRatioEnabled = false
        }
        if angle != 0 { c.angle = angle }
        if !frame.isEmpty { c.imageCropFrame = frame }
        container.addSubview(c)
        crop = c
        laidOut = .zero
        layout()
    }

    private func layout() {
        guard let c = crop else { return }
        let size = container.bounds.size
        guard size.width > 0, size.height > 0, size != laidOut else { return }
        if !ready {
            c.frame = container.bounds
            c.performInitialSetup()
            ready = true
        } else {
            c.prepareforRotation()
            c.frame = container.bounds
            c.performRelayoutForRotation()
        }
        laidOut = size
        report()
    }

    private func applyRatio(animated: Bool) {
        guard let c = crop, ready, !circle else { return }
        let fixed = ratio.width > 0 && ratio.height > 0
        c.aspectRatioLockEnabled = fixed
        c.resetAspectRatioEnabled = !fixed
        if fixed { c.setAspectRatio(ratio, animated: animated) }
    }

    /// The source photo with the current flips drawn in, upright.
    private func mirrored() -> UIImage? {
        guard let image = original else { return nil }
        guard flipX || flipY else { return image }
        let format = UIGraphicsImageRendererFormat()
        format.scale = image.scale
        let size = image.size
        return UIGraphicsImageRenderer(size: size, format: format).image { ctx in
            let g = ctx.cgContext
            g.translateBy(x: flipX ? size.width : 0, y: flipY ? size.height : 0)
            g.scaleBy(x: flipX ? -1 : 1, y: flipY ? -1 : 1)
            image.draw(in: CGRect(origin: .zero, size: size))
        }
    }

    private func report() {
        let now = (crop?.canBeReset ?? false) || flipX || flipY
        guard now != resettable else { return }
        resettable = now
        emit("change", ["resettable": now])
    }

    // MARK: TOCropViewDelegate

    func cropViewDidBecomeResettable(_ cropView: TOCropView) { report() }

    func cropViewDidBecomeNonResettable(_ cropView: TOCropView) { report() }
}
