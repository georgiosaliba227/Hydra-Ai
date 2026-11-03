import Foundation

/// Included in the durable confirmed mutation, never in an inference request.
struct RecognitionFeedback: Codable, Sendable {
    static let consentVersion = "hydra-training-photo-correction-v1"
    let imageSha256: String
    let sourceMode: String
    let originalCandidate: RecognitionCandidate
    let rememberForMe: Bool
    let shareForTraining: Bool
    var correctedLiquidMl: Int? = nil
    var trainingConsentVersion: String? = nil
    var trainingPhotoBase64: String? = nil
    enum CodingKeys: String, CodingKey {
        case imageSha256 = "image_sha256", sourceMode = "source_mode", originalCandidate = "original_candidate"
        case rememberForMe = "remember_for_me", shareForTraining = "share_for_training"
        case correctedLiquidMl = "corrected_liquid_ml", trainingConsentVersion = "training_consent_version", trainingPhotoBase64 = "training_photo_base64"
    }
    func validate() throws {
        guard imageSha256.count == 64, imageSha256.allSatisfy({ "0123456789abcdef".contains($0) }),
              ["mock", "meta_live", "local_meta"].contains(sourceMode),
              correctedLiquidMl.map({ (1...5000).contains($0) }) ?? true else { throw ServiceError.invalidResponse }
        try originalCandidate.validate()
        if shareForTraining {
            guard trainingConsentVersion == Self.consentVersion,
                  let encoded = trainingPhotoBase64, let data = Data(base64Encoded: encoded),
                  data.count <= 1_048_576, data.starts(with: [0xff,0xd8]), data.suffix(2) == Data([0xff,0xd9]) else { throw ServiceError.consent }
        } else if trainingConsentVersion != nil || trainingPhotoBase64 != nil { throw ServiceError.consent }
    }
}

/// Transient prepared photo; enters persistence only after training opt-in.
struct RecognitionFeedbackContext {
    let imageSha256: String
    let jpeg: Data
    let memoryAvailable: Bool
    let trainingAvailable: Bool
}
