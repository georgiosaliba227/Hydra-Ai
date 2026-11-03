import Foundation

/// Preserve Date's reference-time precision while avoiding non-strict Date operator thunks.
/// The native operators failed on the verified iPhone runtime; numeric ordering passed there.
enum DateOrdering {
    static func notAfter(_ lhs: Date, _ rhs: Date) -> Bool {
        lhs.timeIntervalSinceReferenceDate <= rhs.timeIntervalSinceReferenceDate
    }
    static func notBefore(_ lhs: Date, _ rhs: Date) -> Bool {
        lhs.timeIntervalSinceReferenceDate >= rhs.timeIntervalSinceReferenceDate
    }
}
