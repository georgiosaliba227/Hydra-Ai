import Foundation

/// Privacy policy for real on-device records and their pending mutations only.
/// Shared parent folders remain unchanged so server/demo files retain their policy.
enum OnDeviceProtectedFile {
    static func protectExisting(_ fileURL: URL) throws {
        try FileManager.default.setAttributes([
            .posixPermissions: 0o600,
            .protectionKey: FileProtectionType.completeUntilFirstUserAuthentication
        ], ofItemAtPath: fileURL.path)
        var url = fileURL, values = URLResourceValues()
        values.isExcludedFromBackup = true
        try url.setResourceValues(values)
    }

    static func write(_ data: Data, to fileURL: URL) throws {
        let manager = FileManager.default, parent = fileURL.deletingLastPathComponent()
        let directoryAttributes: [FileAttributeKey: Any] = [
            .posixPermissions: 0o700,
            .protectionKey: FileProtectionType.completeUntilFirstUserAuthentication
        ]
        try manager.createDirectory(at: parent, withIntermediateDirectories: true, attributes: directoryAttributes)
        var stagingDirectory = parent.appendingPathComponent(".on-device-write-\(UUID().uuidString)", isDirectory: true)
        try manager.createDirectory(at: stagingDirectory, withIntermediateDirectories: false, attributes: directoryAttributes)
        defer { try? manager.removeItem(at: stagingDirectory) }
        var values = URLResourceValues(); values.isExcludedFromBackup = true
        try stagingDirectory.setResourceValues(values)
        let staged = stagingDirectory.appendingPathComponent("records.json")
        try data.write(to: staged, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        try protectExisting(staged)
        // Keep the staged file's backup exclusion and protection when replacing.
        if manager.fileExists(atPath: fileURL.path) {
            _ = try manager.replaceItemAt(fileURL, withItemAt: staged, options: [.usingNewMetadataOnly])
        } else {
            try manager.moveItem(at: staged, to: fileURL)
        }
    }
}
