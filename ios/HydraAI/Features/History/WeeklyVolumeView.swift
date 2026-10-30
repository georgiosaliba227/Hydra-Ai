import SwiftUI

struct WeeklyVolumeView: View {
    let logs: [BeverageLog]

    private var days: [Date] {
        let calendar = Calendar.current
        let today = calendar.startOfDay(for: .now)
        return (0..<7).reversed().compactMap { calendar.date(byAdding: .day, value: -$0, to: today) }
    }

    private var dailyVolumes: [Int] {
        days.map { day in
            logs.filter { Calendar.current.isDate($0.consumedAt, inSameDayAs: day) }
                .reduce(0) { $0 + $1.consumedMl }
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline) {
                Text("Last 7 days").font(.headline)
                Spacer()
                Text("\(dailyVolumes.reduce(0, +).formatted()) mL total")
                    .font(.subheadline.monospacedDigit())
                    .foregroundStyle(.secondary)
            }

            HStack(alignment: .bottom, spacing: 10) {
                ForEach(days.indices, id: \.self) { index in
                    let isToday = index == days.count - 1
                    VStack(spacing: 6) {
                        Text(dailyVolumes[index].formatted(.number.notation(.compactName)))
                            .font(.caption2.monospacedDigit())
                            .fixedSize()
                        GeometryReader { geometry in
                            let maximum = max(dailyVolumes.max() ?? 0, 1)
                            let fraction = CGFloat(dailyVolumes[index]) / CGFloat(maximum)
                            RoundedRectangle(cornerRadius: 6, style: .continuous)
                                .fill(isToday ? Color.hydraTint : Color.hydraTint.opacity(0.45))
                                .frame(height: max(3, geometry.size.height * fraction))
                                .frame(maxHeight: .infinity, alignment: .bottom)
                        }
                        .frame(height: 84)
                        Text(days[index], format: .dateTime.weekday(.narrow))
                            .font(.caption.weight(isToday ? .bold : .regular))
                    }
                    .frame(maxWidth: .infinity)
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel("\(days[index].formatted(date: .abbreviated, time: .omitted)), \(dailyVolumes[index]) milliliters logged")
                }
            }
            Text("Bars compare logged days with each other, not with a daily target.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(.vertical, 4)
    }
}
