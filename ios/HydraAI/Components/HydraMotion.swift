import SwiftUI

/// Shared presentation only. Decorative water levels never represent hydration.
enum HydraStyle {
    static let ink = Color(red: 0.035, green: 0.16, blue: 0.20)
    static let aqua = Color(red: 0.35, green: 0.94, blue: 0.84)
    static let lime = Color(red: 0.83, green: 0.97, blue: 0.45)
    static let teal = Color(uiColor: UIColor { traits in
        traits.userInterfaceStyle == .dark
            ? UIColor(red: 0.35, green: 0.94, blue: 0.84, alpha: 1)
            : UIColor(red: 0.02, green: 0.42, blue: 0.39, alpha: 1)
    })
    static let canvas = Color(uiColor: .systemGroupedBackground)
}

struct HydraPressStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline)
            .foregroundStyle(HydraStyle.ink)
            .padding(.vertical, 18).padding(.horizontal, 20)
            .frame(maxWidth: .infinity)
            .background(HydraStyle.aqua, in: RoundedRectangle(cornerRadius: 22))
            .scaleEffect(configuration.isPressed && !reduceMotion ? 0.97 : 1)
            .opacity(!isEnabled ? 0.45 : configuration.isPressed ? 0.8 : 1)
            .animation(reduceMotion ? nil : .spring(response: 0.25), value: configuration.isPressed)
    }
}

struct FloatingBottle: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30, paused: reduceMotion)) { context in
            let phase = reduceMotion ? 0 : sin(context.date.timeIntervalSinceReferenceDate * 1.7)
            ZStack {
                Circle().fill(HydraStyle.aqua.opacity(0.12)).frame(width: 190, height: 190)
                Circle().strokeBorder(HydraStyle.aqua.opacity(0.2), style: StrokeStyle(lineWidth: 1, dash: [4, 8]))
                    .frame(width: 220, height: 220)
                VStack(spacing: 0) {
                    RoundedRectangle(cornerRadius: 7).fill(HydraStyle.lime).frame(width: 38, height: 19)
                    RoundedRectangle(cornerRadius: 25)
                        .fill(.white.opacity(0.12))
                        .overlay(alignment: .bottom) {
                            RoundedRectangle(cornerRadius: 24)
                                .fill(LinearGradient(colors: [HydraStyle.aqua, .cyan], startPoint: .topLeading, endPoint: .bottomTrailing))
                                .frame(height: 102)
                        }
                        .overlay { RoundedRectangle(cornerRadius: 25).strokeBorder(.white.opacity(0.6), lineWidth: 2) }
                        .overlay { Image(systemName: "drop.fill").font(.system(size: 35)).foregroundStyle(HydraStyle.ink) }
                        .frame(width: 90, height: 146)
                }
                .rotationEffect(.degrees(-9 + phase * 3)).offset(y: phase * 7)
                Image(systemName: "sparkle").font(.title2).foregroundStyle(HydraStyle.lime).offset(x: 82, y: -65 + phase * 4)
                Circle().fill(HydraStyle.aqua).frame(width: 9, height: 9).offset(x: -82, y: 45 - phase * 5)
            }
        }
        .frame(width: 230, height: 240)
        .accessibilityHidden(true)
    }
}
