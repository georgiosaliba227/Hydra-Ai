import SwiftUI

struct LoggedVolumeCard: View {
    let title: String
    let volumeMl: Int
    let detail: String

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(title, systemImage: "drop.circle.fill")
                .font(.headline)
                .foregroundStyle(.cyan)
            HStack(alignment: .firstTextBaseline, spacing: 5) {
                Text(volumeMl.formatted())
                    .font(.system(size: 38, weight: .bold, design: .rounded))
                    .contentTransition(.numericText())
                Text("mL")
                    .font(.title3.weight(.medium))
                    .foregroundStyle(.secondary)
            }
            Text(detail)
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(20)
        .background(.cyan.opacity(0.09), in: RoundedRectangle(cornerRadius: 20))
        .accessibilityElement(children: .combine)
    }
}
