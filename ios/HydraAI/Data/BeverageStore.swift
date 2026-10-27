import Foundation

enum LoadState: Equatable {
    case idle
    case loading
    case loaded
    case failed(String)
}

@MainActor
final class BeverageStore: ObservableObject {
    @Published private(set) var logs: [BeverageLog] = []
    @Published private(set) var state: LoadState = .idle

    private let service: any BeverageService

    init(service: any BeverageService = MockBeverageService()) {
        self.service = service
    }

    func refresh() async {
        state = .loading
        do {
            logs = try await service.listBeverages()
            state = .loaded
        } catch {
            state = .failed("Saved beverages could not be loaded.")
        }
    }

    func add(category: String, consumedMl: Int, at: Date) async throws {
        let request = CreateBeverageRequest(
            category: category.trimmingCharacters(in: .whitespacesAndNewlines),
            consumedMl: consumedMl,
            consumedAt: at,
            timezone: TimeZone.current.identifier,
            source: "manual"
        )
        try request.validate()
        _ = try await service.createBeverage(request)
        await refresh()
    }
}
