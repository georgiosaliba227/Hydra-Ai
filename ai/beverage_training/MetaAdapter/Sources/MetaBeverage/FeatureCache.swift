import BeverageCore
import Foundation
import MLX
import MLXLMCommon
import MLXVLM
import MemorySafety

func utcNow() -> String { ISO8601DateFormatter().string(from: Date()) }
func canonicalHash(_ object: [String: Any]) throws -> String {
  sha256(try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys, .withoutEscapingSlashes]))
}
func jsonObject(_ url: URL) throws -> [String: Any] {
  guard let value = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any] else {
    throw ContractError.invalid("invalid cache JSON object")
  }
  return value
}
func safeCacheURL(root: URL, relative: String) throws -> URL {
  guard !relative.isEmpty, !relative.hasPrefix("/"), !relative.split(separator: "/").contains("..") else {
    throw ContractError.invalid("cache path escapes root")
  }
  let result = root.appendingPathComponent(relative).standardizedFileURL
  var current = result
  while current.path != "/" {
    if (try current.resourceValues(forKeys: [.isSymbolicLinkKey])).isSymbolicLink == true {
      throw ContractError.invalid("cache symlinks or symlink ancestors are forbidden")
    }
    current.deleteLastPathComponent()
  }
  guard result.path.hasPrefix(root.standardizedFileURL.path + "/"),
    (try result.resourceValues(forKeys: [.isRegularFileKey])).isRegularFile == true else {
    throw ContractError.invalid("invalid cache artifact path")
  }
  return result
}
func fixedPromptTokens(tokenizer: any MLXLMCommon.Tokenizer, featureCount: Int) throws -> [Int] {
  // Message generation only renders a media placeholder. It never reads this URL.
  let input = UserInput(prompt: recognitionPrompt,
    images: [.init(source: .url(URL(fileURLWithPath: "/hydra-fixed-image-placeholder")))],
    additionalContext: ["current_date": templateCurrentDate, "reasoning_strength": reasoningStrength])
  let messages = Qwen2VLMessageGenerator().generate(from: input)
  let base = try tokenizer.applyChatTemplate(messages: messages, tools: nil, additionalContext: input.additionalContext)
  let patch = tokenizer.convertTokenToId("<|patch|>") ?? 200092
  let start = tokenizer.convertTokenToId("<|image_start|>") ?? 200080
  let end = tokenizer.convertTokenToId("<|image_end|>") ?? 200081
  guard base.filter({ $0 == patch }).count == 1 else { throw ContractError.invalid("fixed image template mismatch") }
  return base.flatMap { $0 == patch ? [start] + Array(repeating: patch, count: featureCount) + [end] : [$0] }
    + tokenizer.encode(text: generationHeader, addSpecialTokens: false)
}
func tokenBytes(_ tokens: [Int]) -> Data {
  var result = Data()
  for token in tokens { var value = Int32(token).littleEndian; withUnsafeBytes(of: &value) { result.append(contentsOf: $0) } }
  return result
}

