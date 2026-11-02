import AVFoundation
import PhotosUI
import SwiftUI
import UIKit

/// Explicitly consented recognition; images stay transient unless the user exports them.
struct CameraCaptureView: View {
    @EnvironmentObject private var store: BeverageStore
    let onLogManually: () -> Void

    @State private var photoItem: PhotosPickerItem?
    @State private var preparedPhoto: PreparedRecognitionPhoto?
    private var capturedImage: UIImage? { preparedPhoto?.image }
    @State private var showingCamera = false
    @State private var alertTitle = ""
    @State private var alertMessage: String?

    #if DEBUG
    @State private var libraryFixtureReady = false
    #endif
    @StateObject private var cameraSession = CameraSession()
    private var recognitionMode: String? { cameraSession.mode }
    private var isLoadingCapabilities: Bool { cameraSession.isLoadingCapabilities }
    private var presentation: RecognitionPresentation { RecognitionPresentation(mode: recognitionMode) }
    @State private var scenario = "ambiguous"
    @State private var showingOptions = false
    @State private var scanConsent: ScanConsentContext?
    @State private var photoID = UUID()
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private struct ScanConsentContext: Identifiable {
        let id: UUID
        let generation: UUID
        let mode: String
    }
    private var isAnalyzing: Bool { cameraSession.isAnalyzing }
    private var result: RecognitionResult? { cameraSession.result }
    @State private var selectedCandidate: RecognitionCandidate?

