import Foundation

/// Original on-phone suggestion, kept separately from user-confirmed consumption.
/// No image, image hash, training payload or unrelated label transcript is stored.
struct OnDeviceRecognitionProvenance: Codable, Equatable, Sendable {
    let modelID: String
    let originalCandidate: RecognitionCandidate
    let processedAt: Date

    enum CodingKeys: String, CodingKey {
        case modelID = "model_id", originalCandidate = "original_candidate", processedAt = "processed_at"
    }

    func validate(now: Date = .now) throws {
        try validatePersisted()
        guard DateBoundary.onOrBefore(processedAt, now.addingTimeInterval(60)) else { throw ServiceError.invalidResponse }
    }

    /// Saved provenance must remain readable when the device clock moves backward.
    func validatePersisted() throws {
        guard modelID == "dinov2-small-beverage-v1",
              processedAt.timeIntervalSince1970.isFinite,
              DateBoundary.onOrAfter(processedAt, Date(timeIntervalSince1970: 946_684_800)),
              originalCandidate.personalCorrection == nil else { throw ServiceError.invalidResponse }
        try originalCandidate.validate()
    }

    static func == (lhs: Self, rhs: Self) -> Bool {
        // Candidate's transient SwiftUI id is deliberately excluded by Codable.
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
        return lhs.modelID == rhs.modelID && lhs.processedAt == rhs.processedAt
            && (try? encoder.encode(lhs.originalCandidate)) == (try? encoder.encode(rhs.originalCandidate))
    }
}

/// The v1 log contract. User-assumed consumption is explicitly tagged; units are mL.
struct BeverageLog: Codable, Identifiable, Equatable, Sendable {
    let id: UUID
    let consumedMl: Int
    let category: String
    let consumedAt: Date
    let timezone: String
    let source: String
    let revision: Int
    var consumptionAssumption: String? = nil
    var beverageType: String? = nil
    var onDeviceRecognition: OnDeviceRecognitionProvenance? = nil
    var containerMl: Int? = nil
    var assumptionDescription: String? {
        switch consumptionAssumption {
        case "entire_liquid": "Assumed all liquid consumed"
        case "full_container": "Assumed full container consumed"
        default: nil
        }
    }

    enum CodingKeys: String, CodingKey {
        case id, category, timezone, source, revision
        case consumedMl = "consumed_ml"
        case consumedAt = "consumed_at"
        case consumptionAssumption = "consumption_assumption"
        case beverageType = "beverage_type"
        case onDeviceRecognition = "on_device_recognition"
        case containerMl = "container_ml"
    }
}

/// A confirmed manual submission. Identity is assigned by the service, as it would be by the API.
struct CreateBeverageRequest: Codable, Sendable {
    let category: String
    let consumedMl: Int
    let consumedAt: Date
    let timezone: String
    let source: String
    var recognitionId: UUID? = nil
    var productId: String? = nil
    var containerMl: Int? = nil
    var recognitionFeedback: RecognitionFeedback? = nil
    var consumptionAssumption: String? = nil
    var beverageType: String? = nil
    var onDeviceRecognition: OnDeviceRecognitionProvenance? = nil

    enum CodingKeys: String, CodingKey {
        case category, timezone, source
        case productId = "product_id", containerMl = "container_ml", recognitionId = "recognition_id"
        case recognitionFeedback = "recognition_feedback"
        case consumptionAssumption = "consumption_assumption"
        case beverageType = "beverage_type"
        case onDeviceRecognition = "on_device_recognition"
        case consumedMl = "consumed_ml"
        case consumedAt = "consumed_at"
    }
}

/// A correction of a confirmed log. Nil fields are omitted and keep their stored value.
struct UpdateBeverageRequest: Encodable, Equatable, Sendable {
    let revision: Int
    var category: String?
    var consumedMl: Int?
    var consumedAt: Date?

    enum CodingKeys: String, CodingKey {
        case revision, category
        case consumedMl = "consumed_ml"
        case consumedAt = "consumed_at"
    }

