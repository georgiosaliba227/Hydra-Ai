import BeverageCore
import Darwin
import Foundation
import MLX

/// Check immediately after graph creation, before consuming a possibly invalid result.
/// GPU driver aborts and OS process termination remain outside Swift error recovery.
public func guardedMLX<R>(_ body: (ErrorBox) throws -> R) throws -> R {
  try withError(body)
}

public func guardedMLX<R>(_ body: (ErrorBox) async throws -> R) async throws -> R {
  try await withError(body)
}

public struct MemoryGuardFailure: Error, Sendable { public let kind: String }

public func currentResidentBytes() throws -> Int {
  var info = mach_task_basic_info()
  var count = mach_msg_type_number_t(
    MemoryLayout<mach_task_basic_info>.size / MemoryLayout<natural_t>.size)
  let status = withUnsafeMutablePointer(to: &info) { pointer in
    pointer.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
      task_info(mach_task_self_, task_flavor_t(MACH_TASK_BASIC_INFO), $0, &count)
    }
  }
  guard status == KERN_SUCCESS else {
    throw ContractError.invalid("resident memory measurement unavailable")
  }
  return Int(info.resident_size)
}

/// Sampled guards bound admission and stop a growing process. They do not make
/// MLX.memoryLimit a hard allocator cap; a single allocation can overshoot a sample.
public final class RuntimeSafety: @unchecked Sendable {
  private let budget: MemoryBudget
  private let output: URL
  private let lock = NSLock()
  private let queue = DispatchQueue(label: "hydra.beverage.memory-watchdog")
  private var timer: DispatchSourceTimer?
  private var phase = "starting"
  private var failureWritten = false

  public init(mlxBytes: Int, residentBytes: Int, output: URL) {
    self.budget = MemoryBudget(mlxBytes: mlxBytes, residentBytes: residentBytes)
    self.output = output
  }
  private func snapshot() throws -> (Int, Int, Int) {
    (Memory.activeMemory, Memory.cacheMemory, try currentResidentBytes())
  }
  private func failure(_ kind: String, phase: String, sample: (Int, Int, Int)?) {
    let shouldWrite = lock.withLock {
      if failureWritten { return false }
      failureWritten = true
      return true
    }
    guard shouldWrite else { return }
    var record: [String: Any] = [
      "schema_version": "beverage-runtime-failure-v1", "kind": kind,
      "phase": phase, "mlx_budget_bytes": budget.mlxBytes, "rss_budget_bytes": budget.residentBytes,
      "sample_interval_ms": 50,
      "guard_limit": "sampled guard; allocations may overshoot between observations",
    ]
    if let (active, cache, rss) = sample {
      record["mlx_active_bytes"] = active
      record["mlx_cache_bytes"] = cache
      record["resident_bytes"] = rss
    }
    if let data = try? JSONSerialization.data(
      withJSONObject: record, options: [.sortedKeys, .prettyPrinted])
    {
      try? data.write(to: output.appendingPathComponent("failure.json"), options: .atomic)
      FileHandle.standardError.write(data + Data([10]))
    }
  }
  public func check(_ newPhase: String) throws {
    lock.withLock { phase = newPhase }
    do {
      let sample = try snapshot()
      if let kind = budget.violation(mlxActive: sample.0, mlxCache: sample.1, resident: sample.2) {
        failure(kind, phase: newPhase, sample: sample)
        throw MemoryGuardFailure(kind: kind)
      }
    } catch {
      failure("memory_measurement_or_budget_failed", phase: newPhase, sample: nil)
      if let guardFailure = error as? MemoryGuardFailure { throw guardFailure }
      throw MemoryGuardFailure(kind: "memory_measurement_unavailable")
    }
  }
  public func start() throws {
    try check("watchdog_start")
    let source = DispatchSource.makeTimerSource(queue: queue)
    source.schedule(deadline: .now(), repeating: .milliseconds(50), leeway: .milliseconds(5))
    source.setEventHandler { [weak self] in
      guard let self else { return }
      let phase = self.lock.withLock { self.phase }
      do {
        let sample = try self.snapshot()
        if let kind = self.budget.violation(
          mlxActive: sample.0, mlxCache: sample.1, resident: sample.2)
        {
          self.failure(kind, phase: phase, sample: sample)
          _exit(86)
        }
      } catch {
        self.failure("memory_measurement_unavailable", phase: phase, sample: nil)
        _exit(87)
      }
    }
    timer = source
    source.resume()
  }
  public func recordFailure(_ kind: String) {
    failure(kind, phase: lock.withLock { phase }, sample: try? snapshot())
  }
  public func stop() {
    timer?.cancel()
    queue.sync {}
    timer = nil
  }
}

/// Evaluate a diagnostic reduction before converting its scalar value.
public func checkedScalarDouble(_ body: (ErrorBox) throws -> MLXArray) throws -> Double {
  try guardedMLX { error in
    let value = try body(error)
    try error.check()
    let size = value.size
    try error.check()
    guard size == 1 else { throw ContractError.invalid("expected scalar diagnostic") }
    // BF16 -> Double via MLXArray.item can create an unsupported Float64 GPU
    // conversion. Read Float32 on device, then widen the copied Swift value.
    let readable = value.asType(.float32)
    try error.check()
    eval(readable)
    try error.check()
    let scalar = readable.item(Float.self)
    try error.check()
    return Double(scalar)
  }
}
