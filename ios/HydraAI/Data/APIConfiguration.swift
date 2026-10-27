import Foundation
import Security

struct APIConfiguration {
    var baseURL: String
    var token: String
    var offline: Bool

    static func load() -> APIConfiguration {
        let defaults = UserDefaults.standard
        var config = APIConfiguration(baseURL: defaults.string(forKey: "hydra.backendURL") ?? "http://127.0.0.1:8000", token: CredentialStore.read() ?? "", offline: defaults.bool(forKey: "hydra.offline"))
        #if DEBUG
        // Runtime-only simulator configuration; no credential is shipped in the app.
        let env = ProcessInfo.processInfo.environment
        if let url = env["HYDRA_TEST_BACKEND_URL"], let token = env["HYDRA_TEST_API_TOKEN"] {
            config = APIConfiguration(baseURL: url, token: token, offline: false)
        }
        #endif
        return config
    }

    func validatedURL() throws -> URL {
        guard let url = URL(string: baseURL), let host = url.host,
              url.user == nil, url.password == nil, url.query == nil, url.fragment == nil,
              url.path.isEmpty || url.path == "/" else { throw ServiceError.configuration }
        let parts = host.split(separator: ".").compactMap { Int($0) }
        let privateIPv4 = parts.count == 4 && parts.allSatisfy { (0...255).contains($0) } &&
            (parts[0] == 10 || parts[0] == 127 || (parts[0] == 192 && parts[1] == 168) || (parts[0] == 172 && (16...31).contains(parts[1])))
        let local = host == "localhost" || host == "[::1]" || host == "::1" || host.hasSuffix(".local") || privateIPv4
        guard url.scheme == "https" || (url.scheme == "http" && local), token.count >= 32,
              !token.contains("\n"), !token.contains("\r") else { throw ServiceError.configuration }
        return url
    }

    func save() throws {
        if !offline { _ = try validatedURL() }
        try CredentialStore.write(token)
        UserDefaults.standard.set(baseURL, forKey: "hydra.backendURL")
        UserDefaults.standard.set(offline, forKey: "hydra.offline")
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
