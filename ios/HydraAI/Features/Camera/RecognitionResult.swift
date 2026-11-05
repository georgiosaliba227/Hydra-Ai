import Foundation
import CoreTransferable
import UniformTypeIdentifiers
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
    var visibleLabelText: String? = nil
    var estimatedLiquidMlMin: Int? = nil
    var estimatedLiquidMlMax: Int? = nil
    var volumeBasis: String? = nil
    var personalCorrection: PersonalRecognitionCorrection? = nil
    var labelCapacityMl: Int? = nil
    enum CodingKeys: String, CodingKey {
        case identity, confidence, nutrition, category, brand, product
        case productId = "product_id", containerMl = "container_ml", uncertaintyReasons = "uncertainty_reasons"
        case visibleLabelText = "visible_label_text", estimatedLiquidMlMin = "estimated_liquid_ml_min"
        case estimatedLiquidMlMax = "estimated_liquid_ml_max", volumeBasis = "volume_basis", personalCorrection = "personal_correction"
        case labelCapacityMl = "label_capacity_ml"
    }

    var suggestedIdentity: String { personalCorrection?.identity ?? identity }
    var suggestedCapacity: Int? {
        if let personalCorrection, personalCorrection.matchBasis == "exact_image" { return personalCorrection.containerMl }
        return labelCapacityMl ?? containerMl
    }
    /// User's whole-liquid default, not an inference that consumption occurred.
    var wholeLiquidMl: Int? {
        let capacity = suggestedCapacity ?? 5000
        guard (1...5000).contains(capacity) else { return nil }
        if let correction = personalCorrection, correction.matchBasis == "exact_image", let ml = correction.liquidMl {
            return (1...capacity).contains(ml) ? ml : nil
        }
        guard let lower = estimatedLiquidMlMin, let upper = estimatedLiquidMlMax,
              ["visual_estimate", "visible_measurement"].contains(volumeBasis ?? ""),
              (1...capacity).contains(lower), lower <= upper, upper <= capacity else { return nil }
        return lower + (upper - lower + 1) / 2
    }
    var personalLiquidText: String? {
        personalCorrection?.liquidMl.map { "Your previous liquid correction for this photo: \($0) mL" }
    }
    var feedbackReference: RecognitionCandidate {
        if !identity.isEmpty { return self }
        return RecognitionCandidate(identity: "Unknown beverage", productId: nil, containerMl: nil,
            confidence: "low", uncertaintyReasons: uncertaintyReasons)
    }
    var liquidEstimateText: String {
        guard let lower = estimatedLiquidMlMin, let upper = estimatedLiquidMlMax else { return "Liquid currently present: unknown" }
        return "Liquid currently present: about \(lower)–\(upper) mL"
    }

    func validate() throws {
        guard !identity.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, identity.count <= 80,
              ["low", "medium", "high"].contains(confidence), (1...8).contains(uncertaintyReasons.count),
              uncertaintyReasons.allSatisfy({ !$0.isEmpty && $0.count <= 300 }),
              containerMl.map({ (1...5000).contains($0) }) ?? true,
              labelCapacityMl.map({ (1...5000).contains($0) }) ?? true,
              [brand, product, category].allSatisfy({ $0.map({ $0.count <= 80 }) ?? true }),
              visibleLabelText.map({ $0.count <= 600 }) ?? true else { throw ServiceError.invalidResponse }
        if estimatedLiquidMlMin != nil || estimatedLiquidMlMax != nil {
            guard let lower = estimatedLiquidMlMin, let upper = estimatedLiquidMlMax,
                  (1...5000).contains(lower), lower <= upper, upper <= (containerMl ?? 5000),
                  ["visual_estimate", "visible_measurement"].contains(volumeBasis ?? "") else { throw ServiceError.invalidResponse }
        } else if volumeBasis != nil && volumeBasis != "unknown" { throw ServiceError.invalidResponse }
        try personalCorrection?.validate()
    }
}

struct PersonalRecognitionCorrection: Codable, Sendable {
    let identity: String
    let containerMl: Int?
    var liquidMl: Int? = nil
    var beverageType: String? = nil
    let matchBasis: String
    let confirmedAt: String
    enum CodingKeys: String, CodingKey {
        case identity, containerMl = "container_ml", liquidMl = "liquid_ml", matchBasis = "match_basis", confirmedAt = "confirmed_at"
        case beverageType = "beverage_type"
    }
    func validate() throws {
        guard !identity.isEmpty, identity.count <= 80,
              ["exact_image", "product_label"].contains(matchBasis),
              containerMl.map({ (1...5000).contains($0) }) ?? true,
              beverageType.map({ !$0.isEmpty && $0.count <= 80 }) ?? true,
              liquidMl.map({ (1...(containerMl ?? 5000)).contains($0) }) ?? true,
              matchBasis != "product_label" || (containerMl == nil && liquidMl == nil),
              !confirmedAt.isEmpty, confirmedAt.count <= 60 else { throw ServiceError.invalidResponse }
    }
}

