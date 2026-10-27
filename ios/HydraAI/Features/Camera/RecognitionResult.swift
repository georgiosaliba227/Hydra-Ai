import Foundation
import UIKit

struct RecognitionRequest: Encodable {
    let imageBase64: String
    let photoConsent: Bool
    let mockScenario: String
    var mode: String? = nil
    var metaPhotoConsent: Bool? = nil
    enum CodingKeys: String, CodingKey {
        case imageBase64 = "image_base64", photoConsent = "photo_consent", mockScenario = "mock_scenario"
        case mode, metaPhotoConsent = "meta_photo_consent"
    }
}

struct RecognitionCandidate: Codable, Identifiable, Sendable {
    // One local identity per decoded/created alternative, retained across view
    // updates and value copies. Names (and even whole candidates) may repeat.
    // Deliberately omitted from CodingKeys: no API contract or persistence change.
    let id = UUID()
    let identity: String
    let productId: String?
    let containerMl: Int?
    let confidence: String
    let uncertaintyReasons: [String]
    var nutrition: SourcedNutrition? = nil
    var category: String? = nil
    var brand: String? = nil
    var product: String? = nil
    enum CodingKeys: String, CodingKey {
        case identity, confidence, nutrition, category, brand, product
        case productId = "product_id", containerMl = "container_ml", uncertaintyReasons = "uncertainty_reasons"
    }
}

enum RecognitionPresentation: Sendable, Equatable {
    case unavailable, mock, metaLive

    init(mode: String?) {
        switch mode {
        case "mock": self = .mock
        case "meta_live": self = .metaLive
        default: self = .unavailable
        }
    }

    var header: String {
        switch self {
        case .unavailable: "Take or choose a beverage photo. Verify the backend recognition mode before analysis."
        case .mock: "Take or choose a photo, try mock analysis, then confirm what you drank."
        case .metaLive: "Take or choose a photo for live Meta analysis, then confirm what you drank."
        }
    }

    var photoDescription: String {
        switch self {
        case .unavailable: "Analysis is unavailable until the backend recognition mode is verified."
        case .mock: "Mock analysis: selected demo responses do not interpret this photo."
        case .metaLive: "Live Meta analysis sends this photo to Meta. Recognition is uncertain; verify every suggestion."
        }
    }

    var analyzeTitle: String {
        switch self {
        case .unavailable: "Analysis unavailable"
        case .mock: "Analyze with mock Meta response"
        case .metaLive: "Analyze with live Meta"
        }
    }

    var resultTitle: String {
        switch self {
        case .unavailable: "Recognition source unavailable"
        case .mock: "Mock result — confirmation required"
        case .metaLive: "Live Meta result — confirmation required"
        }
    }

    var suggestionTitle: String {
        switch self {
        case .unavailable: "Recognition source unavailable — verify every field"
        case .mock: "Mock suggestion — verify every field"
        case .metaLive: "Live Meta suggestion — verify every field"
        }
    }
}

struct RecognitionResult: Decodable, Sendable {
    let version: String
    let mode: String
    let model: String
    let candidates: [RecognitionCandidate]
    let requiresConfirmation: Bool
    var recognitionId: UUID? = nil
    enum CodingKeys: String, CodingKey {
        case version, mode, model, candidates
        case requiresConfirmation = "requires_confirmation", recognitionId = "recognition_id"
    }
    func validate() throws {
        guard version == "recognition-v1", ["mock", "meta_live"].contains(mode), model == "muse-spark-1.3", requiresConfirmation,
              candidates.count <= 3 else { throw ServiceError.invalidResponse }
        guard (mode == "meta_live") == (recognitionId != nil) else { throw ServiceError.invalidResponse }
        for candidate in candidates {
            guard !candidate.identity.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  candidate.identity.count <= 80, ["low", "medium", "high"].contains(candidate.confidence),
                  (1...8).contains(candidate.uncertaintyReasons.count),
                  candidate.uncertaintyReasons.allSatisfy({ !$0.isEmpty && $0.count <= 300 }),
                  candidate.containerMl.map({ (1...5000).contains($0) }) ?? true else { throw ServiceError.invalidResponse }
        }
    }
}

enum PhotoPreparation {
    /// Redraw orientation-correct pixels; EXIF/GPS and original filename never upload.
    @MainActor static func jpeg(_ image: UIImage) throws -> Data {
        guard image.size.width > 0, image.size.height > 0,
              image.size.width * image.size.height <= 60_000_000 else { throw ServiceError.invalidResponse }
        let scale = min(1, 1600 / max(image.size.width, image.size.height))
        let size = CGSize(width: max(1, floor(image.size.width * scale)), height: max(1, floor(image.size.height * scale)))
        let format = UIGraphicsImageRendererFormat(); format.scale = 1; format.opaque = true
        let redrawn = UIGraphicsImageRenderer(size: size, format: format).image { context in
            UIColor.white.setFill(); context.fill(CGRect(origin: .zero, size: size))
            image.draw(in: CGRect(origin: .zero, size: size))
        }
        for quality in [0.8, 0.6, 0.4, 0.2] {
            if let data = redrawn.jpegData(compressionQuality: quality), data.count <= 1_048_576 { return data }
        }
        throw ServiceError.invalidResponse
    }
}

struct SourcedNutrition: Codable, Sendable {
    let basisMl: Double
    let sodiumMg: Double?
    let carbohydrateG: Double?
    let provenance: [String]
    enum CodingKeys: String, CodingKey {
        case basisMl = "basis_ml", sodiumMg = "sodium_mg", carbohydrateG = "carbohydrate_g", provenance
    }
}

struct RecognitionCapabilities: Decodable {
    let version: String
    let mode: String
    let model: String
    func validate() throws {
        guard version == "recognition-v1", ["mock", "meta_live"].contains(mode), model == "muse-spark-1.3" else { throw ServiceError.invalidResponse }
    }
}
