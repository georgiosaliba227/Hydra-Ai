import AVFoundation
import PhotosUI
import SwiftUI
import UIKit

/// An offline capture flow. Images stay in memory and are never sent or saved here.
struct CameraCaptureView: View {
    let onLogManually: () -> Void

    @State private var photoItem: PhotosPickerItem?
    @State private var capturedImage: UIImage?
    @State private var showingCamera = false
    @State private var alertTitle = ""
    @State private var alertMessage: String?

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

                    Label("Recognition is unavailable in this mock build. Confirm the beverage and amount in the manual log.", systemImage: "info.circle")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)

                    Button("Log beverage manually") {
                        // Manual logging receives no image or inferred beverage details.
                        self.capturedImage = nil
                        photoItem = nil
                        onLogManually()
                    }
                    .buttonStyle(.borderedProminent)

                    Button("Discard photo", role: .destructive) {
                        self.capturedImage = nil
                        photoItem = nil
                    }
                    .buttonStyle(.bordered)
                } else {
                    captureOptions
                }

                Text("Photos remain on this device in this mock flow. They are not uploaded, saved by Hydra AI, or used to create a beverage log.")
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

    private var header: some View {
        VStack(alignment: .leading, spacing: 8) {
            Image(systemName: "camera.viewfinder")
                .font(.largeTitle)
                .foregroundStyle(.cyan)
                .accessibilityHidden(true)
            Text("Add a beverage photo")
                .font(.title2.bold())
            Text("Take or choose a photo. Recognition will be added after the approved AI service is ready.")
                .foregroundStyle(.secondary)
        }
    }

    private var captureOptions: some View {
        VStack(alignment: .leading, spacing: 14) {
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
