import Foundation
import MLX
import MLXLMCommon
import MLXNN
import MLXOptimizers
import MLXVLM
import MemorySafety
import XCTest

final class CachedFeatureParityTests: XCTestCase {
  func testFrozenFeatureForwardUpdateAndReloadMatchDirectPixels() throws {
    try Device.withDefaultDevice(.cpu) {
      let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
        UUID().uuidString)
      try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
      defer { try? FileManager.default.removeItem(at: directory) }
      let config = try TinyMuseFixture.configuration()
      let direct = MuseGlimmer(config)
      direct.train(false)
      try MLX.save(
        arrays: Dictionary(uniqueKeysWithValues: direct.parameters().flattened()),
        url: directory.appendingPathComponent("model.safetensors"))
      let encoder = MuseGlimmerFrozenVisionEncoder(config)
      try loadWeights(modelDirectory: directory, model: encoder)
      encoder.freeze()
      encoder.train(false)
      XCTAssertEqual(
        Set(encoder.parameters().flattened().map { $0.0.split(separator: ".")[0] }),
        Set(["vision_tower", "vision_adapter", "vision_projection"]))
      let cached = MuseGlimmer(config, frozenVisionFeaturesOnly: true)
      try loadWeights(modelDirectory: directory, model: cached, excludedComponents: [.vision])
      cached.train(false)
      let adapterConfig = LoRAConfiguration(
        numLayers: 1,
        loraParameters: .init(rank: 2, scale: 4, keys: ["self_attn.q_proj", "self_attn.v_proj"]))
      let adapter = try LoRAContainer.from(model: direct, configuration: adapterConfig)
      cached.freeze()
      try cached.load(adapter: LoRAContainer(configuration: adapter.configuration,
        parameters: ModuleParameters.unflattened(Dictionary(uniqueKeysWithValues: adapter.parameters.flattened()))))
      let pixels = MLXArray.ones([4, 12])
      let grid = [THW(1, 2, 2)]
      let features = try encoder(pixels, grid: grid)
      eval(features)
      let tokens = MLXArray([1, 12, 2]).expandedDimensions(axis: 0)
      let directCache = try direct.newCache(parameters: nil)
      let cachedCache = try cached.newCache(parameters: nil)
      let prepared = try direct.prepare(
        LMInput(text: .init(tokens: tokens), image: .init(pixels: pixels, frames: grid)),
        cache: directCache, state: nil, prefill: .init(stepSize: 2))
      if case .logits(let output) = prepared { eval(output.logits, directCache) }
      let cachedPrepared = try cached.prepareWithFrozenVisionFeatures(
        tokens: tokens, features: features, cache: cachedCache, prefill: .init(stepSize: 2))
      if case .logits(let output) = cachedPrepared { eval(output.logits, cachedCache) }
      let x = MLXArray([3, 4]).expandedDimensions(axis: 0)
      let y = MLXArray([4, 5]).expandedDimensions(axis: 0)
      let directLogits = direct(x, cache: directCache.map { $0.copy() })
      let cachedLogits = cached(x, cache: cachedCache.map { $0.copy() })
      XCTAssertLessThanOrEqual(
        try checkedScalarDouble { _ in max(abs(directLogits - cachedLogits)) }, 1e-6)
      XCTAssertFalse(cached.onDemandComponents.contains { $0.isLoaded })
      XCTAssertThrowsError(
        try cached.prepare(
          LMInput(text: .init(tokens: tokens), image: .init(pixels: pixels, frames: grid)),
          cache: cached.newCache(parameters: nil), state: nil, prefill: .init(stepSize: 2)))
      let before = Dictionary(
        uniqueKeysWithValues: cached.trainableParameters().flattened().map { ($0.0, $0.1 + 0) })
      eval(Array(before.values))
      func update(_ model: MuseGlimmer, _ prefix: [any KVCache]) throws {
        let gradient = valueAndGrad(model: model) { (m: MuseGlimmer, a: MLXArray, b: MLXArray) in
          mean(crossEntropy(logits: m(a, cache: prefix.map { $0.copy() }), targets: b))
        }
        let (loss, g) = gradient(model, x, y)
        eval(loss, g)
        let optimizer = Adam(learningRate: 0.001)
        optimizer.update(model: model, gradients: g)
        eval(model.trainableParameters(), optimizer)
      }
      try update(direct, directCache)
      try update(cached, cachedCache)
      let expected = Dictionary(uniqueKeysWithValues: direct.trainableParameters().flattened())
      let actual = Dictionary(uniqueKeysWithValues: cached.trainableParameters().flattened())
      var delta = 0.0
      for (key, value) in actual {
        XCTAssertLessThanOrEqual(
          try checkedScalarDouble { _ in max(abs(value - expected[key]!)) }, 1e-6)
        delta += try checkedScalarDouble { _ in sum(square(value - before[key]!)) }
      }
      XCTAssertGreaterThan(delta, 0)
      let beforeReload = cached(x, cache: cachedCache.map { $0.copy() })
      eval(beforeReload)
      try MLX.save(arrays: actual, url: directory.appendingPathComponent("adapters.safetensors"))
      try JSONEncoder().encode(adapterConfig).write(
        to: directory.appendingPathComponent("adapter_config.json"))
      try cached.load(adapter: LoRAContainer.from(directory: directory))
      let afterReload = cached(x, cache: cachedCache.map { $0.copy() })
      XCTAssertLessThanOrEqual(
        try checkedScalarDouble { _ in max(abs(beforeReload - afterReload)) }, 1e-6)
      let changed = try encoder(MLXArray.zeros([4, 12]), grid: grid)
      XCTAssertGreaterThan(try checkedScalarDouble { _ in max(abs(changed - features)) }, 0)
    }
  }
}
