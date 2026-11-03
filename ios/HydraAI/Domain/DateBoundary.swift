import Foundation

/// Avoid newer weak-linked Date relational operators on device OS releases.
/// Finite timestamp comparisons keep inclusive validation bounds unchanged.
enum DateBoundary {
    static func onOrAfter(_ value: Date, _ boundary: Date) -> Bool {
        DateOrdering.notBefore(value, boundary)
    }
    static func onOrBefore(_ value: Date, _ boundary: Date) -> Bool {
        DateOrdering.notAfter(value, boundary)
    }
}
