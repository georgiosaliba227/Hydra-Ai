import Foundation
import UIKit

struct RecognitionRequest: Encodable {
    let imageBase64: String
    let photoConsent: Bool
    let mockScenario: String
    enum CodingKeys: String, CodingKey {
        case imageBase64 = "image_base64", photoConsent = "photo_consent", mockScenario = "mock_scenario"
    }
}

struct RecognitionCandidate: Codable, Identifiable, Sendable {
    var id: String { identity }
    let identity: String
    let productId: String?
    let containerMl: Int?
    let confidence: String
    let uncertaintyReasons: [String]
    var nutrition: SourcedNutrition? = nil
    enum CodingKeys: String, CodingKey {
        case identity, confidence, nutrition
        case productId = "product_id", containerMl = "container_ml", uncertaintyReasons = "uncertainty_reasons"
    }
}

struct RecognitionResult: Decodable, Sendable {
    let version: String
    let mode: String
    let model: String
    let candidates: [RecognitionCandidate]
    let requiresConfirmation: Bool
    enum CodingKeys: String, CodingKey {
        case version, mode, model, candidates
        case requiresConfirmation = "requires_confirmation"
    }
    func validate() throws {
        guard version == "recognition-v1", mode == "mock", model == "muse-spark-1.3", requiresConfirmation,
              candidates.count <= 3 else { throw ServiceError.invalidResponse }
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
