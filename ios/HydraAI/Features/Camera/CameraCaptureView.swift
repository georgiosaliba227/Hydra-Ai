import AVFoundation
import PhotosUI
import SwiftUI
import UIKit

/// Explicitly consented mock analysis; images are transient, never saved by Hydra.
struct CameraCaptureView: View {
    @EnvironmentObject private var store: BeverageStore
    let onLogManually: () -> Void

    @State private var photoItem: PhotosPickerItem?
    @State private var capturedImage: UIImage?
    @State private var showingCamera = false
    @State private var alertTitle = ""
    @State private var alertMessage: String?

    #if DEBUG
    @State private var libraryFixtureReady = false
    #endif
    @State private var consent = false
    @State private var metaConsent = false
    @State private var recognitionMode: String?
    private var isLive: Bool { recognitionMode == "meta_live" }
    @State private var scenario = "ambiguous"
    @State private var isAnalyzing = false
    @State private var result: RecognitionResult?
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

                    Text(isLive ? "Meta analysis sends this photo to Meta. Recognition is uncertain; verify every suggestion." : "Mock analysis: selected demo responses do not interpret this photo.")
                        .font(.subheadline).foregroundStyle(.secondary)
                    if !isLive { Picker("Demo response", selection: $scenario) {
                        Text("Ambiguous / no match").tag("ambiguous")
                        Text("Branded US cola").tag("branded")
                        Text("Generic coffee").tag("generic")
                        Text("Missing nutrition").tag("missing_nutrition")
                        Text("API failure").tag("failure")
                    }
                    .accessibilityIdentifier("mockScenario")
                    .disabled(isAnalyzing) }
                    Toggle("Allow this photo to be sent to my configured backend for this analysis", isOn: $consent)
                        .accessibilityIdentifier("photoConsent")
                        .disabled(isAnalyzing)
                    if isLive {
                        Toggle("I consent to sending this beverage photo to Meta for AI analysis", isOn: $metaConsent)
                            .accessibilityIdentifier("metaPhotoConsent").disabled(isAnalyzing)
                        Text("Meta may retain content for service, safety and legal purposes. Zero retention is not promised. No location metadata or HealthKit records are sent.").font(.footnote)
                    }
                    Button(isAnalyzing ? "Analyzing…" : (isLive ? "Analyze with Meta" : "Analyze with mock Meta response")) {
                        Task { await analyze() }
                    }
                    .buttonStyle(.borderedProminent)
                    .accessibilityIdentifier("analyzePhoto")
                    .disabled(!consent || isAnalyzing || recognitionMode == nil || (isLive && !metaConsent))
                    if let result {
                        Text(result.mode == "meta_live" ? "Meta result — confirmation required" : "Mock result — confirmation required").font(.headline)
                        ForEach(result.candidates) { candidate in
                            Button("Review \(candidate.identity) (\(candidate.confidence) confidence)") { selectedCandidate = candidate }
                                .buttonStyle(.bordered)
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

                Text("Photos stay on device until you consent and tap Analyze. A resized copy without original metadata goes to your configured backend. In Meta mode, a separate consent is required before the backend sends it to Meta. Images are not saved by Hydra. Confirmed logs contain details you approve.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding()
        }
        .navigationTitle("Capture beverage")
        .sheet(isPresented: $showingCamera) {
            SystemCameraPicker(image: $capturedImage, isPresented: $showingCamera)
                .ignoresSafeArea()
        }
        .sheet(item: $selectedCandidate) { candidate in
            NavigationStack { RecognitionConfirmationView(candidate: candidate, mode: result?.mode ?? "mock", recognitionId: result?.recognitionId, onSaved: clearPhoto) }
        }
        .task { await loadCapabilities() }
        .onChange(of: scenario) { _, _ in result = nil }
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
        capturedImage = nil; photoItem = nil; result = nil; consent = false; metaConsent = false
    }

    @MainActor private func analyze() async {
        guard consent, !isAnalyzing, let mode = recognitionMode, (!isLive || metaConsent), let capturedImage else { return }
        isAnalyzing = true; result = nil
        defer { isAnalyzing = false }
        do {
            guard !store.isOffline else { throw ServiceError.configuration }
            let jpeg = try PhotoPreparation.jpeg(capturedImage)
            let service = try HTTPBeverageService(configuration: store.configuration)
            result = try await service.analyzePhoto(jpeg, scenario: scenario, mode: mode, metaConsent: metaConsent)
        } catch {
            alertTitle = "Analysis unavailable"
            alertMessage = isLive ? "\(error.localizedDescription) Do not retry this Meta attempt. Ask a developer to review the budget ledger and reconcile any uncertain charges. You can log manually; analysis created no beverage." : "\(error.localizedDescription) Retry analysis or log manually. No beverage was created."
        }
    }

    @MainActor private func loadCapabilities() async {
        recognitionMode = nil; consent = false; metaConsent = false; result = nil
        do {
            guard !store.isOffline else { throw ServiceError.configuration }
            let service = try HTTPBeverageService(configuration: store.configuration)
            recognitionMode = try await service.recognitionCapabilities().mode
        } catch {
            alertTitle = "Recognition unavailable"
            alertMessage = "Could not verify the backend recognition mode. \(error.localizedDescription) Reopen Camera after checking Settings."
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
            Text("Take or choose a photo, try mock analysis, then confirm what you drank.")
                .foregroundStyle(.secondary)
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
                    capturedImage = UIGraphicsImageRenderer(size: CGSize(width: 64, height: 64)).image { context in
                        UIColor.blue.setFill(); context.fill(CGRect(x: 0, y: 0, width: 64, height: 64))
                    }
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
            guard let data = try await item.loadTransferable(type: Data.self),
                  data.count <= maximumImageBytes,
                  let image = UIImage(data: data)
            else {
                alertTitle = "Photo unavailable"
                alertMessage = "Choose an image smaller than 12 MB in a supported format."
                photoItem = nil
                return
            }
            capturedImage = image
        } catch {
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
