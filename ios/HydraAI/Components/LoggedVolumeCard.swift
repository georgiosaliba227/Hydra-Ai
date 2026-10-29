import SwiftUI

struct LoggedVolumeCard: View {
    let title: String
    let volumeMl: Int
    let detail: String
    @ScaledMetric(relativeTo: .largeTitle) private var volumeSize: CGFloat = 38

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Cyan on the light card fails contrast for text, so only the icon keeps it.
            Label {
                Text(title)
            } icon: {
                Image(systemName: "drop.circle.fill").foregroundStyle(.cyan)
            }
            .font(.headline)
            HStack(alignment: .firstTextBaseline, spacing: 5) {
                Text(volumeMl.formatted())
                    .font(.system(size: volumeSize, weight: .bold, design: .rounded))
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
        .accessibilityValue(String(volumeMl))
    }
}