enum RecognitionPresentation: Sendable, Equatable {
    case unavailable, mock, metaLive, localMeta, onDevice

    init(mode: String?) {
        switch mode {
        case "mock": self = .mock
        case "meta_live": self = .metaLive
        case "local_meta": self = .localMeta
        case "on_device": self = .onDevice
        default: self = .unavailable
        }
    }

    var header: String {
        switch self {
        case .unavailable: "Take or choose a beverage photo. Verify the backend recognition mode before analysis."
        case .mock: "Take or choose a photo, try mock analysis, then confirm what you drank."
        case .metaLive: "Take or choose a photo for live Meta analysis, then confirm what you drank."
        case .localMeta: "Take or choose a photo for your trained Meta model on your Mac, then confirm what you drank."
        case .onDevice: "Take or choose a beverage photo. Analyze it on this iPhone, then confirm what you drank."
        }
    }

    var photoDescription: String {
        switch self {
        case .unavailable: "Analysis is unavailable until the backend recognition mode is verified."
        case .mock: "Mock analysis: selected demo responses do not interpret this photo."
        case .metaLive: "Live Meta analysis sends this photo to Meta. Recognition is uncertain; verify every suggestion."
        case .localMeta: "Your trained Meta model processes this photo on your configured Mac. Check the drink name and exact printed size."
        case .onDevice: "Your iPhone analyzes this photo using a compact Meta model and local label reading. Verify the experimental category and printed size."
        }
    }

    var analyzeTitle: String {
        switch self {
        case .unavailable: "Analysis unavailable"
        case .mock: "Analyze with mock Meta response"
        case .metaLive: "Analyze with live Meta"
        case .localMeta: "Analyze with trained Meta"
        case .onDevice: "Analyze"
        }
    }

    var resultTitle: String {
        switch self {
        case .unavailable: "Recognition source unavailable"
        case .mock: "Mock result — confirmation required"
        case .metaLive: "Live Meta result — confirmation required"
        case .localMeta: "Local trained Meta result — confirmation required"
        case .onDevice: "On-device result — confirmation required"
        }
    }

    var suggestionTitle: String {
        switch self {
        case .unavailable: "Recognition source unavailable — verify every field"
        case .mock: "Mock suggestion — verify every field"
        case .metaLive: "Live Meta suggestion — verify every field"
        case .localMeta: "Local trained Meta suggestion — verify every field"
        case .onDevice: "On-device suggestion — verify every field"
        }
    }

    var modelName: String {
        switch self {
        case .unavailable: "Unverified model"
        case .mock: "Demo"
        case .metaLive: "Muse"
        case .localMeta: "Trained Meta"
        case .onDevice: "Meta on device"
        }
    }

    static func validModel(_ model: String, mode: String) -> Bool {
        switch mode {
        case "mock", "meta_live": model == "muse-spark-1.3"
        case "local_meta": model == "muse-glimmer-30b-beverage-lora-v1"
        case "on_device": model == "dinov2-small-beverage-v1"
        default: false
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
    var imageSha256: String? = nil
    enum CodingKeys: String, CodingKey {
        case version, mode, model, candidates
        case requiresConfirmation = "requires_confirmation", recognitionId = "recognition_id"
        case imageSha256 = "image_sha256"
    }
    func validate() throws {
        guard version == "recognition-v1", RecognitionPresentation.validModel(model, mode: mode), requiresConfirmation,
              candidates.count <= 3 else { throw ServiceError.invalidResponse }
        guard (mode != "mock") == (recognitionId != nil) else { throw ServiceError.invalidResponse }
        if let imageSha256 { guard imageSha256.count == 64, imageSha256.allSatisfy({ "0123456789abcdef".contains($0) }) else { throw ServiceError.invalidResponse } }
        for candidate in candidates { try candidate.validate() }
    }
}

/// The selected image is prepared once; export and analysis consume identical bytes.
struct PreparedRecognitionPhoto {
    let image: UIImage
    let export: PreparedPhotoExport

    @MainActor init(image: UIImage) throws {
        self.image = image
        self.export = PreparedPhotoExport(jpeg: try PhotoPreparation.jpeg(image))
    }
}

struct PreparedPhotoExport: Transferable {
    let jpeg: Data

    static var transferRepresentation: some TransferRepresentation {
        DataRepresentation(exportedContentType: .jpeg) { photo in photo.jpeg }
            .suggestedFileName("hydra-prepared-beverage.jpg")
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
    var correctionMemoryAvailable: Bool? = nil
    var trainingExamplesAvailable: Bool? = nil
    enum CodingKeys: String, CodingKey {
        case version, mode, model
        case correctionMemoryAvailable = "correction_memory_available", trainingExamplesAvailable = "training_examples_available"
    }
    func validate() throws {
        guard version == "recognition-v1", RecognitionPresentation.validModel(model, mode: mode) else { throw ServiceError.invalidResponse }
    }
}
