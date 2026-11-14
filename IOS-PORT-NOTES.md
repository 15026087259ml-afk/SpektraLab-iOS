# iOS Port — Inventory Notes

What the survey of the v2.3.2 desktop tree found, and what the iOS port does with each finding.
This file is the survey; `IOS-BUILD.md` is the build manual. Nothing here changes the desktop app.

## 1. How the desktop project is generated (`app/SpektraLab/gen_project.py`)

- One Mac Catalyst app target "SpektraLab": every `Sources/**/*.swift` plus the bridging header
  (`Sources/Support/SpektraLab-Bridging-Header.h`, the engine's C ABI), the resources under
  `Resources/`, and `build/SampleFrames` (the demo library's pictures, copied from
  `SampleSources/`).
- `SDKROOT = iphoneos` with `SUPPORTS_MACCATALYST = YES`; the deployment target is 17.0 with
  `[sdk=macosx*] = 18.0` (the iOS target's own floor is 18.0 — the shared tree's drag and
  marquee recognisers are `UIGestureRecognizerRepresentable`, iOS 18+, unguarded). **A Catalyst build compiles the app against the iOS SDK.**
- The engine is linked where `tools/build_engine_mac.sh` has left one
  (`build/engine-macosx/{libspektralab_engine.a, EngineResources/}`), via
  `OTHER_LDFLAGS[sdk=macosx*]` and the `SPK_ENGINE` compilation condition; the engine resources
  folder is copied by a `PBXShellScriptBuildPhase` that reads `$PLATFORM_NAME` (`macosx` for a
  Catalyst build). Without the library the app builds the scheduler over `SimulatedEngine`.
- The kernels are never compiled by Xcode (no `.metal` file in any target).
- Object ids are `sha1(name)` — regenerating is stable; adding a file needs no project edit.

## 2. Platform coupling — what the survey found

The app has **no AppKit import anywhere** (checked: `grep "import AppKit|Cocoa" Sources/` → none).
317 Swift files import only SwiftUI / UIKit / Foundation / Metal / ImageIO / Accelerate etc.
Mac behaviour is reached *through the runtime* (`NSClassFromString("NSOpenPanel")`,
`NSSelectorFromString`, key-value access), so it compiles for any iOS platform and no-ops where
the class does not exist. Concretely:

- `Sources/Mac/` (74 files) is the **window layer, not an AppKit layer**: the shell
  (`MainWindowLayout`), the library page (`MacLibraryPage` — also what `LibraryScreen` shows),
  the export page (`MacExportPage` — also what the router presents for `.export`), the settings
  window (`SettingsWindowRoot`), the key registry (`MacShortcutRegistry`, `UIKeyCommand`),
  the scroll/zoom and display helpers. **26 files outside `Sources/Mac/` reference symbols
  defined in `Sources/Mac/`** (measured with `tools/xref-mac-symbols.py` of this port), among
  them `AppServices` (→ `CatalogSourcesStore`, `MacRenderCache`), `RootView` (→
  `MainWindowLayout`, `MacShellPath`, `MacWindow`), `Routes` (→ `SettingsWindowRoot`),
  `LibraryScreen` (→ `MacLibraryPage`), `PadDevelopPage` (→ `MacShellBar`, `MacInfoStrip`).
  Excluding `Sources/Mac/` from the iOS target is therefore **not compile-safe**: the iOS target
  compiles the same source tree as the Mac one. Mac-only *behaviour* stays out of the way at
  runtime (runtime lookups return nil on iOS; every harness checks `CommandLine.arguments`
  before doing anything).
- Genuinely Catalyst-only APIs, found by scanning for the windowing surface: `scene.titlebar`
  (in `Tour.swift` and `Mac/MacWindow.swift`; Mac Catalyst 13.0+ only, per Apple's docs JSON)
  → wrapped in `#if targetEnvironment(macCatalyst)`. `scene.sizeRestrictions` is iOS 13.0+
  (harmless on a device: the scene has no window to restrict). `Scene.commands` and the
  `Commands` protocol are iOS 14.0+ (they feed iPad's ⌘-HUD), so the menu commands compile.
- Existing conditional compilation is small and already platform-aware:
  `Sources/Features/Develop/HDRDisplays.swift` and `HDRImage.swift` guard Catalyst display
  code; `Sources/App/AppServices.swift` guards simulator/Catalyst; `Sources/Model/Localization.swift`
  uses `canImport(UIKit)`; `Sources/Mac/MacScrollZoom.swift` and `MacFlowBar.swift` note it.
- Import/export: the shared `Features/Import/ImportSheet.swift` already drives
  `fileImporter` (`.rawImage`, `.image`, folders), and the shared `Features/Export/ExportSheet.swift`
  has `SystemShareSheet` (a `UIActivityViewController` wrapper). The Mac pages add Finder-panel
  and destination-folder polish on top (runtime-guarded). **The Phase 1 flow — open a RAW,
  develop it, export or share it — is already written in platform-neutral SwiftUI.**
- Engine resources: read from `Bundle.main.resourceURL/EngineResources` (`EngineRouter.swift`),
  the layout both platforms copy to. The demo pictures come from `build/SampleFrames`.

## 3. Engine build (`tools/build_engine_mac.sh`, `engine/build.sh`)

- Compiles `engine/src/{core,gpu,pipeline}/*.cpp` with clang, `-std=c++20 -O2 -Wall -Wextra`,
  targets `arm64/x86_64-apple-ios18.0-macabi`, links via `libtool -static` + `lipo`.
- The kernels: `xcrun metal -fmetal-math-mode=safe -fmetal-math-fp32-functions=precise`
  (`engine/build.sh` trap 1 — the engine *refuses* a fast-math metallib at startup), `-mmacos-version-min=15.0`.
- Resources: `engine/resources/` (minus `*.metallib/metalar`) + `engine/resources_product/profiles`
  + the CC BY-SA notice + `ENGINE-COMMIT.txt`; `metallib` stitches the `.air` files;
  `engine/tools/build_metal_archive.sh` bakes the optional `.metalar` **with a host tool**
  (macosx SDK — works on any Mac build host regardless of the target platform).
- The compiled C++ set is iOS-clean: POSIX mmap/mman in `blob.cpp`/`disk_checkpoint.cpp`,
  `dispatch/dispatch.h` in `contrast_mask.cpp`, Accelerate/CoreGraphics/CoreText in `overscan.cpp`
  — all exist on iOS. `vulkan_gpu.cpp` is `#ifndef __APPLE__`. Nothing under `src/desktop`
  or `src/io` is compiled into the app.

## 4. What the port adds (this branch)

| piece | where | note |
|---|---|---|
| iOS engine build | `app/SpektraLab/tools/build_engine_ios.sh` | same flags/standard as the mac script; `air64-apple-ios18.0` Metal target; output `build/engine-iphoneos/` and `build/engine-iphonesimulator/` |
| dual-platform generator | `app/SpektraLab/gen_project.py` | adds the `SpektraLab-iOS` target next to the Mac one; the Mac target's generated settings are byte-identical to 2.3.2's |
| iOS platform layer | `app/SpektraLab/Sources/iOS/` | the import sheet's Photos row (`IOSPhotoImportRow`, the system picker, no permission asked); does **not** duplicate Mac types |
| Catalyst-only guards | `Tour.swift`, `Mac/MacWindow.swift` | `#if targetEnvironment(macCatalyst)` around `scene.titlebar` |
| Info.plist keys | gen_project target settings | photo-library usage strings, orientations, launch screen — iOS target only |
| CI | `.github/workflows/ios.yml` | engine (iOS) → project → `xcodebuild` iPhone 16 Pro simulator |
| docs | `IOS-BUILD.md` | local Mac build, CI, limitations, GPL notes |

## 5. Deliberate exclusions (Phase 2)

Light Table's Mac shell, Capture One sources (the helper `spklib-host` is a macOS binary),
the update feed check (`UpdateCheck` — App Store builds do not self-update), the Finder drop
zone. These compile (they are runtime-guarded) but are not wired to iOS gestures yet; each
carries a TODO where the gap is felt. The window/keyboard layer (shortcuts, key anchor,
multi-window) is inert on iPhone/iPad touch use and kept for iPad-with-keyboard parity.
