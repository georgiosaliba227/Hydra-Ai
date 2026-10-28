import Foundation
import Combine

/// One camera consent/result scope per saved backend configuration. Tickets keep
/// delayed responses from an old connection (including A -> B -> A) out of UI.
@MainActor
final class CameraSession: ObservableObject {
    struct Ticket: Equatable {
        let generation: UUID
        let identifier = UUID()
        let mode: String?
    }

    @Published private(set) var generation: UUID?
    @Published private(set) var mode: String?
    @Published var consent = false
    @Published var metaConsent = false
    @Published private(set) var result: RecognitionResult?
    @Published private(set) var isAnalyzing = false
    @Published private(set) var isLoadingCapabilities = false
    private var capabilitiesTicket: Ticket?
    private var analysisTicket: Ticket?

    func bind(to generation: UUID) {
        guard self.generation != generation else { return }
        self.generation = generation
        mode = nil
        revokePhotoConsent()
        capabilitiesTicket = nil; analysisTicket = nil
        isAnalyzing = false; isLoadingCapabilities = false
    }

    func revokePhotoConsent() {
        consent = false; metaConsent = false; result = nil
    }

    func discardResult() { result = nil }

    func beginCapabilities(generation: UUID) -> Ticket? {
        bind(to: generation)
        guard !isAnalyzing, !isLoadingCapabilities else { return nil }
        mode = nil; revokePhotoConsent()
        let ticket = Ticket(generation: generation, mode: nil)
        capabilitiesTicket = ticket; isLoadingCapabilities = true
        return ticket
    }

    @discardableResult
    func completeCapabilities(_ mode: String?, ticket: Ticket, currentGeneration: UUID) -> Bool {
        guard generation == currentGeneration, ticket.generation == currentGeneration,
              capabilitiesTicket == ticket else { return false }
        capabilitiesTicket = nil; isLoadingCapabilities = false
        self.mode = mode
        return true
    }

    func beginAnalysis(generation: UUID) -> Ticket? {
        // Never transfer an old consent to a newly selected connection, even if
        // SwiftUI has not yet observed the configuration-generation change.
        guard self.generation == generation else {
            bind(to: generation)
            return nil
        }
        guard consent, !isAnalyzing, !isLoadingCapabilities, let mode,
              ["mock", "meta_live"].contains(mode), mode != "meta_live" || metaConsent else { return nil }
        let ticket = Ticket(generation: generation, mode: mode)
        analysisTicket = ticket; isAnalyzing = true; result = nil
        return ticket
    }

    @discardableResult
    func completeAnalysis(_ result: RecognitionResult?, ticket: Ticket, currentGeneration: UUID) -> Bool {
        guard generation == currentGeneration, ticket.generation == currentGeneration,
              analysisTicket == ticket else { return false }
        analysisTicket = nil; isAnalyzing = false
        self.result = result
        return true
    }
}