    /// Only fields that differ from `log`; a photo-confirmed log keeps its product category.
    init(correcting log: BeverageLog, category: String, consumedMl: Int, consumedAt: Date) {
        revision = log.revision
        let trimmed = category.trimmingCharacters(in: .whitespacesAndNewlines)
        self.category = log.source == "manual" && trimmed != log.category ? trimmed : nil
        self.consumedMl = consumedMl != log.consumedMl ? consumedMl : nil
        self.consumedAt = abs(consumedAt.timeIntervalSince(log.consumedAt)) >= 1 ? consumedAt : nil
    }

    var hasChanges: Bool { category != nil || consumedMl != nil || consumedAt != nil }

    func validate(now: Date = .now) throws {
        if let category { guard !category.isEmpty, category.count <= 80 else { throw BeverageValidationError.invalidCategory } }
        if let consumedMl { guard (1...5_000).contains(consumedMl) else { throw BeverageValidationError.invalidVolume } }
        if let consumedAt {
            guard DateBoundary.onOrAfter(consumedAt, Date(timeIntervalSince1970: 946_684_800)) else { throw BeverageValidationError.historicalDate }
            guard DateBoundary.onOrBefore(consumedAt, now.addingTimeInterval(60)) else { throw BeverageValidationError.futureDate }
        }
    }
}

enum BeverageValidationError: LocalizedError {
    case invalidCategory
    case invalidVolume
    case invalidTimezone
    case futureDate
    case historicalDate

    var errorDescription: String? {
        switch self {
        case .invalidCategory: "Choose a beverage category."
        case .invalidVolume: "Enter an amount between 1 and 5,000 mL."
        case .invalidTimezone: "The device timezone is unavailable."
        case .historicalDate: "The consumption time must be in 2000 or later."
        case .futureDate: "The consumption time cannot be in the future."
        }
    }
}

extension CreateBeverageRequest {
    func validate(now: Date = .now, allowOnDevice: Bool = false) throws {
        if let onDeviceRecognition {
            guard allowOnDevice, source == "confirmed_recognition", recognitionId != nil, recognitionFeedback == nil else { throw ServiceError.invalidResponse }
            try onDeviceRecognition.validate(now: now)
        }
        guard !category.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              category.count <= 80 else { throw BeverageValidationError.invalidCategory }
        guard (1...5_000).contains(consumedMl) else { throw BeverageValidationError.invalidVolume }
        guard ["manual", "confirmed_recognition"].contains(source) else { throw BeverageValidationError.invalidCategory }
        if source == "confirmed_recognition" {
            if let beverageType { guard !beverageType.isEmpty, beverageType.count <= 80 else { throw BeverageValidationError.invalidCategory } }
            if let containerMl { guard (1...5000).contains(containerMl), consumedMl <= containerMl else { throw BeverageValidationError.invalidVolume } }
            if let consumptionAssumption {
                guard ["entire_liquid", "full_container"].contains(consumptionAssumption),
                      consumptionAssumption != "full_container" || consumedMl == containerMl else { throw BeverageValidationError.invalidVolume }
            }
            if let recognitionFeedback {
                try recognitionFeedback.validate()
                guard (recognitionFeedback.sourceMode != "mock") == (recognitionId != nil),
                      recognitionFeedback.correctedLiquidMl.map({ $0 <= (containerMl ?? 5000) }) ?? true else { throw BeverageValidationError.invalidVolume }
            }
        } else if productId != nil || containerMl != nil || recognitionId != nil || recognitionFeedback != nil || consumptionAssumption != nil || beverageType != nil || onDeviceRecognition != nil { throw BeverageValidationError.invalidCategory }
        guard TimeZone(identifier: timezone) != nil else { throw BeverageValidationError.invalidTimezone }
        guard DateBoundary.onOrAfter(consumedAt, Date(timeIntervalSince1970: 946_684_800)) else { throw BeverageValidationError.historicalDate }
        guard DateBoundary.onOrBefore(consumedAt, now.addingTimeInterval(60)) else { throw BeverageValidationError.futureDate }
    }
}
