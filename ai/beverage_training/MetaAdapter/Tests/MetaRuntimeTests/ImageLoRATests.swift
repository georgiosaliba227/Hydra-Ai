import Foundation
import MLX
import MLXLMCommon
import MLXNN
import MLXOptimizers
import MLXVLM
import XCTest

/// A small random Muse architecture verifies our API use and visual conditioning.
/// This fixture is never evidence of the real 30B checkpoint fitting or accuracy.
final class ImageLoRATests: XCTestCase {
  func testImagePrefixChangesLogitsAndLoRAUpdatesThenReloads() throws {
    try Device.withDefaultDevice(.cpu) {
      let configJSON =
        #"{"model_type":"muse_glimmer","image_token_id":12,"video_token_id":13,"out_hidden_size":32,"projector_hidden_size":8,"text_config":{"vocab_size":32,"hidden_size":8,"intermediate_size":16,"num_hidden_layers":2,"num_attention_heads":2,"num_key_value_heads":1,"head_dim":4,"sliding_window":32},"vision_config":{"hidden_size":8,"intermediate_size":16,"num_hidden_layers":1,"num_attention_heads":2,"patch_size":2,"patch_temporal":1,"merge_size":2,"pos_emb_height":2,"pos_emb_width":2}}"#
      let config = try JSONDecoder().decode(
        MuseGlimmerConfiguration.self, from: Data(configJSON.utf8))
      let model = MuseGlimmer(config)
      model.train(false)
      let adapterConfig = LoRAConfiguration(
        numLayers: 1,
        loraParameters: .init(rank: 2, scale: 4, keys: ["self_attn.q_proj", "self_attn.v_proj"]))
      _ = try LoRAContainer.from(model: model, configuration: adapterConfig)
      func prefix(_ pixels: MLXArray) throws -> [any KVCache] {
        let cache = try model.newCache(parameters: nil)
        let input = LMInput(
          text: .init(tokens: MLXArray([1, 12, 2]).expandedDimensions(axis: 0)),
          image: .init(pixels: pixels, frames: [THW(1, 2, 2)]))
        if case .logits(let output) = try model.prepare(
          input, cache: cache, state: nil, prefill: .init(stepSize: 2))
        {
          eval(output.logits, cache)
        }
        for var item in cache { item.state = item.state.map { stopGradient($0) } }
        return cache
      }
      let first = try prefix(MLXArray.zeros([4, 12]))
      let second = try prefix(MLXArray.ones([4, 12]))
      let tokens = MLXArray([3, 4]).expandedDimensions(axis: 0)
      let targets = MLXArray([4, 5]).expandedDimensions(axis: 0)
      let a = model(tokens, cache: first.map { $0.copy() })
      let b = model(tokens, cache: second.map { $0.copy() })
      XCTAssertGreaterThan(max(abs(a - b)).item(Float.self), 0)
      let before = Dictionary(
        uniqueKeysWithValues: model.trainableParameters().flattened().map { ($0.0, $0.1 + 0) })
      eval(Array(before.values))
      let vg = valueAndGrad(model: model) { (m: MuseGlimmer, x: MLXArray, y: MLXArray) in
        mean(crossEntropy(logits: m(x, cache: first.map { $0.copy() }), targets: y))
      }
      let (loss, gradients) = vg(model, tokens, targets)
      XCTAssertTrue(loss.item(Float.self).isFinite)
      let optimizer = Adam(learningRate: 0.001)
      optimizer.update(model: model, gradients: gradients)
      eval(model.trainableParameters(), optimizer)
      let updated = Dictionary(uniqueKeysWithValues: model.trainableParameters().flattened())
      let delta = updated.reduce(Float(0)) {
        $0 + sum(square($1.value - before[$1.key]!)).item(Float.self)
      }
      XCTAssertGreaterThan(delta, 0)
      let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
        UUID().uuidString)
      try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
      defer { try? FileManager.default.removeItem(at: directory) }
      try MLX.save(arrays: updated, url: directory.appendingPathComponent("adapters.safetensors"))
      try JSONEncoder().encode(adapterConfig).write(
        to: directory.appendingPathComponent("adapter_config.json"))
      let savedLogits = model(tokens, cache: first.map { $0.copy() })
      eval(savedLogits)
      let restored = try LoRAContainer.from(directory: directory)
      try model.load(adapter: restored)
      let restoredLogits = model(tokens, cache: first.map { $0.copy() })
      eval(restoredLogits)
      XCTAssertLessThanOrEqual(max(abs(savedLogits - restoredLogits)).item(Float.self), 1e-6)
    }
  }
}
