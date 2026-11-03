import BeverageCore
import Foundation
import MLX
import MLXLMCommon
import MLXVLM
import MemorySafety

func modelConfiguration(_ directory: URL) throws -> (MuseGlimmerConfiguration, BaseConfiguration) {
  let data = try Data(contentsOf: directory.appendingPathComponent("config.json"))
  return (try JSONDecoder().decode(MuseGlimmerConfiguration.self, from: data),
    try JSONDecoder().decode(BaseConfiguration.self, from: data))
}
func localProcessor(_ directory: URL, tokenizer: any MLXLMCommon.Tokenizer) throws -> MuseGlimmerProcessor {
  MuseGlimmerProcessor(try JSONDecoder().decode(MuseGlimmerProcessorConfiguration.self,
    from: Data(contentsOf: directory.appendingPathComponent("processor_config.json"))), tokenizer: tokenizer)
}
func loadLanguageContext(_ directory: URL) async throws -> ModelContext {
  let (config, base) = try modelConfiguration(directory)
  let model = try guardedMLX { error in
    let model = MuseGlimmer(config, frozenVisionFeaturesOnly: true)
    try error.check(); return model
  }
  try await guardedMLX { error in
    try await loadWeights(modelDirectory: directory, model: model, perLayerQuantization: base.perLayerQuantization)
    try error.check()
  }
  guard !model.parameters().flattened().contains(where: { $0.0.hasPrefix("vision_") }),
    !model.onDemandComponents.contains(where: { $0.isLoaded }) else { throw ContractError.invalid("language worker loaded vision") }
  let tokenizer = try await LocalTokenizerLoader().load(from: directory)
  var configuration = ModelConfiguration(directory: directory)
  configuration.eosTokenIds = base.effectiveEOSTokenIds
  if let generation = try? JSONDecoder().decode(GenerationConfigFile.self,
    from: Data(contentsOf: directory.appendingPathComponent("generation_config.json"))), let ids = generation.eosTokenIds?.values {
    configuration.eosTokenIds = Set(ids)
  }
  return ModelContext(configuration: configuration, model: model,
    processor: try localProcessor(directory, tokenizer: tokenizer), tokenizer: tokenizer)
}

