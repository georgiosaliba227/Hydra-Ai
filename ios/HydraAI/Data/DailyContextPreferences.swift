import Foundation

/// Only opt-in preferences, rounded area, and weather metadata are persisted. Never Health records.
@MainActor
final class DailyContextPreferences {
    static let setupKey = "hydra.dailyContext.setupCompleted"
    static let healthAutoKey = "hydra.dailyContext.healthAutoEnabled"
    static let weatherAutoKey = "hydra.dailyContext.weatherAutoEnabled"
    private static let areaKey = "hydra.dailyContext.roundedArea"
    private let defaults: UserDefaults

    init(defaults: UserDefaults = .standard) { self.defaults = defaults }
    var setupCompleted: Bool {
        get { defaults.bool(forKey: Self.setupKey) }
        set { defaults.set(newValue, forKey: Self.setupKey) }
    }
    var healthAutoEnabled: Bool {
        get { defaults.bool(forKey: Self.healthAutoKey) }
        set { defaults.set(newValue, forKey: Self.healthAutoKey) }
    }
    var weatherAutoEnabled: Bool {
        get { defaults.bool(forKey: Self.weatherAutoKey) }
        set { defaults.set(newValue, forKey: Self.weatherAutoKey) }
    }
    var savedCoordinate: RoundedCoordinate? {
        get {
            guard weatherAutoEnabled, let area = defaults.array(forKey: Self.areaKey) as? [Double], area.count == 2 else { return nil }
            return try? RoundedCoordinate(latitude: area[0], longitude: area[1])
        }
        set {
            guard weatherAutoEnabled, let newValue else { defaults.removeObject(forKey: Self.areaKey); return }
            defaults.set([newValue.latitude, newValue.longitude], forKey: Self.areaKey)
        }
    }
    func clearWeather() { defaults.removeObject(forKey: Self.areaKey) }
}
