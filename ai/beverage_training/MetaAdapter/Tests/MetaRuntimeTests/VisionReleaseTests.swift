import Foundation
import MLX
import MLXLMCommon
import MLXVLM
import MemorySafety
import XCTest

final class VisionReleaseTests: XCTestCase {
  func testOnDemandVisionReleaseReloadPreservesPixelsAndLogits() throws {
    try Device.withDefaultDevice(.cpu) {
      let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
        UUID().uuidString)
      try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
      defer { try? FileManager.default.removeItem(at: directory) }
      let model = MuseGlimmer(try TinyMuseFixture.configuration())
      model.train(false)
      try guardedMLX { error in
        try MLX.save(
          arrays: Dictionary(uniqueKeysWithValues: model.parameters().flattened()),
          url: directory.appendingPathComponent("model.safetensors"))
        try error.check()
        try loadWeights(modelDirectory: directory, model: model, componentLoading: .onFirstUse)
        try error.check()
      }
      let holder = try XCTUnwrap(model.onDemandComponents.first)
      XCTAssertFalse(holder.isLoaded)
      func prefill(_ pixels: MLXArray) throws -> MLXArray {
        try guardedMLX { error in
          let input = LMInput(
            text: .init(tokens: MLXArray([1, 12, 2]).expandedDimensions(axis: 0)),
            image: .init(pixels: pixels, frames: [THW(1, 2, 2)]))
          try error.check()
          let result = try model.prepare(
            input, cache: model.newCache(parameters: nil), state: nil, prefill: .init(stepSize: 2))
          try error.check()
          guard case .logits(let output) = result else { throw CocoaError(.coderInvalidValue) }
          eval(output.logits)
          try error.check()
          return output.logits
        }
      }
      // Default behavior retains vision and provides a numerical control.
      let control = try prefill(MLXArray.zeros([4, 12]))
      XCTAssertTrue(holder.isLoaded)
      model.releaseFrozenVisionAfterEmbedding = true
      let released = try prefill(MLXArray.zeros([4, 12]))
      XCTAssertFalse(holder.isLoaded)
      XCTAssertFalse(holder.releaseLoaded())
      XCTAssertLessThanOrEqual(try checkedScalarDouble { _ in max(abs(control - released)) }, 1e-6)
      // A second image forces a reload from the original source, then releases again.
      let different = try prefill(MLXArray.ones([4, 12]))
      XCTAssertFalse(holder.isLoaded)
      XCTAssertGreaterThan(try checkedScalarDouble { _ in max(abs(different - control)) }, 0)
      let repeated = try prefill(MLXArray.zeros([4, 12]))
      XCTAssertFalse(holder.isLoaded)
      XCTAssertLessThanOrEqual(try checkedScalarDouble { _ in max(abs(repeated - control)) }, 1e-6)
    }
  }

  func testAttachedVisionRejectsOptInInsteadOfPretendingToRelease() throws {
    try Device.withDefaultDevice(.cpu) {
      let model = MuseGlimmer(try TinyMuseFixture.configuration())
      model.releaseFrozenVisionAfterEmbedding = true
      let input = LMInput(
        text: .init(tokens: MLXArray([1, 12, 2]).expandedDimensions(axis: 0)),
        image: .init(pixels: MLXArray.zeros([4, 12]), frames: [THW(1, 2, 2)]))
      XCTAssertThrowsError(
        try model.prepare(
          input, cache: model.newCache(parameters: nil), state: nil, prefill: .init(stepSize: 2)))
    }
  }
}
