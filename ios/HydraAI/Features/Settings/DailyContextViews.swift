import SwiftUI

/// Permission choices are explicit; automatic refresh never presents these prompts.
struct DailyContextSetupView: View {
    @EnvironmentObject private var context: DailyContextCoordinator
    @EnvironmentObject private var units: DisplayUnits

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text("Make Hydra yours")
                        .font(.title2.bold()).accessibilityIdentifier("contextSetupTitle")
                    Text("Connect once, then Hydra checks for fresh workout and weather context automatically. Both are optional, and you can change them in Settings.")
                    Text("Display units: \(units.system.label). Change units in Settings.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                Section("Apple Health") {
                    Text("Reads recent workouts, heart rate and active energy on this iPhone. These records stay on your phone; heart rate is context, never a hydration measurement.")
                        .font(.footnote)
                    Button(context.healthAutoEnabled ? "Reconnect Apple Health" : "Connect Apple Health") {
                        Task { await context.connectHealth() }
                    }
                    .accessibilityIdentifier("connectAutomaticHealth")
                    .disabled(context.isRefreshing)
                    ContextStatusRow(title: "Workouts", state: context.healthState, success: context.lastHealthSuccess)
                }
                Section("Local weather") {
                    Text(Self.weatherDisclosure)
                        .font(.footnote).accessibilityIdentifier("automaticWeatherDisclosure")
                    Button(context.weatherAutoEnabled ? "Update my approximate area" : "Allow automatic weather") {
                        Task { await context.enableAutomaticWeather() }
                    }
                    .accessibilityIdentifier("enableAutomaticWeather")
                    .disabled(context.isRefreshing)
                    ContextStatusRow(title: "Weather", state: context.weatherState, success: context.lastWeatherSuccess)
                }
                Section {
                    Button("Continue") { context.completeSetup() }
                        .font(.headline).accessibilityIdentifier("finishContextSetup")
                        .disabled(context.isRefreshing)
                    Text("You can continue without either connection. Automatic updates run when you open Hydra and when iOS allows background refresh; timing is controlled by iOS.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Welcome to Hydra")
            .navigationBarTitleDisplayMode(.inline)
            .interactiveDismissDisabled()
        }
    }

    static let weatherDisclosure = "With your permission, Hydra saves your rounded approximate area on this iPhone and sends that area to Open-Meteo for automatic weather updates. No continuous tracking or background location access. Turn this off to remove the saved area and weather."
}

struct DailyContextSettingsSections: View {
    @EnvironmentObject private var context: DailyContextCoordinator

    var body: some View {
        Section {
            Toggle("Refresh Apple Health workouts automatically", isOn: Binding(
                get: { context.healthAutoEnabled },
                set: { enabled in Task { await context.setHealthAutoEnabled(enabled) } }
            ))
            .accessibilityIdentifier("automaticHealthToggle")
            ContextStatusRow(title: "Workouts", state: context.healthState, success: context.lastHealthSuccess)
            Text("Reads on this iPhone using your Health permissions. Empty results can mean no recent workouts or no read access. Records stay on device.")
                .font(.footnote).foregroundStyle(.secondary)
        } header: { Text("Automatic workout context") }
        Section {
            Toggle("Refresh local weather automatically", isOn: Binding(
                get: { context.weatherAutoEnabled },
                set: { enabled in
                    if enabled { Task { await context.enableAutomaticWeather() } }
                    else { context.disableAutomaticWeather() }
                }
            ))
            .accessibilityIdentifier("automaticWeatherToggle")
            ContextStatusRow(title: "Weather", state: context.weatherState, success: context.lastWeatherSuccess)
            if context.weatherAutoEnabled {
                Button("Update my approximate area") { Task { await context.enableAutomaticWeather() } }
                    .disabled(context.isRefreshing)
            }
            Text(DailyContextSetupView.weatherDisclosure).font(.footnote).foregroundStyle(.secondary)
        } header: { Text("Automatic local weather") }
        Section {
            Button("Check for context updates") { Task { await context.refreshIfNeeded() } }
                .disabled(context.isRefreshing)
                .accessibilityIdentifier("refreshDailyContext")
            Text("Hydra refreshes on open, as the day changes and during available iOS background time. Locked Health data and background restrictions can delay updates. Freshness above shows the last successful read.")
                .font(.footnote).foregroundStyle(.secondary)
        }
    }
}

struct DailyContextSettingsView: View {
    var body: some View {
        Form { DailyContextSettingsSections() }
            .navigationTitle("Automatic context").navigationBarTitleDisplayMode(.inline)
    }
}

struct DailyContextCard: View {
    @EnvironmentObject private var context: DailyContextCoordinator
    @EnvironmentObject private var units: DisplayUnits

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("Your daily context", systemImage: "arrow.triangle.2.circlepath")
                .font(.headline)
            if context.healthAutoEnabled {
                ContextStatusRow(title: "Apple Health", state: context.healthState, success: context.lastHealthSuccess)
            } else { Text("Automatic workout context is off.").font(.subheadline).foregroundStyle(.secondary) }
            if context.weatherAutoEnabled {
                if let weather = context.currentWeather {
                    Text("\(units.temperature(weather.temperatureC)) · \(weather.humidityPercent.formatted(.number.precision(.fractionLength(0))))% humidity")
                        .font(.subheadline).accessibilityIdentifier("dailyWeatherSummary")
                    Text("Open-Meteo · forecast for \(weather.forecastHour.formatted(date: .abbreviated, time: .shortened))")
                        .font(.caption).foregroundStyle(.secondary)
                }
                ContextStatusRow(title: "Weather", state: context.weatherState, success: context.lastWeatherSuccess)
            } else { Text("Automatic local weather is off.").font(.subheadline).foregroundStyle(.secondary) }
            NavigationLink("Manage automatic context") { DailyContextSettingsView() }
                .font(.subheadline).accessibilityIdentifier("manageDailyContext")
            Text("Workout and weather context do not change your research score's product rules.")
                .font(.caption).foregroundStyle(.secondary)
        }
        .hydraCard().accessibilityIdentifier("dailyContextCard")
    }
}

private struct ContextStatusRow: View {
    let title: String
    let state: LoadState
    let success: Date?

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            switch state {
            case .loading: ProgressView("Updating \(title.lowercased())…")
            case .failed(let message): Text(message).font(.footnote).foregroundStyle(.secondary)
            case .idle: Text("\(title): not updated yet").font(.footnote).foregroundStyle(.secondary)
            case .loaded: Text("\(title): context read completed").font(.footnote)
            }
            if let success {
                Text("Last successful update: \(success.formatted(date: .abbreviated, time: .shortened))")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .accessibilityElement(children: .combine)
    }
}
