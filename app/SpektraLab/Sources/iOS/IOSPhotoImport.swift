//  IOSPhotoImport.swift — the import sheet's Photos row, the iOS platform layer's own
//  (IOS-PORT-NOTES.md §4).
//
//  One way in on the iPhone and the iPad that the Mac's sheet does not have: the system's photo
//  picker (PHPicker underneath, which asks for no permission), its pictures copied in exactly as
//  the document picker's files are (`ImportService.copyIn`: probe the header, keep the app's own
//  copy, make the frame, join the develop queue). A camera's RAW that Photos holds arrives as its
//  file; whatever the picker cannot hand over reads as "nothing could be read", the files' rows'
//  note (`ImportSheet.failed`).
//
//  The file compiles on the Mac too (PhotosUI is a Catalyst framework) but its row is attached
//  under `#if !targetEnvironment(macCatalyst)` — `os(iOS)` is true under Catalyst, so that is
//  the guard that keeps the Mac's two-row sheet as it was.

import PhotosUI
import SwiftUI

/// The sheet's third way in, and the picker it presents. Owns nothing the sheet does not hand it:
/// the "Copying" state and the failure note are the sheet's (`working`, `failed`), the dismissal
/// and the services are the environment's — the same shape the sheet's own rows take.
@MainActor
struct IOSPhotoImportRow: View {
    @Environment(AppServices.self) private var model
    @Environment(AppRouter.self) private var router
    @Environment(\.isSnapshot) private var isSnapshot
    @Binding var working: String?
    @Binding var failed: Bool
    @State private var picking = false
    /// The picked items, held only between the picker's answer and the copy's start.
    @State private var picked: [PhotosPickerItem] = []

    var body: some View {
        SourceRow(icon: .importPhotos, title: L("From Photos"), sub: L("Pictures and RAWs copied in"),
                  trailing: working == "photos" ? L("Copying") : nil) {
            guard !isSnapshot else { return }
            failed = false
            picking = true
        }
        .photosPicker(isPresented: $picking, selection: $picked, matching: .images)
        .onChange(of: picked) { _, items in
            guard !items.isEmpty else { return }
            picked = []
            working = "photos"
            Task {
                let count = await bring(items)
                working = nil
                if count > 0 { router.dismissSheet() } else { failed = true }
            }
        }
    }

    /// The picked originals, copied in; how many arrived. `loadTransferable(type: URL.self)`
    /// hands one file per item, a copy the system makes in its own temporary directory — a
    /// security-scoped one, whose access `ImportService.copyIn` already opens and closes.
    private func bring(_ items: [PhotosPickerItem]) async -> Int {
        var urls: [URL] = []
        for item in items {
            if let url = try? await item.loadTransferable(type: URL.self) { urls.append(url) }
        }
        guard !urls.isEmpty else { return 0 }
        return await ImportService(model: model).copyIn(urls)
    }
}
