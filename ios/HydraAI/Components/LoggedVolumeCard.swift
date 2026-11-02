import SwiftUI

struct LoggedVolumeCard: View {
    let title: String
    let volumeMl: Int
    let detail: String
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @ScaledMetric(relativeTo: .largeTitle) private var volumeSize: CGFloat = 58

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Label(title, systemImage: "drop.fill").font(.headline)
                Spacer()
                Image(systemName: "sparkles").foregroundStyle(HydraStyle.lime)
            }
            let layout = dynamicTypeSize.isAccessibilitySize
                ? AnyLayout(VStackLayout(alignment: .leading, spacing: 4))
                : AnyLayout(HStackLayout(alignment: .firstTextBaseline, spacing: 7))
            layout {
                Text(volumeMl.formatted())
                    .font(.system(size: volumeSize, weight: .bold, design: .rounded))
                    .lineLimit(1).minimumScaleFactor(0.5)
                    .contentTransition(.numericText())
                    .animation(reduceMotion ? nil : .spring(response: 0.5), value: volumeMl)
                Text("mL").font(.title2.weight(.medium)).foregroundStyle(HydraStyle.aqua)
            }
            Text(detail).font(.footnote).foregroundStyle(.white.opacity(0.8))
            HStack(spacing: 5) {
                ForEach(0..<18) { index in
                    Capsule().fill(index.isMultiple(of: 3) ? HydraStyle.lime : HydraStyle.aqua.opacity(0.45))
                        .frame(height: CGFloat([12, 22, 16, 30, 20, 14][index % 6]))
                }
            }
            .frame(height: 30).accessibilityHidden(true)
        }
        .foregroundStyle(.white)
        .padding(24)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(HydraStyle.ink.gradient, in: RoundedRectangle(cornerRadius: 30))
        .accessibilityElement(children: .combine)
        .accessibilityValue(String(volumeMl))
    }
}
