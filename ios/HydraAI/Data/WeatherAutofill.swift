import CoreLocation
import Foundation

/// A coordinate rounded to two decimal places (about 1 km) before it can leave the device.
struct RoundedCoordinate: Equatable, Sendable {
    let latitude: Double
    let longitude: Double

    init(latitude: Double, longitude: Double) throws {
        guard latitude.isFinite, longitude.isFinite, (-90...90).contains(latitude), (-180...180).contains(longitude) else {
            throw WeatherAutofillError.locationUnavailable
        }
        self.latitude = Self.round(latitude)
        self.longitude = Self.round(longitude)
    }

    init(_ coordinate: CLLocationCoordinate2D) throws {
        try self.init(latitude: coordinate.latitude, longitude: coordinate.longitude)
    }

    /// Two decimals; never "-0.00".
    var latitudeText: String { Self.text(latitude) }
    var longitudeText: String { Self.text(longitude) }

    private static func round(_ value: Double) -> Double {
        let rounded = (value * 100).rounded() / 100
        return rounded == 0 ? 0 : rounded
    }

    private static func text(_ value: Double) -> String {
        String(format: "%.2f", locale: Locale(identifier: "en_US_POSIX"), value)
    }
}

/// One forecast hour from Open-Meteo, nearest to the planned start.
struct WeatherConditions: Equatable, Sendable {
    let temperatureC: Double
    let humidityPercent: Double
    /// The forecast hour that was used (absolute time).
    let forecastHour: Date
    let coordinate: RoundedCoordinate
    /// Open-Meteo's resolved IANA timezone for the area, if returned.
    let timezoneIdentifier: String?
}

enum WeatherAutofillError: LocalizedError, Equatable {
    case consentRequired
    case locationDenied
    case locationUnavailable
    case offline
    case outOfForecastRange
    case unavailable
    case invalidResponse

    var errorDescription: String? {
        switch self {
        case .consentRequired:
            return "Turn on \"Use my location to fill in the weather\" first. Nothing was looked up."
        case .locationDenied:
            return "Location access is off for Hydra. You can allow it in Settings, or enter the weather yourself."
        case .locationUnavailable:
            return "Your approximate location could not be found. Enter the weather yourself."
        case .offline:
            return "You appear to be offline. Enter the weather yourself or try again later."
        case .outOfForecastRange:
            return "The planned start is outside the available weather forecast. Enter the weather yourself."
        case .unavailable:
            return "The weather service is unavailable right now. Enter the weather yourself."
        case .invalidResponse:
            return "The weather service returned data that could not be used. Enter the weather yourself."
        }
    }
}

// MARK: - Consent

/// The stored "Use my location to fill in the weather" preference. Off by default.
/// Granting it is the only thing that allows a location lookup and the Open-Meteo request.
@MainActor
final class WeatherLocationConsentStore {
    static let key = "hydra.weatherLocationConsent"
    private let defaults: UserDefaults

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
    }

    var isGranted: Bool {
        get { defaults.bool(forKey: Self.key) }
        set { defaults.set(newValue, forKey: Self.key) }
    }
}

// MARK: - Location

@MainActor
protocol ApproximateLocationProvider: AnyObject {
    /// Requests when-in-use permission if needed, then returns one reduced-accuracy fix, rounded.
    func approximateCoordinate() async throws -> RoundedCoordinate
}

/// When-in-use, reduced-accuracy, one-shot location. No continuous updates, nothing is stored.
@MainActor
final class CoreLocationApproximateLocationProvider: NSObject, ApproximateLocationProvider, CLLocationManagerDelegate {
    private let manager = CLLocationManager()
    private var authorizationContinuation: CheckedContinuation<CLAuthorizationStatus, Never>?
    private var locationContinuation: CheckedContinuation<CLLocation, Error>?

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyReduced
    }

    func approximateCoordinate() async throws -> RoundedCoordinate {
        guard authorizationContinuation == nil, locationContinuation == nil else {
            throw WeatherAutofillError.locationUnavailable
        }
        var status = manager.authorizationStatus
        if status == .notDetermined {
            status = await withCheckedContinuation { continuation in
                authorizationContinuation = continuation
                manager.requestWhenInUseAuthorization()
            }
        }
        guard status == .authorizedWhenInUse || status == .authorizedAlways else {
            throw WeatherAutofillError.locationDenied
        }
        let location: CLLocation = try await withCheckedThrowingContinuation { continuation in
            locationContinuation = continuation
            manager.requestLocation()
        }
        return try RoundedCoordinate(location.coordinate)
    }

    nonisolated func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        let status = manager.authorizationStatus
        MainActor.assumeIsolated {
            guard status != .notDetermined, let continuation = authorizationContinuation else { return }
            authorizationContinuation = nil
            continuation.resume(returning: status)
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        let location = locations.last
        MainActor.assumeIsolated {
            guard let continuation = locationContinuation else { return }
            locationContinuation = nil
            if let location { continuation.resume(returning: location) }
            else { continuation.resume(throwing: WeatherAutofillError.locationUnavailable) }
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        let denied = (error as? CLError)?.code == .denied
        MainActor.assumeIsolated {
            guard let continuation = locationContinuation else { return }
            locationContinuation = nil
            continuation.resume(throwing: denied ? WeatherAutofillError.locationDenied : WeatherAutofillError.locationUnavailable)
        }
    }
}

// MARK: - Open-Meteo

@MainActor
protocol WeatherForecastClient: AnyObject {
    func conditions(at coordinate: RoundedCoordinate, nearest start: Date) async throws -> WeatherConditions
}

/// Free Open-Meteo forecast API (no key). Sends only the rounded coordinate and the requested variables.
@MainActor
final class OpenMeteoWeatherClient: WeatherForecastClient {
    static let host = "api.open-meteo.com"
    private let session: URLSession