final class FeatureCache {
  let root: URL
  let descriptor: [String: Any]
  let config: [String: Any]
  let entries: [String: [String: Any]]
  let path: URL
  let descriptorHash: String
  let encoderHash: String
  var uses: [String: String] = [:]
  init(options: Options, rows: [InferenceRow], split: String, imageTokens: Int) throws {
    path = URL(fileURLWithPath: try options.required("feature-cache"))
    root = path.deletingLastPathComponent()
    _ = try safeCacheURL(root: root, relative: path.lastPathComponent)
    descriptorHash = try fileSHA256(path)
    guard descriptorHash == (try options.required("feature-cache-sha256")) else { throw ContractError.invalid("cache descriptor changed") }
    descriptor = try jsonObject(path)
    encoderHash = try options.required("encoder-config-sha256")
    guard descriptor["schema_version"] as? String == "beverage-feature-cache-v1",
      descriptor["execution_policy"] as? String == executionPolicy,
      descriptor["encoder_config_sha256"] as? String == encoderHash,
      descriptor["source_manifest_sha256"] as? String == (try options.required("source-manifest-sha256")),
      descriptor["split_policy_sha256"] as? String == (try options.required("split-policy-sha256")),
      descriptor["split"] as? String == split, descriptor["outcome"] as? String == "complete",
      let configPath = descriptor["encoder_config_path"] as? String,
      let raw = descriptor["entries"] as? [[String: Any]] else { throw ContractError.invalid("cache frozen input binding mismatch") }
    config = try jsonObject(safeCacheURL(root: root, relative: configPath))
    guard try canonicalHash(config) == encoderHash,
      config["execution_policy"] as? String == executionPolicy,
      config["model_id"] as? String == baseModelID,
      config["base_revision"] as? String == baseRevision,
      config["runtime_revision"] as? String == runtimeRevision,
      config["runtime_patch_sha256"] as? String == runtimePatchSHA256,
      config["executable_sha256"] as? String == (try fileSHA256(URL(fileURLWithPath: CommandLine.arguments[0]))),
      config["model_provenance_sha256"] as? String == (try options.required("model-provenance-sha256")),
      config["prompt_sha256"] as? String == sha256(Data(recognitionPrompt.utf8)),
      config["image_tokens"] as? Int == imageTokens else { throw ContractError.invalid("cache encoder configuration mismatch") }
    var keyed: [String: [String: Any]] = [:]
    for entry in raw {
      guard let id = entry["image_id"] as? String, keyed[id] == nil else { throw ContractError.invalid("duplicate cache ID") }
      keyed[id] = entry
    }
    let expected = rows.filter { $0.split == split }
    guard Set(keyed.keys) == Set(expected.map(\.image_id)), expected.allSatisfy({ keyed[$0.image_id]?["image_sha256"] as? String == $0.image_sha256 && keyed[$0.image_id]?["split"] as? String == split }) else {
      throw ContractError.invalid("cache does not cover exact worker split")
    }
    entries = keyed
  }
  func load(_ row: InferenceRow, tokenizer: any MLXLMCommon.Tokenizer) throws -> (MLXArray, [Int]) {
    guard let entry = entries[row.image_id], entry["outcome"] as? String == "success",
      let relative = entry["tensor_path"] as? String, let hash = entry["tensor_sha256"] as? String,
      let shape = entry["feature_shape"] as? [Int], shape.count == 2, shape[1] == 6656,
      1...(config["image_tokens"] as? Int ?? 0) ~= shape[0],
      let tokensShape = entry["tokens_shape"] as? [Int], tokensShape.count == 1 else {
      throw ContractError.invalid("cache case unavailable")
    }
    let url = try safeCacheURL(root: root, relative: relative)
    let data = try Data(contentsOf: url)
    guard data.count >= 10, data.count <= 32 * 1024 * 1024, sha256(data) == hash else { throw ContractError.invalid("cache tensor hash/size mismatch") }
    let headerSize = data.prefix(8).enumerated().reduce(UInt64(0)) { $0 | (UInt64($1.element) << (8 * $1.offset)) }
    guard headerSize <= 1024 * 1024, headerSize >= 2, headerSize <= data.count - 8,
      let header = try JSONSerialization.jsonObject(with: data.subdata(in: 8..<(8 + Int(headerSize)))) as? [String: Any],
      Set(header.keys.filter { $0 != "__metadata__" }) == Set(["vision_features", "prompt_tokens"]),
      let feature = header["vision_features"] as? [String: Any], let token = header["prompt_tokens"] as? [String: Any],
      feature["shape"] as? [Int] == shape, token["shape"] as? [Int] == tokensShape,
      feature["dtype"] as? String == entry["feature_dtype"] as? String,
      ["BF16", "F16", "F32"].contains(feature["dtype"] as? String ?? ""), token["dtype"] as? String == "I32",
      let f = feature["data_offsets"] as? [Int], f.count == 2,
      let t = token["data_offsets"] as? [Int], t.count == 2 else { throw ContractError.invalid("cache safetensors header mismatch") }
    let payloadSize = data.count - 8 - Int(headerSize)
    let bytesPerFeature = feature["dtype"] as? String == "F32" ? 4 : 2
    let ranges = [f, t].sorted { $0[0] < $1[0] }
    guard f[0] >= 0, t[0] >= 0, f[1] - f[0] == shape[0] * shape[1] * bytesPerFeature,
      t[1] - t[0] == tokensShape[0] * 4, tokensShape[0] <= (config["image_tokens"] as? Int ?? 0) + 512,
      ranges[0][0] == 0, ranges[0][1] == ranges[1][0], ranges[1][1] == payloadSize else { throw ContractError.invalid("cache tensor offsets invalid") }
    let expectedTokens = try fixedPromptTokens(tokenizer: tokenizer, featureCount: shape[0])
    let rawTokens = data.subdata(in: (8 + Int(headerSize) + t[0])..<(8 + Int(headerSize) + t[1]))
    guard rawTokens == tokenBytes(expectedTokens), sha256(rawTokens) == entry["prompt_tokens_sha256"] as? String else { throw ContractError.invalid("cache tokens differ from fixed prompt") }
    let features = try guardedMLX { error in
      let arrays = try MLX.loadArrays(url: url)
      try error.check()
      guard let features = arrays["vision_features"], features.shape == shape else { throw ContractError.invalid("invalid cached feature array") }
      eval(features); try error.check(); return features
    }
    uses[row.image_id] = hash
    return (features, expectedTokens)
  }
  var actualUses: [[String: String]] { uses.keys.sorted().map { ["image_id": $0, "feature_sha256": uses[$0]!] } }
}
