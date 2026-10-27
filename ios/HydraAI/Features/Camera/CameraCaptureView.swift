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

                    Text("Mock analysis: selected demo responses do not interpret this photo.")
                        .font(.subheadline).foregroundStyle(.secondary)
                    Picker("Demo response", selection: $scenario) {
                        Text("Ambiguous / no match").tag("ambiguous")
                        Text("Branded US cola").tag("branded")
                        Text("Generic coffee").tag("generic")
                        Text("Missing nutrition").tag("missing_nutrition")
                        Text("API failure").tag("failure")
                    }
                    .accessibilityIdentifier("mockScenario")
                    .disabled(isAnalyzing)
                    Toggle("Allow this photo to be sent to my configured backend for this analysis", isOn: $consent)
                        .accessibilityIdentifier("photoConsent")
                        .disabled(isAnalyzing)
                    Button(isAnalyzing ? "Analyzing…" : "Analyze with mock Meta response") {
                        Task { await analyze() }
                    }
                    .buttonStyle(.borderedProminent)
                    .accessibilityIdentifier("analyzePhoto")
                    .disabled(!consent || isAnalyzing)
                    if let result {
                        Text("Mock result — confirmation required").font(.headline)
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

                Text("Photos stay on device until you consent and tap Analyze. A resized copy without original metadata goes only to your configured backend, which uses mock responses and does not save images. No Meta upload occurs. Confirmed logs contain details you approve.")
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
            NavigationStack { RecognitionConfirmationView(candidate: candidate, onSaved: clearPhoto) }
        }
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
        capturedImage = nil; photoItem = nil; result = nil; consent = false
    }

    @MainActor private func analyze() async {
        guard consent, !isAnalyzing, let capturedImage else { return }
        isAnalyzing = true; result = nil
        defer { isAnalyzing = false }
        do {
            guard !store.isOffline else { throw ServiceError.configuration }
            let jpeg = try PhotoPreparation.jpeg(capturedImage)
            let service = try HTTPBeverageService(configuration: store.configuration)
            result = try await service.analyzePhoto(jpeg, scenario: scenario)
        } catch {
            alertTitle = "Analysis unavailable"
            alertMessage = "\(error.localizedDescription) Retry analysis or log manually. No beverage was created."
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
