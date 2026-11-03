import SwiftUI

/// Progress is descriptive and always uses the user's explicitly chosen goal.
struct TodayProgressCard: View {
    let volumeMl: Int
    let goal: DailySummary.Goal?
    let drinkCount: Int
    let confirmation: BeverageLog?
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @ScaledMetric(relativeTo: .largeTitle) private var percentSize: CGFloat = 40
    @State private var feedbackID: UUID?

    private var validGoal: DailySummary.Goal? { goal.flatMap { $0.isValid ? $0 : nil } }
    private var fraction: Double { min(validGoal?.progressRatio ?? 0, 1) }
    private var reached: Bool { fraction >= 1 }
    private var milestone: String {
        switch fraction {
        case 1...: "Goal reached"
        case 0.75...: "Three quarters"
        case 0.5...: "Halfway logged"
        case 0.25...: "First quarter"
        default: volumeMl == 0 ? "A fresh start" : "Your day, taking shape"
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            if typeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 12) { heading; loggedBadge }
            } else {
                HStack(alignment: .top) { heading; Spacer(minLength: 8); loggedBadge }
            }

            if typeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 24) { gauge; details }
            } else {
                HStack(spacing: 24) { gauge; details }
            }

            if validGoal != nil { milestones }

            if reached {
                Label {
                    Text("Goal reached. Nicely recorded.")
                        .accessibilityIdentifier("goalCompletion")
                } icon: {
                    Image(systemName: "checkmark.seal.fill").accessibilityHidden(true)
                }
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(Color.hydraProgressAccent)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(12)
                .background(Color.hydraTint.opacity(0.09), in: RoundedRectangle(cornerRadius: 14))
                .transition(.opacity)
            }

            InfoNote("Drink volume you logged — not a measure of hydration.")
        }
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background {
            RoundedRectangle(cornerRadius: 28, style: .continuous)
                .fill(Color.hydraCard)
                .shadow(color: .hydraTint.opacity(0.06), radius: 16, y: 6)
        }
        .overlay {
            RoundedRectangle(cornerRadius: 28, style: .continuous)
                .strokeBorder(Color.hydraTint.opacity(0.10), lineWidth: 1)
        }
        .onChange(of: confirmation?.id) { _, newID in
            guard let confirmation, newID != nil,
                  Calendar.current.isDateInToday(confirmation.consumedAt) else { return }
            feedbackID = newID
        }
        .sensoryFeedback(.success, trigger: feedbackID)
    }

    private var heading: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Your daily flow").font(.title3.bold())
            Text(Date.now.formatted(.dateTime.weekday(.abbreviated).month(.abbreviated).day()))
                .font(.caption).foregroundStyle(.primary)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Your daily flow, \(Date.now.formatted(.dateTime.weekday(.wide).month().day()))")
        .accessibilityAddTraits(.isHeader)
    }

    private var loggedBadge: some View {
        Label("\(drinkCount) logged", systemImage: reached ? "checkmark.seal.fill" : "drop.fill")
            .font(.caption.weight(.semibold))
            .foregroundStyle(Color.hydraProgressAccent)
            .padding(.horizontal, 10).padding(.vertical, 7)
            .background(Color.hydraTint.opacity(0.10), in: Capsule())
            .accessibilityLabel("\(drinkCount) drinks logged today")
    }

    private var gauge: some View {
        LiquidProgressGauge(volumeMl: volumeMl, progress: validGoal?.progressRatio, feedbackID: feedbackID)
    }

    private var details: some View {
        VStack(alignment: .leading, spacing: 7) {
            Text("Logged today").font(.subheadline.weight(.medium)).foregroundStyle(Color.primary.opacity(0.72))
            if let validGoal {
                VStack(alignment: .leading, spacing: 6) {
                    Text("\(Int((min(validGoal.progressRatio, 9.99) * 100).rounded()))%")
                        .font(.system(size: percentSize, weight: .bold, design: .rounded))
                        .monospacedDigit()
                        .foregroundStyle(Color.hydraProgressAccent)
                        .contentTransition(.numericText())
                        .animation(reduceMotion ? nil : .smooth(duration: 0.8), value: volumeMl)
                        .lineLimit(1).minimumScaleFactor(0.65)
                    Text(milestone).font(.subheadline.weight(.semibold))
                    Text("\(volumeMl.formatted()) of \(validGoal.dailyBeverageGoalMl.formatted()) mL · your own goal")
                        .font(.caption).foregroundStyle(Color.primary.opacity(0.72))
                }
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier("goalProgress")
            } else {
                Text(volumeMl == 0 ? "A fresh start" : "Nicely recorded.").font(.headline)
                Text("Choose a goal to watch it fill.").font(.subheadline).foregroundStyle(.secondary)
                NavigationLink { BackendSettingsView() } label: {
                    Text("Set your own goal").font(.subheadline.weight(.semibold))
                }
                .accessibilityIdentifier("setDailyGoal")
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var milestones: some View {
        HStack(spacing: 7) {
            ForEach(1...4, id: \.self) { step in
                let part = min(max(fraction * 4 - Double(step - 1), 0), 1)
                VStack(spacing: 7) {
                    GeometryReader { geometry in
                        Capsule().fill(Color.hydraTint.opacity(0.11))
                        Capsule()
                            .fill(LinearGradient(colors: [Color(red: 0.27, green: 0.80, blue: 0.73), .hydraTint],
                                                 startPoint: .leading, endPoint: .trailing))
                            .frame(width: geometry.size.width * part)
                    }
                    .frame(height: 7)
                    Text("\(step * 25)%")
                        .font(.caption2.weight(.semibold).monospacedDigit())
                        .foregroundStyle(part >= 1 ? Color.hydraProgressAccent : Color.primary.opacity(0.65))
                }
                .frame(maxWidth: .infinity)
            }
        }
        .animation(reduceMotion ? nil : .smooth(duration: 0.9), value: fraction)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Goal milestones")
        .accessibilityValue("\(Int(fraction * 4)) of 4 recorded")
        .accessibilityIdentifier("progressMilestones")
    }
}
