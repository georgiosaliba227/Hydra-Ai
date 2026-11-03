import Foundation
import MLX
import MemorySafety
import XCTest

final class MemoryFailureTests: XCTestCase {
  func testBackendErrorThrowsBeforeInvalidArrayIsConsumed() throws {
    try Device.withDefaultDevice(.cpu) {
      XCTAssertThrowsError(
        try guardedMLX { error in
          let invalid = matmul(MLXArray.ones([2, 3]), MLXArray.ones([4, 2]))
          try error.check()
          eval(invalid)
          return invalid
        })
    }
  }
  func testScalarDiagnosticsRejectBackendErrorsAndNonScalarArrays() throws {
    try Device.withDefaultDevice(.cpu) {
      XCTAssertEqual(try checkedScalarDouble { _ in MLXArray(Float(2.5)) }, 2.5)
      XCTAssertThrowsError(
        try checkedScalarDouble { _ in
          matmul(MLXArray.ones([2, 3]), MLXArray.ones([4, 2]))
        })
      XCTAssertThrowsError(try checkedScalarDouble { _ in MLXArray.ones([2, 2]) })
    }
  }

  func testBFloat16DiagnosticOnGPUAvoidsFloat64Conversion() throws {
    try Device.withDefaultDevice(.gpu) {
      XCTAssertEqual(try checkedScalarDouble { _ in MLXArray(Float(2.5)).asType(.bfloat16) }, 2.5)
    }
  }

  func testResidentMeasurementAndPhaseGuardProduceFailureArtifact() throws {
    XCTAssertGreaterThan(try currentResidentBytes(), 0)
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    let guardrail = RuntimeSafety(mlxBytes: Int.max, residentBytes: 1, output: directory)
    XCTAssertThrowsError(try guardrail.check("test_phase"))
    let object =
      try JSONSerialization.jsonObject(
        with: Data(contentsOf: directory.appendingPathComponent("failure.json"))) as! [String: Any]
    XCTAssertEqual(object["kind"] as? String, "rss_budget_exceeded")
    XCTAssertEqual(object["phase"] as? String, "test_phase")
  }
}
