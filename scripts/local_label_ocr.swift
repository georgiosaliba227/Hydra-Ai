// Local printed-label evidence. No network, training or persistent image storage.
import Foundation
import Vision

guard CommandLine.arguments.count == 3 else { exit(2) }
let source = URL(fileURLWithPath: CommandLine.arguments[1])
let destination = URL(fileURLWithPath: CommandLine.arguments[2])
guard !FileManager.default.fileExists(atPath: destination.path) else { exit(2) }
do {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = false
    request.recognitionLanguages = ["en-US", "fr-FR", "de-DE"]
    request.minimumTextHeight = 0.004
    try VNImageRequestHandler(url: source, options: [:]).perform([request])
    let lines = (request.results ?? []).compactMap { result -> String? in
        guard let text = result.topCandidates(1).first, text.confidence >= 0.65 else { return nil }
        return text.string
    }
    // An overlong label is incomplete evidence; leave it unknown rather than
    // truncating away serving or conflicting-volume qualifiers.
    let text = lines.joined(separator: "\n")
    let data = try JSONSerialization.data(withJSONObject: ["label_text": text.count <= 600 ? text : ""])
    try data.write(to: destination, options: .atomic)
} catch {
    // OCR failure is a missing-size result, never guessed capacity.
    try? Data("{\"label_text\":\"\"}".utf8).write(to: destination, options: .atomic)
}
