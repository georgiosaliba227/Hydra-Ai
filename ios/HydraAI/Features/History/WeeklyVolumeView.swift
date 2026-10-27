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
            Text("Last 7 days")
                .font(.headline)
            Text("Confirmed beverage volume by day · mL")
                .font(.footnote)
                .foregroundStyle(.secondary)

            HStack(alignment: .bottom, spacing: 10) {
                ForEach(days.indices, id: \.self) { index in
                    VStack(spacing: 6) {
                        Text(dailyVolumes[index].formatted())
                            .font(.caption2.monospacedDigit())
                            .lineLimit(1)
                            .minimumScaleFactor(0.7)
                        GeometryReader { geometry in
                            let maximum = max(dailyVolumes.max() ?? 0, 1)
                            let fraction = CGFloat(dailyVolumes[index]) / CGFloat(maximum)
                            RoundedRectangle(cornerRadius: 5)
                                .fill(.cyan)
                                .frame(height: max(2, geometry.size.height * fraction))
                                .frame(maxHeight: .infinity, alignment: .bottom)
                        }
                        .frame(height: 70)
                        Text(days[index], format: .dateTime.weekday(.narrow))
                            .font(.caption)
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