    private let maximumImageBytes = 12 * 1_024 * 1_024

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                header
                BeverageScanStage(image: capturedImage, scanning: isAnalyzing, compact: result != nil)
                if isAnalyzing {
                    Label(presentation == .mock ? "Loading demo result…" : "Scanning your drink…", systemImage: "sparkles")
                        .font(.headline).foregroundStyle(HydraStyle.teal)
                        .accessibilityIdentifier("scanInProgress")
                }
                if capturedImage == nil {
                    captureOptions
                } else if !isAnalyzing {
                    if let result {
                        resultCards(result)
                    } else {
                        Button { presentScanConsent() } label: {
                            Label(presentation == .mock ? "Try demo scan" : "Scan this photo", systemImage: "viewfinder")
                        }
                        .buttonStyle(HydraPressStyle())
                        .disabled(recognitionMode == nil || isLoadingCapabilities)
                        .accessibilityIdentifier("reviewPhotoSharing")
                        Text(presentation == .mock ? "Demo mode uses sample answers; it does not identify your photo." : "Check the photo, then scan to see your drink’s details.")
                            .font(.footnote).foregroundStyle(.secondary)
                            .accessibilityIdentifier("recognitionSource")
                    }
                    HStack {
                        Button("Retake", systemImage: "arrow.counterclockwise") {
                            clearPhoto()
                            Task { await openCamera() }
                        }.disabled(!UIImagePickerController.isSourceTypeAvailable(.camera))
                        Spacer()
                        Button("Discard photo", role: .destructive) { clearPhoto() }
                    }.font(.subheadline)
                    Button("Log beverage manually") { clearPhoto(); onLogManually() }
                        .frame(maxWidth: .infinity)
                }
                if recognitionMode == nil && !isLoadingCapabilities {
                    Label("Scanning is unavailable. Check your connection in Settings, or log a drink manually.", systemImage: "wifi.slash")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }.padding(20)
        }
        .hydraReadableScrollEdges()
        .background(HydraStyle.canvas)
        .navigationTitle("Scan a drink")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { showingOptions = true } label: { Image(systemName: "ellipsis.circle") }
                    .accessibilityLabel("Camera options").accessibilityIdentifier("cameraOptions")
                    .disabled(isAnalyzing)
            }
        }
        .sheet(isPresented: $showingCamera, onDismiss: presentScanConsent) {
            SystemCameraPicker(image: Binding(get: { capturedImage }, set: { selectPhoto($0) }), isPresented: $showingCamera)
                .ignoresSafeArea()
        }
        .sheet(item: $scanConsent) { context in sharingSheet(context) }
        .sheet(isPresented: $showingOptions) { optionsSheet }
        .sheet(item: $selectedCandidate) { candidate in
            NavigationStack { RecognitionConfirmationView(candidate: candidate, mode: result?.mode ?? "mock", recognitionId: result?.recognitionId, onSaved: clearPhoto) }
        }
        .task(id: store.configurationGeneration) { await loadCapabilities() }
        .onChange(of: store.configurationGeneration) { _, generation in
            cameraSession.bind(to: generation)
            selectedCandidate = nil; alertMessage = nil; scanConsent = nil
        }
        .onChange(of: scenario) { _, _ in cameraSession.revokePhotoConsent() }
        .alert(alertTitle, isPresented: Binding(
            get: { alertMessage != nil },
            set: { if !$0 { alertMessage = nil } }
        )) {
            Button("OK", role: .cancel) { alertMessage = nil }
        } message: { Text(alertMessage ?? "") }
        .onChange(of: photoItem) { _, newItem in
            guard let newItem else { return }
            Task { await loadSelectedPhoto(newItem) }
        }
        .animation(reduceMotion ? nil : .easeInOut(duration: 0.25), value: isAnalyzing)
    }

    private func resultCards(_ result: RecognitionResult) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            Label(result.mode == "mock" ? "Demo results" : "Here’s what we found", systemImage: "checkmark.circle.fill")
                .font(.system(.title2, design: .rounded, weight: .bold))
                .accessibilityIdentifier("recognitionResultSource")
            Text(result.mode == "mock" ? "Sample data, not recognition of your photo. Review before logging." : "Check the details before adding what you drank.")
                .font(.footnote).foregroundStyle(.secondary)
            ForEach(result.candidates) { candidate in
                ScanCandidateCard(candidate: candidate) { selectedCandidate = candidate }
            }
            if result.candidates.isEmpty {
                Label("No clear match this time", systemImage: "questionmark.viewfinder").font(.headline)
                Text("Try a clear photo of the label, or add the details yourself.").foregroundStyle(.secondary)
            }
            Button("Enter or correct beverage details") {
                selectedCandidate = RecognitionCandidate(identity: "", productId: nil, containerMl: nil, confidence: "low", uncertaintyReasons: ["Identity, capacity and nutrients are unknown"])
            }.buttonStyle(.bordered)
        }
    }

    private func presentScanConsent() {
        guard preparedPhoto != nil, result == nil, !isAnalyzing, !isLoadingCapabilities,
              let mode = recognitionMode, ["mock", "meta_live"].contains(mode) else { return }
        scanConsent = ScanConsentContext(id: photoID, generation: store.configurationGeneration, mode: mode)
    }

    private func sharingSheet(_ context: ScanConsentContext) -> some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Label("Ready to scan?", systemImage: "sparkles")
                        .font(.system(.title, design: .rounded, weight: .bold))
                    if let capturedImage {
                        Image(uiImage: capturedImage).resizable().scaledToFit().frame(maxWidth: .infinity).frame(height: 160)
                            .clipShape(RoundedRectangle(cornerRadius: 20))
                    }
                    Text(context.mode == "meta_live"
                         ? "Scan photo sends this picture to your connected server and Meta for AI recognition. Meta may retain it for service, safety and legal purposes. Zero retention is not promised."
                         : "Try demo scan sends this picture to your connected server and returns sample data. It does not identify the photo or send it to Meta.")
                        .accessibilityIdentifier("scanSharingDisclosure")
                    Label("Location metadata is removed. No health records are sent. Nothing is logged until you confirm it.", systemImage: "lock.shield")
                        .font(.footnote).foregroundStyle(.secondary)
                    Button {
                        guard context.id == photoID,
                              context.generation == store.configurationGeneration,
                              cameraSession.consentToScan(generation: context.generation, expectedMode: context.mode) else { scanConsent = nil; return }
                        scanConsent = nil
                        Task { await analyze() }
                    } label: {
                        Label(context.mode == "mock" ? "Try demo scan" : "Scan photo", systemImage: "viewfinder")
                    }
                    .buttonStyle(HydraPressStyle())
                    .accessibilityIdentifier("analyzePhoto")
                }.padding(24)
            }
            .toolbar { ToolbarItem(placement: .cancellationAction) {
                Button("Not now") { scanConsent = nil }.accessibilityIdentifier("cancelPhotoScan")
            } }
        }
        .presentationDetents([.large])
    }

    private var optionsSheet: some View {
        NavigationStack {
            Form {
                Section("Connection") {
                    Text(presentation.photoDescription)
                    Button(isLoadingCapabilities ? "Refreshing…" : "Refresh analysis mode") {
                        scanConsent = nil
                        Task { await loadCapabilities() }
                    }.accessibilityIdentifier("refreshRecognitionMode")
                        .disabled(isAnalyzing || isLoadingCapabilities)
                }
                if let preparedPhoto, let capturedImage {
                    Section("Photo approval") {
                        ShareLink(item: preparedPhoto.export, preview: SharePreview("Prepared beverage photo", image: Image(uiImage: capturedImage))) {
                            Label("Export prepared photo for approval", systemImage: "square.and.arrow.up")
                        }.accessibilityIdentifier("exportPreparedPhoto")
                        Text("Exports the exact resized JPEG used for analysis. Export does not approve a scan.").font(.footnote)
                    }
                }
                if presentation == .mock {
                    Section("Demo tools") {
                        Picker("Demo response", selection: $scenario) {
                            Text("Ambiguous / no match").tag("ambiguous")
                            Text("Branded US cola").tag("branded")
                            Text("Generic coffee").tag("generic")
                            Text("Missing nutrition").tag("missing_nutrition")
                            Text("API failure").tag("failure")
                        }.pickerStyle(.menu).accessibilityIdentifier("mockScenario")
                    }
                }
            }
            .navigationTitle("Camera options").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { showingOptions = false } } }
        }
    }

    private func clearPhoto() {
        preparedPhoto = nil; photoItem = nil; selectedCandidate = nil; scanConsent = nil; photoID = UUID()
        cameraSession.revokePhotoConsent()
    }

    @MainActor private func selectPhoto(_ image: UIImage?) {
        // A camera selection must invalidate any older in-flight library load.
        photoItem = nil
        preparedPhoto = nil; selectedCandidate = nil; scanConsent = nil; photoID = UUID()
        cameraSession.revokePhotoConsent()
        guard let image else { return }
        do {
            preparedPhoto = try PreparedRecognitionPhoto(image: image)
            if !showingCamera { presentScanConsent() }
        } catch {
            alertTitle = "Photo unavailable"
            alertMessage = "This photo could not be prepared for analysis. Choose another photo."
            photoItem = nil
        }
    }

    @MainActor private func analyze() async {
        guard let preparedPhoto, !store.isOffline else { return }
        let generation = store.configurationGeneration
        let configuration = store.configuration
        guard let ticket = cameraSession.beginAnalysis(generation: generation), let mode = ticket.mode else { return }
        let metaConsent = cameraSession.metaConsent
        do {
            let service = try HTTPBeverageService(configuration: configuration)
            let next = try await service.analyzePhoto(preparedPhoto.export.jpeg, scenario: scenario, mode: mode, metaConsent: metaConsent)
            guard cameraSession.completeAnalysis(next, ticket: ticket, currentGeneration: store.configurationGeneration) else { return }
            if let receipt = next.recognitionId {
                guard store.registerRecognitionReceipt(receipt, generation: generation) else {
                    cameraSession.revokePhotoConsent()
                    return
                }
            }
        } catch {
            guard cameraSession.completeAnalysis(nil, ticket: ticket, currentGeneration: store.configurationGeneration) else { return }
            alertTitle = "Analysis unavailable"
            alertMessage = mode == "meta_live" ? ServiceError.liveRecognitionUnverified.localizedDescription : "\(error.localizedDescription) Retry analysis or log manually. No beverage was created."
        }
    }

    @MainActor private func loadCapabilities() async {
        guard store.isConfigured, !store.isOffline else { return }
        let generation = store.configurationGeneration
        let configuration = store.configuration
        guard let ticket = cameraSession.beginCapabilities(generation: generation) else { return }
        selectedCandidate = nil
        do {
            guard !configuration.offline else { throw ServiceError.configuration }
            let service = try HTTPBeverageService(configuration: configuration)
            let mode = try await service.recognitionCapabilities().mode
            if cameraSession.completeCapabilities(mode, ticket: ticket, currentGeneration: store.configurationGeneration),
               !showingOptions, !showingCamera { presentScanConsent() }
        } catch {
            guard cameraSession.completeCapabilities(nil, ticket: ticket, currentGeneration: store.configurationGeneration) else { return }
            alertTitle = "Recognition unavailable"
            alertMessage = "Could not verify the backend recognition mode. \(error.localizedDescription) Check Settings, then tap Refresh analysis mode."
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(isAnalyzing ? "A closer look…" : result != nil ? "Meet your drink." : "Sip. Snap. Discover.")
                .font(.system(.largeTitle, design: .rounded, weight: .bold))
                .fixedSize(horizontal: false, vertical: true)
            Text(presentation == .mock ? "Demo mode · sample results" : "Point your camera at a drink. We’ll help with the details.")
                .font(.subheadline).foregroundStyle(.secondary)
                .accessibilityIdentifier("recognitionHeader")
        }
    }

    private var captureOptions: some View {
        VStack(alignment: .leading, spacing: 14) {
            #if DEBUG
            if ProcessInfo.processInfo.environment["HYDRA_TEST_LIBRARY_FIXTURE"] == "1" {
                Button("Add synthetic picker fixture") {
                    Task {
                        do { try await PhotoLibraryTestFixture.add(); libraryFixtureReady = true }
                        catch { alertTitle = "Test fixture unavailable"; alertMessage = "Add-only Photos permission is needed for this opt-in test." }
                    }
                }.accessibilityIdentifier("addLibraryFixture")
                if libraryFixtureReady { Text("Synthetic picker fixture ready").accessibilityIdentifier("libraryFixtureReady") }
            }
            if ProcessInfo.processInfo.environment["HYDRA_TEST_PHOTO_FIXTURE"] == "1" {
                Button("Use synthetic test photo") {
                    selectPhoto(UIGraphicsImageRenderer(size: CGSize(width: 64, height: 64)).image { context in
                        UIColor.blue.setFill(); context.fill(CGRect(x: 0, y: 0, width: 64, height: 64))
                    })
                }.accessibilityIdentifier("syntheticPhoto")
            }
            #endif
            if UIImagePickerController.isSourceTypeAvailable(.camera) {
                Button {
                    Task { await openCamera() }
                } label: {
                    Label("Take photo", systemImage: "camera")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(HydraPressStyle())
            } else {
                Text("Camera capture is unavailable on this device. Choose a photo or log manually.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            PhotosPicker(selection: $photoItem, matching: .images) {
                Label("Choose photo", systemImage: "photo.on.rectangle")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
            .accessibilityIdentifier("chooseBeveragePhoto")

            Button("Log without photo", action: onLogManually)
                .frame(maxWidth: .infinity)
                .buttonStyle(.bordered)
        }
    }

    @MainActor
    private func openCamera() async {
        let status = AVCaptureDevice.authorizationStatus(for: .video)
        switch status {
        case .authorized:
            showingCamera = true
        case .notDetermined:
            showingCamera = await AVCaptureDevice.requestAccess(for: .video)
            if !showingCamera { showCameraPermissionAlert() }
        case .denied, .restricted:
            showCameraPermissionAlert()
        @unknown default:
            showCameraPermissionAlert()
        }
    }

    private func showCameraPermissionAlert() {
        alertTitle = "Camera access needed"
        alertMessage = "Enable camera access in Settings to take a photo. You can still choose an existing photo or log manually."
    }

    @MainActor
    private func loadSelectedPhoto(_ item: PhotosPickerItem) async {
        do {
            let loadedData = try await item.loadTransferable(type: Data.self)
            guard photoItem == item else { return }
            guard let data = loadedData, data.count <= maximumImageBytes,
                  let image = UIImage(data: data)
            else {
                alertTitle = "Photo unavailable"
                alertMessage = "Choose an image smaller than 12 MB in a supported format."
                photoItem = nil
                return
            }
            selectPhoto(image)
        } catch {
            guard photoItem == item else { return }
            alertTitle = "Photo unavailable"
            alertMessage = "The selected photo could not be opened. Try another photo."
            photoItem = nil
        }
    }
}

private struct SystemCameraPicker: UIViewControllerRepresentable {
    @Binding var image: UIImage?
    @Binding var isPresented: Bool

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.mediaTypes = ["public.image"]
        picker.cameraCaptureMode = .photo
        picker.allowsEditing = false
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ picker: UIImagePickerController, context: Context) { }

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    final class Coordinator: NSObject, UINavigationControllerDelegate, UIImagePickerControllerDelegate {
        private let parent: SystemCameraPicker

        init(_ parent: SystemCameraPicker) {
            self.parent = parent
        }

        func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            parent.image = info[.originalImage] as? UIImage
            parent.isPresented = false
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            parent.isPresented = false
        }
    }
}
