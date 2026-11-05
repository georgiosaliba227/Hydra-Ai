import Foundation
import Security

struct APIConfiguration: CustomStringConvertible, CustomDebugStringConvertible {
    var baseURL: String
    var token: String
    var offline: Bool { didSet { if offline { onDevice = false } } }
    var onDevice: Bool { didSet { if onDevice { offline = false } } }
    var insightsEnabled: Bool
    var description: String { "APIConfiguration(onDevice: \(onDevice), offline: \(offline), insightsEnabled: \(insightsEnabled))" }
    var debugDescription: String { description }

    init(baseURL: String, token: String, offline: Bool, onDevice: Bool = false, insightsEnabled: Bool = false) {
        self.baseURL = baseURL
        self.token = token
        self.offline = offline && !onDevice
        self.onDevice = onDevice
        self.insightsEnabled = insightsEnabled
    }

    /// Separate from the destination for photos and confirmed drinks.
    var backendInsightsConfiguration: APIConfiguration? {
        guard !offline, !onDevice || insightsEnabled, (try? validatedURL()) != nil else { return nil }
        return APIConfiguration(baseURL: baseURL, token: token, offline: false)
    }

    static func load(defaults: UserDefaults = .standard) -> APIConfiguration {
        let firstInstall = ["hydra.backendURL", "hydra.offline", "hydra.onDevice"].allSatisfy { defaults.object(forKey: $0) == nil }
        var config = APIConfiguration(baseURL: defaults.string(forKey: "hydra.backendURL") ?? "http://127.0.0.1:8000", token: CredentialStore.read() ?? "", offline: defaults.bool(forKey: "hydra.offline"), onDevice: firstInstall || defaults.bool(forKey: "hydra.onDevice"), insightsEnabled: defaults.bool(forKey: "hydra.backendInsights"))
        #if DEBUG
        // Runtime-only simulator configuration; no credential is shipped in the app.
        let env = ProcessInfo.processInfo.environment
        if let url = env["HYDRA_TEST_BACKEND_URL"], let token = env["HYDRA_TEST_API_TOKEN"] {
            config = APIConfiguration(baseURL: url, token: token, offline: false)
        }
        // UI/inference tests opt in explicitly; production never changes mode automatically.
        if env["HYDRA_TEST_ON_DEVICE"] == "1" {
            config.onDevice = true
        }
        #endif
        return config
    }

    func validatedURL() throws -> URL {
        guard let url = URL(string: baseURL), let host = url.host,
              url.user == nil, url.password == nil, url.query == nil, url.fragment == nil,
              url.path.isEmpty || url.path == "/" else { throw ServiceError.configuration }
        let labels = host.split(separator: ".", omittingEmptySubsequences: false)
        let parts = labels.compactMap { label -> Int? in
            guard !label.isEmpty, label.allSatisfy({ $0.isASCII && $0.isNumber }) else { return nil }
            return Int(label)
        }
        let privateIPv4 = labels.count == 4 && parts.count == 4 && parts.allSatisfy { (0...255).contains($0) } &&
            (parts[0] == 10 || parts[0] == 127 || (parts[0] == 192 && parts[1] == 168) || (parts[0] == 172 && (16...31).contains(parts[1])))
        let local = host == "localhost" || host == "[::1]" || host == "::1" || host.hasSuffix(".local") || privateIPv4
        guard url.scheme == "https" || (url.scheme == "http" && local), token.count >= 32,
              token.unicodeScalars.allSatisfy({ $0.isASCII && !CharacterSet.whitespacesAndNewlines.contains($0) && !CharacterSet.controlCharacters.contains($0) }) else { throw ServiceError.configuration }
        return url
    }

    func save() throws {
        if !offline && (!onDevice || insightsEnabled) { _ = try validatedURL() }
        try CredentialStore.write(token)
        UserDefaults.standard.set(baseURL, forKey: "hydra.backendURL")
        UserDefaults.standard.set(offline, forKey: "hydra.offline")
        UserDefaults.standard.set(onDevice, forKey: "hydra.onDevice")
        UserDefaults.standard.set(insightsEnabled, forKey: "hydra.backendInsights")
    }
}

private enum CredentialStore {
    static let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: "HydraAI.localBackend", kSecAttrAccount as String: "development-session"]
    static func read() -> String? {
        var request = query
        request[kSecReturnData as String] = true
        var result: CFTypeRef?
        guard SecItemCopyMatching(request as CFDictionary, &result) == errSecSuccess, let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }
    static func write(_ value: String) throws {
        let attributes: [String: Any] = [kSecValueData as String: Data(value.utf8), kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly]
        let status = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
        if status == errSecItemNotFound {
            guard SecItemAdd(query.merging(attributes) { _, new in new } as CFDictionary, nil) == errSecSuccess else { throw ServiceError.credentials }
        } else if status != errSecSuccess { throw ServiceError.credentials }
    }
}
