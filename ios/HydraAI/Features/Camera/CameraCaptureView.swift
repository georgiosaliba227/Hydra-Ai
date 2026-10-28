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
    private var consent: Bool { cameraSession.consent }
    private var metaConsent: Bool { cameraSession.metaConsent }
    private var recognitionMode: String? { cameraSession.mode }
    private var isLoadingCapabilities: Bool { cameraSession.isLoadingCapabilities }
    private var presentation: RecognitionPresentation { RecognitionPresentation(mode: recognitionMode) }
    private var isLive: Bool { recognitionMode == "meta_live" }
    @State private var scenario = "ambiguous"
    private var isAnalyzing: Bool { cameraSession.isAnalyzing }
    private var result: RecognitionResult? { cameraSession.result }
    @State private var selectedCandidate: RecognitionCandidate?

    private let maximumImageBytes = 12 * 1_024 * 1_024

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                header

                if let capturedImage {
                    Image(uiImage: capturedImage)
                        .resizable()
                        .scaledToFit()
                        .frame(maxWidth: .infinity)
                        .frame(maxHeight: 360)
                        .background(.quaternary, in: RoundedRectangle(cornerRadius: 16))
                        .clipShape(RoundedRectangle(cornerRadius: 16))
                        .accessibilityLabel("Selected beverage photo")

                    if let preparedPhoto {
                        ShareLink(item: preparedPhoto.export, preview: SharePreview("Prepared beverage photo", image: Image(uiImage: capturedImage))) {
                            Label("Export prepared photo for approval", systemImage: "square.and.arrow.up")
                        }
                        .accessibilityIdentifier("exportPreparedPhoto")
                        .disabled(isAnalyzing)
                        Text("Share this exact resized JPEG with your developer for image approval. Analysis uses the same copy. Exporting does not approve analysis or automatically send it to Meta.")
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                    Text(presentation.photoDescription)
                        .font(.subheadline).foregroundStyle(.secondary)
                        .accessibilityIdentifier("recognitionSource")
                    if presentation == .mock { Picker("Demo response", selection: $scenario) {
                        Text("Ambiguous / no match").tag("ambiguous")
                        Text("Branded US cola").tag("branded")
                        Text("Generic coffee").tag("generic")
                        Text("Missing nutrition").tag("missing_nutrition")
                        Text("API failure").tag("failure")
                    }
                    .accessibilityIdentifier("mockScenario")
                    .disabled(isAnalyzing) }
                    Toggle("Allow this photo to be sent to my configured backend for this analysis", isOn: $cameraSession.consent)
                        .accessibilityIdentifier("photoConsent")
                        .disabled(isAnalyzing || isLoadingCapabilities)
                    if isLive {
                        Toggle("I consent to sending this beverage photo to Meta for AI analysis", isOn: $cameraSession.metaConsent)
                            .accessibilityIdentifier("metaPhotoConsent").disabled(isAnalyzing || isLoadingCapabilities)
                        Text("Meta may retain content for service, safety and legal purposes. Zero retention is not promised. No location metadata or HealthKit records are sent.").font(.footnote)
                    }
                    Button(isAnalyzing ? "Analyzing…" : presentation.analyzeTitle) {
                        Task { await analyze() }
                    }
                    .buttonStyle(.borderedProminent)
                    .accessibilityIdentifier("analyzePhoto")
                    .disabled(!consent || isAnalyzing || recognitionMode == nil || (isLive && !metaConsent))
                    if let result {
                        Text(RecognitionPresentation(mode: result.mode).resultTitle).font(.headline)
                            .accessibilityIdentifier("recognitionResultSource")
                        ForEach(result.candidates) { candidate in
                            Button("Review \(candidate.identity) (\(candidate.confidence) confidence)") { selectedCandidate = candidate }
                                .buttonStyle(.bordered)
                                .accessibilityIdentifier("recognitionCandidate-\(candidate.id.uuidString)")
                        }
                        if result.candidates.isEmpty {
                            Text("No confident match. Retake the photo or enter the identity and capacity yourself.")
                        }
                        Button("Enter or correct beverage details") {
                            selectedCandidate = RecognitionCandidate(identity: "", productId: nil, containerMl: nil, confidence: "low", uncertaintyReasons: ["Identity, capacity and nutrients are unknown"])
                        }
                    }

                    Button("Log beverage manually") {
                        // Manual logging receives no image or inferred beverage details.
                        clearPhoto()
                        onLogManually()
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(isAnalyzing)

                    Button("Discard photo", role: .destructive) {
                        clearPhoto()
                    }
                    .buttonStyle(.bordered)
                    .disabled(isAnalyzing)
                } else {
                    captureOptions
                }

                Text("Photos stay on device unless you choose Export or consent and tap Analyze. A resized copy without original metadata goes to your configured backend. In Meta mode, a separate consent is required before the backend sends it to Meta. Only an export you choose saves or shares a separate copy. Confirmed logs contain details you approve.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding()
        }
        .navigationTitle("Capture beverage")
        .sheet(isPresented: $showingCamera) {
            SystemCameraPicker(image: Binding(get: { capturedImage }, set: { selectPhoto($0) }), isPresented: $showingCamera)
                .ignoresSafeArea()
        }
        .sheet(item: $selectedCandidate) { candidate in
            NavigationStack { RecognitionConfirmationView(candidate: candidate, mode: result?.mode ?? "mock", recognitionId: result?.recognitionId, onSaved: clearPhoto) }
        }
        .task(id: store.configurationGeneration) { await loadCapabilities() }
        .onChange(of: store.configurationGeneration) { _, generation in
            cameraSession.bind(to: generation)
            selectedCandidate = nil; alertMessage = nil
        }
        .onChange(of: scenario) { _, _ in cameraSession.discardResult() }
        .alert(alertTitle, isPresented: Binding(
            get: { alertMessage != nil },
            set: { if !$0 { alertMessage = nil } }
        )) {
            Button("OK", role: .cancel) { alertMessage = nil }
        } message: {
            Text(alertMessage ?? "")
        }
        .onChange(of: photoItem) { _, newItem in
            guard let newItem else { return }
            Task {
                await loadSelectedPhoto(newItem)
            }
        }
    }

    private func clearPhoto() {
        preparedPhoto = nil; photoItem = nil; selectedCandidate = nil
        cameraSession.revokePhotoConsent()
    }

    @MainActor private func selectPhoto(_ image: UIImage?) {
        // A camera selection must invalidate any older in-flight library load.
        photoItem = nil
        preparedPhoto = nil; selectedCandidate = nil
        cameraSession.revokePhotoConsent()
        guard let image else { return }
        do {
            preparedPhoto = try PreparedRecognitionPhoto(image: image)
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
        let generation = store.configurationGeneration
        let configuration = store.configuration
        guard let ticket = cameraSession.beginCapabilities(generation: generation) else { return }
        selectedCandidate = nil
        do {
            guard !configuration.offline else { throw ServiceError.configuration }
            let service = try HTTPBeverageService(configuration: configuration)
            let mode = try await service.recognitionCapabilities().mode
            _ = cameraSession.completeCapabilities(mode, ticket: ticket, currentGeneration: store.configurationGeneration)
        } catch {
            guard cameraSession.completeCapabilities(nil, ticket: ticket, currentGeneration: store.configurationGeneration) else { return }
            alertTitle = "Recognition unavailable"
            alertMessage = "Could not verify the backend recognition mode. \(error.localizedDescription) Check Settings, then tap Refresh analysis mode."
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 8) {
            Image(systemName: "camera.viewfinder")
                .font(.largeTitle)
                .foregroundStyle(.cyan)
                .accessibilityHidden(true)
            Text("Add a beverage photo")
                .font(.title2.bold())
            Text(presentation.header)
                .foregroundStyle(.secondary)
                .accessibilityIdentifier("recognitionHeader")
            Button(isLoadingCapabilities ? "Refreshing analysis mode…" : "Refresh analysis mode") {
                Task { await loadCapabilities() }
            }
            .accessibilityIdentifier("refreshRecognitionMode")
            .disabled(isAnalyzing || isLoadingCapabilities)
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
                .buttonStyle(.borderedProminent)
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
