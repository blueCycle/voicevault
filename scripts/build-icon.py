#!/usr/bin/env python3
"""Generate VoiceVault menu-bar template icon from macOS SF Symbols.

Produces:
    data/voicevault_icon.png        @1x 22x22
    data/voicevault_icon@2x.png     @2x 44x44

Both PNGs are flagged as macOS template images (monochrome) so they
inherit the system menubar tint (dark or light) automatically. No
external image dependencies — uses only PyObjC (already pulled in by
rumps).
"""

import sys
from pathlib import Path
from AppKit import (
    NSImage,
    NSGraphicsContext,
    NSBitmapImageRep,
    NSBitmapImageFileTypePNG,
    NSCompositingOperationCopy,
)
from Foundation import NSRect  # noqa: F401  (ensures symbol loaded)

ROOT = Path(__file__).resolve().parent.parent
OUT_1X = ROOT / "data" / "voicevault_icon.png"
OUT_2X = ROOT / "data" / "voicevault_icon@2x.png"
OUT_MASTER = ROOT / "data" / "icon_master.png"

SYMBOL_NAME = "mic.fill"


def _rasterize(symbol: NSImage, size_px: int) -> NSBitmapImageRep:
    """Render the SF Symbol into an NSBitmapImageRep of size_px x size_px.

    Anchored on an explicit bitmap rep so the output size is exact —
    NSImage.lockFocus() doesn't reliably honor initWithSize: without one.
    """
    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, size_px, size_px, 8, 4, True, False, "NSDeviceRGBColorSpace", 0, 32
    )
    if rep is None:
        raise RuntimeError(f"Bitmap rep alloc failed for {size_px}x{size_px}")

    ctx = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(ctx)
    try:
        src_w, src_h = symbol.size().width, symbol.size().height
        dst = ((0.0, 0.0), (float(size_px), float(size_px)))
        src = ((0.0, 0.0), (float(src_w), float(src_h)))
        symbol.drawInRect_fromRect_operation_fraction_(
            dst, src, NSCompositingOperationCopy, 1.0
        )
    finally:
        NSGraphicsContext.restoreGraphicsState()
    return rep


def _save_png(rep: NSBitmapImageRep, path: Path):
    data = rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, None)
    if data is None or not data.writeToFile_atomically_(str(path), True):
        raise RuntimeError(f"PNG write failed for {path}")


def build():
    sym = NSImage.imageWithSystemSymbolName_accessibilityDescription_(SYMBOL_NAME, None)
    if sym is None:
        raise RuntimeError(
            f"SF Symbol {SYMBOL_NAME!r} not available. Requires macOS 11+."
        )
    sym.setTemplate_(True)

    OUT_1X.parent.mkdir(parents=True, exist_ok=True)
    _save_png(_rasterize(sym, 22), OUT_1X)
    _save_png(_rasterize(sym, 44), OUT_2X)
    # High-res master used by `iconutil` to produce a multi-size .icns
    # for the bundled .app. 1024x1024 is the largest size Finder/Spotlight
    # expects in a modern .iconset.
    _save_png(_rasterize(sym, 1024), OUT_MASTER)
    print(f"wrote {OUT_1X.relative_to(ROOT)}")
    print(f"wrote {OUT_2X.relative_to(ROOT)}")
    print(f"wrote {OUT_MASTER.relative_to(ROOT)}")
    return OUT_1X, OUT_2X, OUT_MASTER


if __name__ == "__main__":
    try:
        build()
    except Exception as e:
        print(f"[build-icon] failed: {e}", file=sys.stderr)
        sys.exit(1)
