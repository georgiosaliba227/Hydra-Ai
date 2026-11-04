import Foundation

/// Preserve Date's reference-time precision while avoiding non-strict Date operator thunks.
/// The native operators failed on the verified iPhone runtime; numeric ordering passed there.
enum DateOrdering {
    static func notAfter(_ lhs: Date, _ rhs: Date) -> Bool {
        let instant = lhs.timeIntervalSinceReferenceDate, limit = rhs.timeIntervalSinceReferenceDate
        return instant.isFinite && limit.isFinite && instant <= limit
    }
    static func notBefore(_ lhs: Date, _ rhs: Date) -> Bool {
        let instant = lhs.timeIntervalSinceReferenceDate, limit = rhs.timeIntervalSinceReferenceDate
        return instant.isFinite && limit.isFinite && instant >= limit
    }
}
