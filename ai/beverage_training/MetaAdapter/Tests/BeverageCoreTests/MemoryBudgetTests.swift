import XCTest

@testable import BeverageCore

final class MemoryBudgetTests: XCTestCase {
  func testGPUResidencyNeverExceedsRecommendationOrExistingBudget() {
    let gib = 1024 * 1024 * 1024
    XCTAssertEqual(MemoryBudget.gpuResidencyBytes(recommended: 18*gib, mlxBudget: 19*gib), 16*gib)
    XCTAssertEqual(MemoryBudget.gpuResidencyBytes(recommended: 12*gib, mlxBudget: 19*gib), 12*gib)
    XCTAssertEqual(MemoryBudget.gpuResidencyBytes(recommended: 18*gib, mlxBudget: 10*gib), 10*gib)
    XCTAssertEqual(MemoryBudget.gpuResidencyBytes(recommended: 0, mlxBudget: 19*gib), 0)
    XCTAssertEqual(MemoryBudget.gpuResidencyBytes(recommended: -1, mlxBudget: 19*gib), 0)
  }

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
