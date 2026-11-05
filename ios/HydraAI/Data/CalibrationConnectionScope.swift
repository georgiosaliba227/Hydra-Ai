import Foundation
import CryptoKit
import Security

enum CalibrationConnectionScopeError: Error { case unavailable }

/// The connection binding lives only in this device's Keychain. Filenames use unrelated random UUIDs.
/// A changed token is a different connection; returning to the exact prior connection restores its profile.
enum CalibrationConnectionScope {
    struct Binding: Codable {
        let id: UUID
        let endpoint: String
        let tokenFingerprint: String
    }
    static func resolve(_ configuration: APIConfiguration) throws -> UUID {
        let url = try configuration.validatedURL()
        let endpoint = "\(url.scheme!.lowercased())://\(url.host!.lowercased()):\(url.port ?? (url.scheme == "https" ? 443 : 80))"
        let fingerprint = SHA256.hash(data: Data(configuration.token.utf8)).map { String(format: "%02x", $0) }.joined()
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: "HydraAI.manualCalibrationProfiles", kSecAttrAccount as String: "connection-scopes-v1"]
        var read = query; read[kSecReturnData as String] = true
        var result: CFTypeRef?
        let status = SecItemCopyMatching(read as CFDictionary, &result)
        var bindings: [Binding]
        if status == errSecItemNotFound { bindings = [] }
        else {
            guard status == errSecSuccess, let data = result as? Data,
                  let decoded = try? JSONDecoder().decode([Binding].self, from: data) else { throw CalibrationConnectionScopeError.unavailable }
            bindings = decoded
        }
        if let existing = bindings.first(where: { $0.endpoint == endpoint && $0.tokenFingerprint == fingerprint }) { return existing.id }
        let binding = Binding(id: UUID(), endpoint: endpoint, tokenFingerprint: fingerprint)
        bindings.append(binding)
        let attributes: [String: Any] = [kSecValueData as String: try JSONEncoder().encode(bindings),
            kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly]
        let writeStatus = status == errSecItemNotFound
            ? SecItemAdd(query.merging(attributes) { _, new in new } as CFDictionary, nil)
            : SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
        guard writeStatus == errSecSuccess else { throw CalibrationConnectionScopeError.unavailable }
        return binding.id
    }
}
