//  IOSPlatform.swift — what the iOS platform layer defers, and where it will land.
//
//  Phase 1 (this port) ships the flow the shared tree already draws for its reference device:
//  open a RAW — the import sheet's document picker (Files) or its Photos row
//  (`IOSPhotoImportRow`) — develop and edit it (`PadDevelopPage`'s column folds to the room it
//  has), and export it (the export page's folder picker and `SystemShareSheet`). The window
//  shell (`MainWindowLayout`) is that layout on both platforms: its bar, the browser panel at
//  the right, the mode's content between — the 图库+冲洗 two-pane structure the desktop drew,
//  with the Mac's window keys standing down by themselves where no keyboard asks for them.
//
//  Phase 2, in the order the pages will want it. Each is a gap said in place, none a
//  placeholder that blocks the build:
//
//  - TODO(ios-phase2) an iPhone chrome: the shell's bar and browser are drawn at the Mac-point
//    scale for a windowed Mac (`interfaceScaled(.macPoints)`); a phone wants its own compact
//    bar, the browser as a pushed viewer, and the develop column as sheets.
//  - TODO(ios-phase2) the Light Table on touch: the film's pinch-zoom and the drag on and off
//    the light (`LightTableGestures` reaches `MacScrollMonitor` for the wheel today).
//  - TODO(ios-phase2) saving an export into Photos: the usage string is declared
//    (gen_project.py's `INFOPLIST_KEY_NSPhotoLibraryAddUsageDescription`), the page's Share
//    sheet already carries the file as far as the system's own "Save Image".
//  - TODO(ios-phase2) Capture One sources: the library helper (`spklib-host`) is a macOS
//    binary; an iOS store needs its own reader or none (`CaptureOneSource.host` starts nothing
//    until a view asks, so a touch session only ever sees the refusal).
//  - TODO(ios-phase2) the raw-image encoding of Photos picks: `PHPickerConfiguration`'s
//    `preferredItemEncoding` (iOS 17+) pins the original file for a camera's RAW; the row
//    takes the picker's default until then.
