import SwiftUI

/// A finite settling wave: no perpetual animation or display-link work while idle.
struct LiquidProgressGauge: View {
    let volumeMl: Int
    let progress: Double?
    let feedbackID: UUID?
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @ScaledMetric(relativeTo: .largeTitle) private var gaugeSize: CGFloat = 148
    @ScaledMetric(relativeTo: .largeTitle) private var numberSize: CGFloat = 36
    @State private var wavePhase: CGFloat = 0

    private var size: CGFloat { min(gaugeSize, 180) }
    private var level: Double { min(max(progress ?? 0, 0), 1) }
    private let ink = Color(red: 0.03, green: 0.21, blue: 0.27)

    var body: some View {
        ZStack {
            if progress != nil {
                glass
                    .keyframeAnimator(initialValue: 1.0, trigger: feedbackID) { content, scale in
                        content.scaleEffect(reduceMotion ? 1 : scale)
                    } keyframes: { _ in
                        CubicKeyframe(1.035, duration: 0.18)
                        SpringKeyframe(1, duration: 0.65, spring: .snappy)
                    }
                if !reduceMotion {
                    SaveRipple(trigger: feedbackID, size: size)
                }
            } else {
                RoundedRectangle(cornerRadius: 28, style: .continuous)
                    .fill(Color.hydraTint.opacity(0.10))
            }
            VStack(spacing: 0) {
                Text(volumeMl.formatted())
                    .font(.system(size: min(numberSize, 60), weight: .bold, design: .rounded))
                    .monospacedDigit()
                    .contentTransition(.numericText())
                    .lineLimit(1).minimumScaleFactor(0.55)
                Text("mL").font(.subheadline.weight(.semibold))
            }
            .foregroundStyle(progress != nil ? ink : Color.primary)
            .padding(16)
            .animation(reduceMotion ? nil : .smooth(duration: 0.8), value: volumeMl)
        }
        .frame(width: size, height: size)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Logged today, \(volumeMl.formatted()) milliliters")
        .accessibilityValue(String(volumeMl))
        .accessibilityIdentifier("dailyTotal")
        .onChange(of: feedbackID) { _, newID in
            guard !reduceMotion, newID != nil else { return }
            withAnimation(.easeOut(duration: 1.25)) { wavePhase += .pi * 2 }
        }
    }

    private var glass: some View {
        ZStack {
            Circle().fill(Color(red: 0.91, green: 0.97, blue: 0.98))
            ZStack {
                WaterSurface(level: level, phase: reduceMotion ? 0 : wavePhase + 1.8)
                    .fill(Color(red: 0.22, green: 0.77, blue: 0.80).opacity(0.35))
                WaterSurface(level: level, phase: reduceMotion ? 0 : wavePhase)
                    .fill(LinearGradient(colors: [Color(red: 0.52, green: 0.92, blue: 0.83),
                                                  Color(red: 0.13, green: 0.72, blue: 0.79)],
                                         startPoint: .top, endPoint: .bottom))
                ForEach(0..<3) { index in
                    Circle().fill(.white.opacity(0.28))
                        .frame(width: CGFloat(5 + index * 3), height: CGFloat(5 + index * 3))
                        .offset(x: size * [-0.31, 0.29, 0.18][index],
                                y: size * (0.46 - level * [0.40, 0.72, 0.20][index]))
                        .opacity(level > 0 ? 1 : 0)
                }
            }
            .clipShape(Circle())
            .animation(reduceMotion ? nil : .smooth(duration: 0.95), value: level)
            .transaction { if reduceMotion { $0.animation = nil; $0.disablesAnimations = true } }
            Circle().strokeBorder(.white.opacity(0.75), lineWidth: 2).padding(5)
            Circle().trim(from: 0.56, to: 0.84)
                .stroke(.white.opacity(0.8), style: StrokeStyle(lineWidth: 4, lineCap: .round))
                .rotationEffect(.degrees(45)).padding(12)
            Circle().stroke(Color.hydraTint.opacity(0.10), lineWidth: 6).padding(-7)
            Circle().trim(from: 0, to: level)
                .stroke(AngularGradient(colors: [Color(red: 0.27, green: 0.80, blue: 0.73), .hydraTint],
                                        center: .center, startAngle: .degrees(0), endAngle: .degrees(360)),
                        style: StrokeStyle(lineWidth: 6, lineCap: .round))
                .rotationEffect(.degrees(-90)).padding(-7)
                .animation(reduceMotion ? nil : .smooth(duration: 0.95), value: level)
        }
        .shadow(color: .hydraTint.opacity(0.10), radius: 10, y: 6)
    }
}

private struct WaterSurface: Shape {
    var level: Double
    var phase: CGFloat
    var animatableData: AnimatablePair<Double, CGFloat> {
        get { AnimatablePair(level, phase) }
        set { level = newValue.first; phase = newValue.second }
    }

    func path(in rect: CGRect) -> Path {
        let fill = min(max(level, 0), 1)
        let waterline = rect.height * (1 - fill)
        let amplitude = rect.height * min(0.025, fill * 0.25, (1 - fill) * 0.25)
        var path = Path()
        path.move(to: CGPoint(x: 0, y: rect.height))
        for step in 0...60 {
            let x = rect.width * Double(step) / 60
            let y = waterline + sin(Double(step) / 60 * .pi * 2 + phase) * amplitude
            path.addLine(to: CGPoint(x: x, y: y))
        }
        path.addLine(to: CGPoint(x: rect.width, y: rect.height))
        path.closeSubpath()
        return path
    }
}

private struct SaveRipple: View {
    let trigger: UUID?
    let size: CGFloat

    var body: some View {
        KeyframeAnimator(initialValue: 0.0, trigger: trigger) { progress in
            ZStack {
                Circle().stroke(Color.hydraTint.opacity(0.20), lineWidth: 2)
                    .scaleEffect(1 + progress * 0.25)
                ForEach(0..<8) { index in
                    let angle = Double(index) / 8 * .pi * 2
                    Image(systemName: index.isMultiple(of: 2) ? "sparkle" : "circle.fill")
                        .font(.system(size: index.isMultiple(of: 2) ? 12 : 5, weight: .semibold))
                        .foregroundStyle(Color.hydraTint)
                        .offset(x: cos(angle) * (size / 2 + 10 + progress * 16),
                                y: sin(angle) * (size / 2 + 10 + progress * 16))
                }
            }
            .opacity(trigger != nil && progress > 0 && progress < 1 ? 1 - progress : 0)
        } keyframes: { _ in
            LinearKeyframe(0, duration: 0.01)
            CubicKeyframe(1, duration: 0.9)
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}