    init(session: URLSession? = nil) {
        if let session {
            self.session = session
        } else {
            let configuration = URLSessionConfiguration.ephemeral
            configuration.httpCookieStorage = nil
            configuration.urlCache = nil
            configuration.timeoutIntervalForRequest = 15
            self.session = URLSession(configuration: configuration)
        }
    }

    static func url(for coordinate: RoundedCoordinate) -> URL {
        var components = URLComponents()
        components.scheme = "https"
        components.host = host
        components.path = "/v1/forecast"
        components.queryItems = [
            URLQueryItem(name: "latitude", value: coordinate.latitudeText),
            URLQueryItem(name: "longitude", value: coordinate.longitudeText),
            URLQueryItem(name: "hourly", value: "temperature_2m,relative_humidity_2m"),
            URLQueryItem(name: "timezone", value: "auto"),
            // Absolute hour timestamps avoid parsing local times across daylight-saving changes.
            URLQueryItem(name: "timeformat", value: "unixtime"),
        ]
        return components.url!
    }

    func conditions(at coordinate: RoundedCoordinate, nearest start: Date) async throws -> WeatherConditions {
        var request = URLRequest(url: Self.url(for: coordinate), cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 15)
        request.httpShouldHandleCookies = false
        let data: Data, response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch let error as URLError {
            switch error.code {
            case .notConnectedToInternet, .networkConnectionLost, .timedOut, .cannotFindHost,
                 .cannotConnectToHost, .dnsLookupFailed, .dataNotAllowed, .internationalRoamingOff:
                throw WeatherAutofillError.offline
            default:
                throw WeatherAutofillError.unavailable
            }
        } catch {
            throw WeatherAutofillError.unavailable
        }
        guard let http = response as? HTTPURLResponse, http.url?.host == Self.host else {
            throw WeatherAutofillError.invalidResponse
        }
        // Open-Meteo returns 400 with a reason for out-of-range coordinates or parameters.
        guard http.statusCode == 200 else {
            throw http.statusCode == 400 ? WeatherAutofillError.outOfForecastRange : WeatherAutofillError.unavailable
        }
        return try OpenMeteoForecastParser.nearestHour(in: data, to: start, coordinate: coordinate)
    }
}

enum OpenMeteoForecastParser {
    static let maximumBytes = 512 * 1024
    /// A start farther than this from every returned hour is outside the forecast.
    static let maximumDistance: TimeInterval = 90 * 60

    private struct Payload: Decodable {
        struct Hourly: Decodable {
            let time: [Double]
            let temperature_2m: [Double?]
            let relative_humidity_2m: [Double?]
        }
        let timezone: String?
        let hourly: Hourly
    }

    /// Picks the hour nearest `start` that has both values; ties go to the earlier hour.
    static func nearestHour(in data: Data, to start: Date, coordinate: RoundedCoordinate) throws -> WeatherConditions {
        guard data.count <= maximumBytes, let payload = try? JSONDecoder().decode(Payload.self, from: data) else {
            throw WeatherAutofillError.invalidResponse
        }
        let hourly = payload.hourly
        guard !hourly.time.isEmpty, hourly.time.count <= 24 * 32,
              hourly.time.count == hourly.temperature_2m.count,
              hourly.time.count == hourly.relative_humidity_2m.count else {
            throw WeatherAutofillError.invalidResponse
        }
        let target = start.timeIntervalSince1970
        var best: (index: Int, distance: TimeInterval)?
        for (index, time) in hourly.time.enumerated() {
            guard time.isFinite, hourly.temperature_2m[index] != nil, hourly.relative_humidity_2m[index] != nil else { continue }
            let distance = abs(time - target)
            if best == nil || distance < best!.distance { best = (index, distance) }
        }
        guard let best, best.distance <= maximumDistance else { throw WeatherAutofillError.outOfForecastRange }
        guard let temperature = hourly.temperature_2m[best.index], let humidity = hourly.relative_humidity_2m[best.index],
              temperature.isFinite, humidity.isFinite,
              (-60...60).contains(temperature), (0...100).contains(humidity) else {
            throw WeatherAutofillError.invalidResponse
        }
        let timezone = payload.timezone.flatMap { TimeZone(identifier: $0) != nil ? $0 : nil }
        return WeatherConditions(
            temperatureC: (temperature * 10).rounded() / 10,
            humidityPercent: humidity.rounded(),
            forecastHour: Date(timeIntervalSince1970: hourly.time[best.index]),
            coordinate: coordinate,
            timezoneIdentifier: timezone
        )
    }
}

// MARK: - Consent-gated orchestration

/// Checks consent before touching location or the network. Nothing is cached.
@MainActor
final class WeatherAutofillService {
    let consent: WeatherLocationConsentStore
    private let location: any ApproximateLocationProvider
    private let weather: any WeatherForecastClient

    init(consent: WeatherLocationConsentStore? = nil,
         location: (any ApproximateLocationProvider)? = nil,
         weather: (any WeatherForecastClient)? = nil) {
        self.consent = consent ?? WeatherLocationConsentStore()
        self.location = location ?? CoreLocationApproximateLocationProvider()
        self.weather = weather ?? OpenMeteoWeatherClient()
    }

    func conditions(nearest start: Date) async throws -> WeatherConditions {
        guard consent.isGranted else { throw WeatherAutofillError.consentRequired }
        let coordinate = try await location.approximateCoordinate()
        // Consent may be withdrawn while the location prompt is showing.
        guard consent.isGranted else { throw WeatherAutofillError.consentRequired }
        return try await weather.conditions(at: coordinate, nearest: start)
    }
}