func prepareFeatureCache(options: Options, modelDirectory: URL, root: URL, output: URL,
  rows: [InferenceRow], imageTokens: Int, safety: RuntimeSafety) async throws {
  let started = utcNow()
  let split = try options.required("split")
  guard !rows.isEmpty, rows.allSatisfy({ $0.split == split && $0.image_path != nil }) else { throw ContractError.invalid("vision worker requires one exact image split") }
  // Defense in depth: even the worker's raw JSON boundary accepts no gold fields.
  for line in try String(contentsOf: URL(fileURLWithPath: options.required("manifest")), encoding: .utf8).split(whereSeparator: \.isNewline) {
    guard let object = try JSONSerialization.jsonObject(with: Data(line.utf8)) as? [String: Any],
      Set(object.keys) == Set(["image_id", "image_path", "image_sha256", "split", "review_status"]) else {
      throw ContractError.invalid("vision preparation input must be label-free")
    }
  }
  let encoderConfig = try jsonObject(URL(fileURLWithPath: options.required("encoder-config")))
  let encoderHash = try canonicalHash(encoderConfig)
  guard encoderHash == (try options.required("encoder-config-sha256")), encoderConfig["execution_policy"] as? String == executionPolicy,
    encoderConfig["image_tokens"] as? Int == imageTokens,
    encoderConfig["runtime_patch_sha256"] as? String == runtimePatchSHA256,
    encoderConfig["executable_sha256"] as? String == (try fileSHA256(URL(fileURLWithPath: CommandLine.arguments[0]))) else {
    throw ContractError.invalid("encoder configuration differs from actual worker")
  }
  try writeJSON(encoderConfig, output.appendingPathComponent("encoder-config.json"))
  let (config, base) = try modelConfiguration(modelDirectory)
  let encoder = try guardedMLX { error in
    let result = MuseGlimmerFrozenVisionEncoder(config); try error.check(); return result
  }
  try await guardedMLX { error in
    try await loadWeights(modelDirectory: modelDirectory, model: encoder, perLayerQuantization: base.perLayerQuantization)
    try error.check(); encoder.freeze(); encoder.train(false)
  }
  let namespaces = Set(encoder.parameters().flattened().map { String($0.0.split(separator: ".")[0]) }).sorted()
  guard namespaces == ["vision_adapter", "vision_projection", "vision_tower"] else { throw ContractError.invalid("encoder contains unexpected weight namespaces") }
  try safety.check("vision_only_loaded"); announce("vision_only_loaded")
  let tokenizer = try await LocalTokenizerLoader().load(from: modelDirectory)
  let processor = try localProcessor(modelDirectory, tokenizer: tokenizer)
  var entries: [[String: Any]] = []
  var writes: [[String: String]] = []
  for (index, row) in rows.sorted(by: { $0.image_id < $1.image_id }).enumerated() {
    let start = Date()
    var entry: [String: Any] = ["image_id": row.image_id, "image_sha256": row.image_sha256, "split": split]
    do {
      let url = try safeImageURL(root: root, relativePath: row.image_path!)
      guard try fileSHA256(url) == row.image_sha256 else { throw ContractError.invalid("image hash mismatch") }
      var user = UserInput(prompt: recognitionPrompt, images: [.init(source: .url(url))],
        additionalContext: ["current_date": templateCurrentDate, "reasoning_strength": reasoningStrength])
      user.processing.maxPixels = imageTokens * 28 * 28
      let input = try await guardedMLX { error in
        let value = try await processor.prepare(input: user); try error.check(); return value
      }
      guard let image = input.image, let frames = image.frames else { throw ContractError.invalid("image decoder produced no pixels") }
      let features = try guardedMLX { error in
        let value = try encoder(image.pixels, grid: frames); try error.check(); eval(value); try error.check(); return value
      }
      try safety.check("vision_features_materialized")
      guard features.ndim == 2, features.dim(1) == 6656, 1...imageTokens ~= features.dim(0) else { throw ContractError.invalid("vision feature shape exceeds bound") }
      let expected = try fixedPromptTokens(tokenizer: tokenizer, featureCount: features.dim(0))
      let actual = try guardedMLX { error in
        let tokens = input.text.tokens.asArray(Int.self) + tokenizer.encode(text: generationHeader, addSpecialTokens: false)
        try error.check(); return tokens
      }
      guard actual == expected, expected.count <= imageTokens + 512 else { throw ContractError.invalid("processor differs from fixed template reconstruction") }
      let name = String(format: "features-%04d.safetensors", index)
      let tensor = output.appendingPathComponent(name)
      try guardedMLX { error in
        try MLX.save(arrays: ["vision_features": features, "prompt_tokens": MLXArray(expected.map(Int32.init))], url: tensor)
        try error.check()
      }
      let hash = try fileSHA256(tensor)
      let dtype: String
      switch features.dtype { case .bfloat16: dtype = "BF16"; case .float16: dtype = "F16"; case .float32: dtype = "F32"; default: throw ContractError.invalid("unsupported frozen feature dtype") }
      entry.merge(["outcome": "success", "error": NSNull(), "tensor_path": name, "tensor_sha256": hash,
        "feature_key": "vision_features", "feature_dtype": dtype, "feature_shape": features.shape,
        "tokens_key": "prompt_tokens", "tokens_dtype": "I32", "tokens_shape": [expected.count],
        "prompt_tokens_sha256": sha256(tokenBytes(expected)), "encoding_seconds": Date().timeIntervalSince(start)]) { _, new in new }
      writes.append(["image_id": row.image_id, "feature_sha256": hash])
    } catch let error as MLXError { throw error
    } catch let error as MemoryGuardFailure { throw error
    } catch {
      entry["outcome"] = "error"; entry["error"] = "image_decode_or_feature_validation_failed"
    }
    entries.append(entry)
    Memory.clearCache(); try safety.check("feature_case_complete"); announce("feature_case_complete")
  }
  let completed = utcNow()
  let run: [String: Any] = ["schema_version": "beverage-encoder-run-v1", "encoder_config_sha256": encoderHash,
    "vision_only": true, "language_loaded": false, "loaded_weight_namespaces": namespaces,
    "started_utc": started, "completed_utc": completed, "actual_feature_writes": writes,
    "execution_policy": executionPolicy, "memory": memoryRecord("encoder_finished")]
  let runURL = output.appendingPathComponent("encoder-run.json")
  try writeJSON(run, runURL)
  try writeJSON(["schema_version": "beverage-feature-cache-v1", "execution_policy": executionPolicy,
    "encoder_config_sha256": encoderHash, "encoder_config_path": "encoder-config.json",
    "encoder_run_path": "encoder-run.json", "encoder_run_sha256": try fileSHA256(runURL),
    "source_manifest_sha256": try options.required("source-manifest-sha256"),
    "split_policy_sha256": try options.required("split-policy-sha256"), "split": split,
    "started_utc": started, "completed_utc": utcNow(), "outcome": "complete",
    "cache_admission_selection_sha256": options.values["--cache-admission-selection-sha256"] as Any? ?? NSNull(),
    "entries": entries], output.appendingPathComponent("feature-cache.json"))
}
