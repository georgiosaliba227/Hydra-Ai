import XCTest

@testable import BeverageCore

final class MemoryBudgetTests: XCTestCase {
  func testRejectsMLXActivePlusCacheAndResidentBudgets() {
    let budget = MemoryBudget(mlxBytes: 100, residentBytes: 120)
    XCTAssertNil(budget.violation(mlxActive: 80, mlxCache: 20, resident: 119))
    XCTAssertEqual(
      budget.violation(mlxActive: 90, mlxCache: 11, resident: 90), "mlx_budget_exceeded")
    XCTAssertEqual(
      budget.violation(mlxActive: 80, mlxCache: 0, resident: 121), "rss_budget_exceeded")
    XCTAssertEqual(
      budget.violation(mlxActive: -1, mlxCache: 0, resident: 10), "memory_measurement_invalid")
  }
}
