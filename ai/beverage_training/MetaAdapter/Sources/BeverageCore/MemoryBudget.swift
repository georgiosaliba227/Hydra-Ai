public struct MemoryBudget: Sendable {
  /// Process-local GPU residency; never raises the device/OS recommendation.
  public static func gpuResidencyBytes(recommended: Int, mlxBudget: Int) -> Int {
    max(0, min(16 * 1024 * 1024 * 1024, recommended, mlxBudget))
  }

  public let mlxBytes: Int
  public let residentBytes: Int
  public init(mlxBytes: Int, residentBytes: Int) {
    self.mlxBytes = mlxBytes
    self.residentBytes = residentBytes
  }
  public func violation(mlxActive: Int, mlxCache: Int, resident: Int) -> String? {
    guard mlxActive >= 0, mlxCache >= 0, resident > 0 else { return "memory_measurement_invalid" }
    if mlxActive > mlxBytes || mlxCache > mlxBytes - mlxActive { return "mlx_budget_exceeded" }
    if resident > residentBytes { return "rss_budget_exceeded" }
    return nil
  }
}
