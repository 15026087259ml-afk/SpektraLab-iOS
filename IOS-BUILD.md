# SpektraLab for iPhone and iPad — build notes

The iOS port of the Mac app (`app/SpektraLab`): the same source tree, the same engine, one
generated project with two targets. `SpektraLab` stays the Mac Catalyst app exactly as 2.3.2
built it; `SpektraLab-iOS` is the iPhone and iPad app (iOS 18+). What the survey found and why
the port is shaped the way it is lives in [`IOS-PORT-NOTES.md`](IOS-PORT-NOTES.md); this file
is how to build and what to expect.

## Build (a Mac)

Prerequisites, the Mac app's own: Apple-silicon Mac, macOS 15 or later, **Xcode 27 or later**
with its Metal toolchain component (Xcode 26 cannot type-check parts of the app; since Xcode 26
the Metal compiler is a separate component — `xcodebuild -downloadComponent MetalToolchain`).

```bash
app/SpektraLab/tools/build_engine_ios.sh       # the engine for the device AND the simulator, its kernels, its resources
cd app/SpektraLab
python3 gen_project.py                         # writes SpektraLab.xcodeproj with both targets
xcodebuild -project SpektraLab.xcodeproj -scheme SpektraLab-iOS -configuration Debug \
    -destination 'platform=iOS Simulator,name=iPhone 16 Pro' \
    -derivedDataPath build/DerivedData build
xcrun simctl install "iPhone 16 Pro" build/DerivedData/Build/Products/Debug-iphonesimulator/SpektraLab-iOS.app
xcrun simctl launch "iPhone 16 Pro" com.spektralab.ios.local
```

- `build_engine_ios.sh` compiles `engine/` (C++20, `-O2`, the Metal kernels with safe math for
  iOS 18) twice — `build/engine-iphoneos/libspektralab_engine.a` for the device and
  `build/engine-iphonesimulator/libspektralab_engine.a` for the simulator — and lays the baked
  constants, the profiles and `spektralab.metallib` into each folder's `EngineResources/`, which
  the build copies into the app bundle. Run it again after any change under `engine/`. The
  kernels are built once (`air64-apple-ios18.0`): a metallib is not per-simulator.
- `gen_project.py` generates the project from the files on disk — run it again after adding or
  removing a source file. Without an engine build the targets are the interface over
  `SimulatedEngine` (`--no-engine` forces that); with one, each target links its own platform's
  library. The Mac target's settings are generated exactly as 2.3.2 generated them.
- **Signing.** Without `--team` both targets sign to run locally (`CODE_SIGN_IDENTITY = "-"`):
  that runs on any simulator. A **device** build of `SpektraLab-iOS` needs a development team:

  ```bash
  python3 gen_project.py --team YOUR_TEAM_ID
  xcodebuild -project SpektraLab.xcodeproj -scheme SpektraLab-iOS -configuration Debug \
      -destination 'platform=iOS' -allowProvisioningUpdates build
  ```

  The default bundle ids follow the Mac's pattern: `com.spektralab.mac.local` /
  `com.spektralab.ios.local`, or `…mac.<team>` / `…ios.<team>` with a team. `--ios-bundle-id`
  overrides the iOS one.
- The engine's metallib stamp is checked against the app's 18.0 floor at build time; a metallib
  stamped for a newer iOS than the device's would not load — the app would open and not render.

## CI

`.github/workflows/ios.yml` (GitHub-hosted, the `xcode-27` image build.yml uses — the app needs
Xcode 27, which the macos-15 images do not carry): checkout → Xcode 27 → the Metal toolchain
component behind a best-effort cache (`~/Library/Caches/com.apple.dt.Xcode`; the download stays
as the fallback, because a cache restores files while `xcodebuild -downloadComponent` installs
them) → `build_engine_ios.sh` → `gen_project.py` → `xcodebuild` for the iPhone 16 Pro
simulator, or the generic simulator destination when the image carries another family → the
`.app` zipped as the `SpektraLab-iOS-sim` artifact (installable with `xcrun simctl install`).
It runs on pushes to `main` and `ios-port`, on every pull request, and by hand.

What CI does not run, deliberately: the engine's parity harnesses need the Python oracle, which
is not this repository (`docs/agents/BUILD-AND-TEST.md`), and the app's self-tests
(`tools/selftest.sh`) compile Mac-host tools — both are the pre-push gates on a Mac, as
AGENTS.md's "Test gates" says. The Mac target's own gate is `build.yml`, which runs on every
pull request.

## What works, and what is Phase 2

Phase 1 is the flow the shared tree already draws for its reference device, now compiled and
shipped for iOS:

- **Open a RAW** — the Import sheet's document picker (Files: Link a folder, Copy files in) and
  its new **From Photos** row (`Sources/iOS/IOSPhotoImport.swift`), the system's picker, whose
  pictures are copied in exactly as the document picker's files are. No photo-library permission
  is asked to pick; the usage strings are declared for the read reason and for a future
  *save back to Photos*.
- **Develop and edit** — the develop page's column folds to the room it has; every parameter is
  the shared page's.
- **Export** — the export page's folder picker and the system share sheet, as on the reference
  device.

Phase 2, each gap said in place in `Sources/iOS/IOSPlatform.swift` (`TODO(ios-phase2)`):

- an iPhone chrome: the window shell (`MainWindowLayout`) draws its bar and browser at the
  Mac-point scale for a windowed Mac; a phone wants its own compact bar and a pushed viewer;
- the Light Table's gestures (the film's pinch-zoom, drag on and off the light) on touch;
- saving an export into Photos (the AddUsage string is declared; Share already reaches the
  system's own "Save Image");
- Capture One sources (the library helper `spklib-host` is a macOS binary);
- pinning the photo picker to the RAW's original file (`preferredItemEncoding`).

The window/keyboard layer (shortcuts, the key anchor, the ⌘-HUD menus) is compiled and inert on
touch — it serves iPad with a hardware keyboard, as on the Mac.

## GPL compliance

The app is GPL-3.0-or-later (the engine is derived from spektrafilm by Andrea Volpato); the film
profiles it ships are CC BY-SA 4.0 with their own attribution (`license/SPEKTRAFILM_LICENSE.txt`,
copied into `EngineResources/LICENSE-PROFILES.txt` by both engine build scripts; the profiles'
baked sources carry `PRODUCT_PROFILES_NOTICE.md`). Nothing in the port changes the licensing:

- the source remains the offer: a distribution of the iOS app must make this repository's
  corresponding source available on the same terms (the README's and `license/`'s notices travel
  with the tree; the bundle carries `EngineResources/ENGINE-COMMIT.txt`, naming the engine
  revision the build was made from);
- no new dependency was added to the iOS build — the port compiles the repository's own code
  against Apple's SDKs, which are system libraries for this purpose;
- App Store distribution of a GPL app is the owner's decision to make, not this port's; the
  port changes nothing about it (the update feed is off for the iOS target: an App Store build
  does not check a DMG manifest).
