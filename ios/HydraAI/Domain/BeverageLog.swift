import Foundation

/// The v1 beverage log contract. Volume is the confirmed amount consumed, in mL.
struct BeverageLog: Codable, Identifiable, Equatable, Sendable {
    let id: UUID
    let consumedMl: Int
    let category: String
    let consumedAt: Date
    let timezone: String
    let source: String
    let revision: Int

    enum CodingKeys: String, CodingKey {
        case id, category, timezone, source, revision
        case consumedMl = "consumed_ml"
        case consumedAt = "consumed_at"
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

    enum CodingKeys: String, CodingKey {
        case category, timezone, source
        case productId = "product_id", containerMl = "container_ml", recognitionId = "recognition_id"
        case consumedMl = "consumed_ml"
        case consumedAt = "consumed_at"
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
    func validate(now: Date = .now) throws {
        guard !category.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              category.count <= 80 else { throw BeverageValidationError.invalidCategory }
        guard (1...5_000).contains(consumedMl) else { throw BeverageValidationError.invalidVolume }
        guard ["manual", "confirmed_recognition"].contains(source) else { throw BeverageValidationError.invalidCategory }
        if source == "confirmed_recognition" {
            guard let containerMl, (1...5000).contains(containerMl), consumedMl <= containerMl else { throw BeverageValidationError.invalidVolume }
        } else if productId != nil || containerMl != nil || recognitionId != nil { throw BeverageValidationError.invalidCategory }
        guard TimeZone(identifier: timezone) != nil else { throw BeverageValidationError.invalidTimezone }
        guard consumedAt >= Date(timeIntervalSince1970: 946_684_800) else { throw BeverageValidationError.historicalDate }
        guard consumedAt <= now.addingTimeInterval(60) else { throw BeverageValidationError.futureDate }
    }
}
