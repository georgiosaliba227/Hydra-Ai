#if DEBUG
import Photos
import UIKit

/// Opt-in native picker fixture. Never reads existing assets or ships in Release.
@MainActor
enum PhotoLibraryTestFixture {
    static func add() async throws {
        guard ProcessInfo.processInfo.environment["HYDRA_TEST_LIBRARY_FIXTURE"] == "1" else {
            throw ServiceError.configuration
        }
        let status = await PHPhotoLibrary.requestAuthorization(for: .addOnly)
        guard status == .authorized else { throw ServiceError.credentials }
        let format = UIGraphicsImageRendererFormat(); format.scale = 1
        let image = UIGraphicsImageRenderer(size: CGSize(width: 240, height: 360), format: format).image { context in
            UIColor.white.setFill(); context.fill(CGRect(x: 0, y: 0, width: 240, height: 360))
            UIColor.systemBlue.setFill()
            UIBezierPath(roundedRect: CGRect(x: 65, y: 70, width: 110, height: 240), cornerRadius: 20).fill()
            UIColor.darkGray.setFill(); context.fill(CGRect(x: 100, y: 40, width: 40, height: 45))
            ("HYDRA TEST\nBEVERAGE\n2050" as NSString).draw(in: CGRect(x: 72, y: 140, width: 100, height: 130),
                withAttributes: [.font: UIFont.boldSystemFont(ofSize: 16), .foregroundColor: UIColor.white])
        }
        guard let data = image.pngData() else { throw ServiceError.invalidResponse }
        try await PHPhotoLibrary.shared().performChanges {
            let request = PHAssetCreationRequest.forAsset()
            let options = PHAssetResourceCreationOptions()
            options.originalFilename = "HYDRA_SYNTHETIC_BEVERAGE_2050.png"
            request.addResource(with: .photo, data: data, options: options)
            // Unique visible date lets UI tests identify this asset without
            // selecting an arbitrary personal thumbnail. No asset fetches.
            request.creationDate = Date(timeIntervalSince1970: 2_524_651_200)
        }
    }
}
#endif
