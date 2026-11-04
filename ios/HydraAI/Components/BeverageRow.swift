import SwiftUI

struct BeverageRow: View {
    @EnvironmentObject private var units: DisplayUnits
    let log: BeverageLog

    var body: some View {
        HStack(spacing: 12) {
            IconBadge(systemName: BeverageStyle.symbol(for: log.category))

            VStack(alignment: .leading, spacing: 2) {
                Text(log.category.capitalized)
                    .font(.body.weight(.medium))
                HStack(spacing: 4) {
                    Text(log.consumedAt, format: .dateTime.hour().minute())
                    if log.source != "manual" {
                        Text("· from photo")
                    }
                    if let type = log.beverageType { Text("· \(type)") }
                }
                .font(.caption)
                .foregroundStyle(.secondary)
                if let assumption = log.assumptionDescription { Text(assumption).font(.caption).foregroundStyle(.secondary) }
            }

            Spacer()

            Text("\(units.volume(log.consumedMl))")
                .font(.body.monospacedDigit().weight(.semibold))
        }
        .frame(minHeight: 44)
        .accessibilityElement(children: .ignore)
        .accessibilityIdentifier("beverageRow")
        .accessibilityLabel("\(log.category.capitalized), \(units.volumeAccessibility(log.consumedMl)), \(log.consumedAt.formatted(date: .omitted, time: .shortened))\(log.assumptionDescription.map { ", " + $0 } ?? "")")
    }
}
