import SwiftUI

struct BeverageRow: View {
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
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }

            Spacer()

            Text("\(log.consumedMl.formatted()) mL")
                .font(.body.monospacedDigit().weight(.semibold))
        }
        .frame(minHeight: 44)
        .accessibilityElement(children: .ignore)
        .accessibilityIdentifier("beverageRow")
        .accessibilityLabel("\(log.category.capitalized), \(log.consumedMl) milliliters, \(log.consumedAt.formatted(date: .omitted, time: .shortened))")
    }
}
