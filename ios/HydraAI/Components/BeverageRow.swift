import SwiftUI

struct BeverageRow: View {
    let log: BeverageLog

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "drop.fill")
                .foregroundStyle(.cyan)
                .frame(width: 32, height: 32)
                .background(.cyan.opacity(0.12), in: RoundedRectangle(cornerRadius: 9))
                .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: 3) {
                Text(log.category.capitalized)
                    .font(.body.weight(.medium))
                Text(log.consumedAt, format: .dateTime.hour().minute())
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            Text("\(log.consumedMl.formatted()) mL")
                .font(.body.monospacedDigit().weight(.semibold))
        }
        .accessibilityElement(children: .ignore)
        .accessibilityIdentifier("beverageRow")
        .accessibilityLabel("\(log.category.capitalized), \(log.consumedMl) milliliters, \(log.consumedAt.formatted(date: .omitted, time: .shortened))")
    }
}
