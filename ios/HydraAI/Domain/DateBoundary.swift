import Foundation

/// Avoid newer weak-linked Date relational operators on device OS releases.
/// Finite timestamp comparisons keep inclusive validation bounds unchanged.
enum DateBoundary {
    static func onOrAfter(_ value: Date, _ boundary: Date) -> Bool {
        let instant = value.timeIntervalSince1970
        let limit = boundary.timeIntervalSince1970
        return instant.isFinite && limit.isFinite && instant >= limit
    }
    static func onOrBefore(_ value: Date, _ boundary: Date) -> Bool {
        let instant = value.timeIntervalSince1970
        let limit = boundary.timeIntervalSince1970
        return instant.isFinite && limit.isFinite && instant <= limit
    }
}
