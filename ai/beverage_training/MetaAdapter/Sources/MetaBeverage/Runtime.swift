import BeverageCore
import Darwin
import Foundation
import MLX
import MLXLMCommon
import MLXNN
import MLXOptimizers
import MLXVLM
import MemorySafety

struct Options {
  let command: String
  var values: [String: String] = [:]
  init(_ args: [String]) throws {
    guard let command = args.first, ["smoke", "train", "infer", "info"].contains(command) else {
      throw ContractError.invalid(
        "usage: meta-beverage smoke|train|infer|info --model DIR --data-root DIR --manifest JSONL --output NEW_DIR [bounds]"
      )
    }
    self.command = command
    var i = 1
    while i < args.count {
      guard args[i].hasPrefix("--"), i + 1 < args.count, values[args[i]] == nil else {
        throw ContractError.invalid("invalid or repeated argument")
      }
      values[args[i]] = args[i + 1]
      i += 2
    }
  }
  func required(_ key: String) throws -> String {
    guard let value = values["--" + key], !value.isEmpty else {
      throw ContractError.invalid("missing --" + key)
    }
    return value
  }
  func integer(_ key: String, _ fallback: Int, range: ClosedRange<Int>) throws -> Int {
    let raw = values["--" + key] ?? String(fallback)
    guard let value = Int(raw), range.contains(value) else {
      throw ContractError.invalid("invalid bound --" + key)
    }
    return value
  }
}

func writeJSON(_ object: [String: Any], _ url: URL) throws {
  let data = try JSONSerialization.data(
    withJSONObject: object, options: [.sortedKeys, .prettyPrinted, .withoutEscapingSlashes])
  try data.write(to: url, options: .atomic)
}
func memoryRecord(_ phase: String) -> [String: Any] {
  var usage = rusage()
  getrusage(RUSAGE_SELF, &usage)
  return [
    "phase": phase, "mlx_active_bytes": Memory.activeMemory, "mlx_cache_bytes": Memory.cacheMemory,
    "mlx_peak_bytes": Memory.peakMemory, "process_peak_rss_bytes": usage.ru_maxrss,
    "resident_bytes": (try? currentResidentBytes()) ?? -1,
  ]
}
func announce(_ phase: String) {
  let data = try? JSONSerialization.data(
    withJSONObject: memoryRecord(phase), options: [.sortedKeys])
  if let data { FileHandle.standardError.write(data + Data([10])) }
}

/// A process-local lock prevents overlapping model jobs; never affects provider ledgers.
func acquireRuntimeLock() throws -> Int32 {
  let fd = open(
    "/private/tmp/hydra-meta-beverage-runtime.lock", O_CREAT | O_RDWR | O_NOFOLLOW | O_CLOEXEC,
    S_IRUSR | S_IWUSR)
  guard fd >= 0, flock(fd, LOCK_EX | LOCK_NB) == 0 else {
    throw ContractError.invalid("another local Meta training/inference job is running")
  }
  return fd
}

struct ImageRunner {
  let context: ModelContext
  let model: MuseGlimmer
  let root: URL
  let imageTokens: Int
  let prefillStep: Int
  let maxOutput: Int
  let safety: RuntimeSafety

  func input(_ row: InferenceRow) async throws -> LMInput {
    try safety.check("image_preprocess_before")
    let imageURL = try safeImageURL(root: root, relativePath: row.image_path)
    guard try fileSHA256(imageURL) == row.image_sha256 else {
      throw ContractError.invalid("image hash mismatch")
    }
    var user = UserInput(
      prompt: recognitionPrompt, images: [.init(source: .url(imageURL))],
      additionalContext: [
        "current_date": templateCurrentDate, "reasoning_strength": reasoningStrength,
      ])
    // Muse uses 14px patches merged 2x2, hence each language image token = 28x28 pixels.
    user.processing.maxPixels = imageTokens * 28 * 28
    let input = try await guardedMLX { error in
      let result = try await context.processor.prepare(input: user)
      try error.check()
      return result
    }
    try safety.check("image_preprocessed")
    guard input.image != nil, input.text.tokens.size <= imageTokens + 512 else {
      throw ContractError.invalid("image/prompt token budget exceeded")
    }
    // The released ATEM template ends at '<|start|>assistant'. Fix the
    // recipient to user so bounded decoding begins with the JSON answer,
    // rather than consuming its budget generating a private reasoning header.
    let header = context.tokenizer.encode(text: generationHeader, addSpecialTokens: false)
    return try guardedMLX { error in
      let tokens = input.text.tokens.asArray(Int.self) + header
      try error.check()
      let array = MLXArray(tokens).expandedDimensions(axis: 0)
      try error.check()
      return LMInput(text: .init(tokens: array), image: input.image)
    }
  }

  func infer(_ row: InferenceRow) async throws -> BeverageAnswer {
    let input = try await input(row)
    let cache = try guardedMLX { error in
      let value = try model.newCache(parameters: nil)
      try error.check()
      return value
    }
    var logits: MLXArray
    try safety.check("image_inference_prefill")
    let prepared = try guardedMLX { error in
      let result = try model.prepare(
        input, cache: cache, state: nil, prefill: .init(stepSize: prefillStep))
      try error.check()
      if case .logits(let output) = result { eval(output.logits, cache) }
      try error.check()
      return result
    }
    switch prepared {
    case .logits(let output): logits = output.logits
    case .tokens: throw ContractError.invalid("unexpected Muse prefill result")
    }
    try safety.check("decode_ready")
    var generated: [Int] = []
    let eos = context.configuration.eosTokenIds
    for _ in 0..<maxOutput {
      let token = try guardedMLX { error in
        let selected = argMax(logits[0, -1, 0...], axis: -1)
        try error.check()
        eval(selected)
        try error.check()
        return selected.item(Int.self)
      }
      if eos.contains(token) || token == context.tokenizer.eosTokenId { break }
      generated.append(token)
      let text = context.tokenizer.decode(tokenIds: generated, skipSpecialTokens: true)
      if let answer = try? BeverageAnswer.parse(text) { return answer }
      logits = try guardedMLX { error in
        let next = model(MLXArray([token]).expandedDimensions(axis: 0), cache: cache)
        try error.check()
        eval(next, cache)
        try error.check()
        return next
      }
      try safety.check("inference_decode")
    }
    return try BeverageAnswer.parse(
      context.tokenizer.decode(tokenIds: generated, skipSpecialTokens: true))
  }

  /// Frozen, image-conditioned prefix. No image/prompt positions contribute loss.
  /// The detached cache approximation omits gradients THROUGH prefix KV values;
  /// adapters still receive visual evidence by attending to that cache.
  func prefix(_ row: InferenceRow, label: TrainingLabel, maxAnswer: Int) async throws -> (
    [any KVCache], TeacherForcing
  ) {
    let input = try await input(row)
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
    let answerJSON = String(decoding: try encoder.encode(label.answer), as: UTF8.self)
    _ = try BeverageAnswer.parse(answerJSON)
    var answer = context.tokenizer.encode(text: answerJSON, addSpecialTokens: false)
    if let eos = context.tokenizer.convertTokenToId("<|eot|>") ?? context.tokenizer.eosTokenId {
      answer.append(eos)
    }
    let promptTokens = try guardedMLX { error in
      let value = input.text.tokens.asArray(Int.self)
      try error.check()
      return value
    }
    let sequence = try TeacherForcing(
      prompt: promptTokens, answer: answer, maxAnswerTokens: maxAnswer)
    let prefixInput = try guardedMLX { error in
      let array = MLXArray(sequence.prefix).expandedDimensions(axis: 0)
      try error.check()
      return LMInput(text: .init(tokens: array), image: input.image)
    }
    let cache = try guardedMLX { error in
      let value = try model.newCache(parameters: nil)
      try error.check()
      return value
    }
    try safety.check("image_prefix_prefill")
    let prepared = try guardedMLX { error in
      let result = try model.prepare(
        prefixInput, cache: cache, state: nil, prefill: .init(stepSize: prefillStep))
      try error.check()
      if case .logits(let output) = result { eval(output.logits, cache) }
      try error.check()
      return result
    }
    switch prepared {
    case .logits: break
    case .tokens: throw ContractError.invalid("unexpected Muse prefill result")
    }
    // Force values now, outside the valueAndGrad trace; no reused image cache across samples.
    try guardedMLX { error in
      for var item in cache {
        item.state = item.state.map { stopGradient($0) }
        eval(item)
        try error.check()
      }
    }
    Memory.clearCache()
    try safety.check("image_prefix_ready")
    return (cache, sequence)
  }
}

func run() async throws {
  try await guardedMLX { error in
    try await runModelJob()
    try error.check()
  }
}

func runModelJob() async throws {
  let options = try Options(Array(CommandLine.arguments.dropFirst()))
  if options.command == "info" {
    print(
      String(
        decoding: try JSONSerialization.data(
          withJSONObject: [
            "model_id": baseModelID, "base_revision": baseRevision,
            "runtime_revision": runtimeRevision,
            "prompt_sha256": sha256(Data(recognitionPrompt.utf8)), "prompt": recognitionPrompt,
            "generation_header": generationHeader, "template_current_date": templateCurrentDate,
            "reasoning_strength": reasoningStrength,
            "executable_sha256": try fileSHA256(URL(fileURLWithPath: CommandLine.arguments[0])),
          ], options: [.sortedKeys]), as: UTF8.self))
    return
  }
  let lock = try acquireRuntimeLock()
  defer { close(lock) }
  let modelDirectory = URL(fileURLWithPath: try options.required("model"))
  guard
    try fileSHA256(modelDirectory.appendingPathComponent("base-provenance.json"))
      == options.required("model-provenance-sha256")
  else {
    throw ContractError.invalid("base provenance fingerprint mismatch")
  }
  let root = URL(fileURLWithPath: try options.required("data-root"))
  let manifestURL = URL(fileURLWithPath: try options.required("manifest"))
  let output = URL(fileURLWithPath: try options.required("output"))
  guard !FileManager.default.fileExists(atPath: output.path) else {
    throw ContractError.invalid("output directory already exists; preserve prior artifacts")
  }
  let imageTokens = try options.integer("image-tokens", 128, range: 16...512)
  let prefillStep = try options.integer("prefill-step", 32, range: 1...128)
  let maxAnswer = try options.integer("max-answer-tokens", 96, range: 16...192)
  let maxOutput = try options.integer("max-output-tokens", 96, range: 16...192)
  let memoryGiB = try options.integer("memory-limit-gb", 19, range: 16...19)
  let rssGiB = try options.integer("rss-limit-gb", 20, range: 1...20)
  Memory.memoryLimit = memoryGiB * 1024 * 1024 * 1024
  Memory.cacheLimit = 64 * 1024 * 1024
  MLXRandom.seed(42)
  let lines = try String(contentsOf: manifestURL, encoding: .utf8).split(
    whereSeparator: \.isNewline
  ).map { Data($0.utf8) }
  let decoder = JSONDecoder()
  let rows = try lines.map { try decoder.decode(InferenceRow.self, from: $0) }
  guard Set(rows.map(\.image_id)).count == rows.count,
    rows.allSatisfy({
      $0.review_status == "reviewed" && ["train", "validation", "test"].contains($0.split)
    })
  else {
    throw ContractError.invalid("unreviewed, duplicate or invalid split rows")
  }
  try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
  try Data(recognitionPrompt.utf8).write(
    to: output.appendingPathComponent("prompt.txt"), options: .atomic)
  let safety = RuntimeSafety(
    mlxBytes: memoryGiB * 1024 * 1024 * 1024, residentBytes: rssGiB * 1024 * 1024 * 1024,
    output: output)
  do {
    try safety.start()
    defer { safety.stop() }
    try safety.check("before_load")
    announce("before_load")
    let context = try await guardedMLX { error in
      let result = try await VLMModelFactory.shared.load(
        from: modelDirectory, using: LocalTokenizerLoader())
      try error.check()
      return result
    }
    try safety.check("base_loaded")
    guard let model = context.model as? MuseGlimmer else {
      throw ContractError.invalid("local checkpoint is not Muse Glimmer")
    }
    let runner = ImageRunner(
      context: context, model: model, root: root, imageTokens: imageTokens,
      prefillStep: prefillStep, maxOutput: maxOutput, safety: safety)
    announce("base_loaded")
    var settings: [String: Any] = [
      "base_revision": baseRevision, "runtime_revision": runtimeRevision, "model_id": baseModelID,
      "image_tokens": imageTokens, "prefill_step": prefillStep, "max_answer_tokens": maxAnswer,
      "max_output_tokens": maxOutput, "memory_limit_bytes": Memory.memoryLimit,
      "rss_limit_bytes": rssGiB * 1024 * 1024 * 1024,
      "memory_guard":
        "sampled 50ms MLX/RSS plus independent launcher RSS; advisory MLX allocator limit",
      "seed": 42, "generation_header": generationHeader,
      "template_current_date": templateCurrentDate, "reasoning_strength": reasoningStrength,
      "prompt_sha256": sha256(Data(recognitionPrompt.utf8)),
      "executable_sha256": try fileSHA256(URL(fileURLWithPath: CommandLine.arguments[0])),
      "model_provenance_sha256": try options.required("model-provenance-sha256"),
      "adapter_config_sha256": NSNull(), "decoding": "greedy",
    ]
    if options.command == "infer" {
      var adapterHash: String?
      if let path = options.values["--adapter"] {
        let directory = URL(fileURLWithPath: path)
        let adapter = try guardedMLX { error in
          let value = try LoRAContainer.from(directory: directory)
          try error.check()
          return value
        }
        try guardedMLX { error in
          model.freeze()
          try model.load(adapter: adapter)
          try error.check()
          model.train(false)
        }
        adapterHash = try fileSHA256(directory.appendingPathComponent("adapters.safetensors"))
        settings["adapter_config_sha256"] = try fileSHA256(
          directory.appendingPathComponent("adapter_config.json"))
      }
      let split = options.values["--split"] ?? "validation"
      guard ["train", "validation", "test"].contains(split) else {
        throw ContractError.invalid("invalid inference split")
      }
      let predictions = output.appendingPathComponent("predictions.jsonl")
      FileManager.default.createFile(atPath: predictions.path, contents: nil)
      let handle = try FileHandle(forWritingTo: predictions)
      defer { try? handle.close() }
      let encoder = JSONEncoder()
      encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
      for row in rows.filter({ $0.split == split }) {
        let start = Date()
        let prediction: Prediction
        do {
          let answer = try await runner.infer(row)
          prediction = Prediction(
            id: row.image_id, adapter: adapterHash, answer: answer,
            elapsedMS: Int(Date().timeIntervalSince(start) * 1000))
        } catch let error as MemoryGuardFailure {
          throw error
        } catch let error as MLXError {
          throw error
        } catch {
          // Never log raw model output, filename, photo metadata or labels.
          prediction = Prediction(
            id: row.image_id, adapter: adapterHash, answer: nil,
            elapsedMS: Int(Date().timeIntervalSince(start) * 1000),
            error: "inference_or_output_validation_failed")
        }
        try handle.write(contentsOf: encoder.encode(prediction) + Data([10]))
        try handle.synchronize()
        Memory.clearCache()
        announce("prediction_complete")
      }
      settings["predictions_sha256"] = try fileSHA256(predictions)
    } else {
      let layers = try options.integer("layers", 1, range: 1...2)
      let rank = try options.integer("rank", 4, range: 1...8)
      let epochs = try options.integer("epochs", 1, range: 1...10)
      let maxSteps = try options.integer(
        "steps", options.command == "smoke" ? 1 : 1500, range: 1...1500)
      let learningRate = Float(options.values["--learning-rate"] ?? "0.0001") ?? 0
      guard learningRate > 0, learningRate <= 0.01 else {
        throw ContractError.invalid("invalid learning rate")
      }
      let train = rows.filter { $0.split == "train" }
      guard !train.isEmpty else { throw ContractError.invalid("no training examples") }
      // Decode labels ONLY for train rows. Validation/test labels are never passed to model code.
      let trainIDs = Set(train.map(\.image_id))
      let labelData = try lines.filter {
        trainIDs.contains(try decoder.decode(InferenceRow.self, from: $0).image_id)
      }
      let labels = try Dictionary(
        uniqueKeysWithValues: labelData.map { data in
          let label = try decoder.decode(TrainingLabel.self, from: data)
          return (label.image_id, label)
        })
      let config = LoRAConfiguration(
        numLayers: layers,
        loraParameters: .init(
          rank: rank, scale: 8, dropout: 0, keys: ["self_attn.q_proj", "self_attn.v_proj"]))
      let initial = try guardedMLX { error in
        _ = try LoRAContainer.from(model: model, configuration: config)
        try error.check()
        let values = model.trainableParameters().flattened().map { ($0.0, $0.1 + 0) }
        try error.check()
        eval(values.map(\.1))
        try error.check()
        return values
      }
      guard !initial.isEmpty else { throw ContractError.invalid("no LoRA trainable parameters") }
      let initialURL = output.appendingPathComponent("initial-adapters.safetensors")
      try guardedMLX { error in
        try MLX.save(arrays: Dictionary(uniqueKeysWithValues: initial), url: initialURL)
        try error.check()
      }
      let initialHash = try fileSHA256(initialURL)
      let optimizer = try guardedMLX { error in
        let value = Adam(learningRate: learningRate)
        try error.check()
        return value
      }
      let trainingStarted = Date()
      var losses: [Double] = []
      var used = Set<String>()
      var updatedSteps = 0
      var firstCheck: ([any KVCache], TeacherForcing)?
      outer: for _ in 0..<epochs {
        for row in train {
          if updatedSteps >= maxSteps { break outer }
          model.train(false)
          let (prefix, sequence) = try await runner.prefix(
            row, label: labels[row.image_id]!, maxAnswer: maxAnswer)
          announce("image_prefix_ready")
          let (x, y) = try guardedMLX { error in
            let x = MLXArray(sequence.inputs).expandedDimensions(axis: 0)
            try error.check()
            let y = MLXArray(sequence.targets).expandedDimensions(axis: 0)
            try error.check()
            return (x, y)
          }
          if firstCheck == nil && options.command == "smoke" {
            firstCheck = (prefix.map { $0.copy() }, sequence)
          }
          try safety.check("gradient_before")
          model.train(true)
          let valueAndGradient = valueAndGrad(model: model) {
            (m: MuseGlimmer, tokens: MLXArray, targets: MLXArray) in
            // Fresh cache copies avoid mutation leaking to another closure evaluation.
            let cache = prefix.map { $0.copy() }
            let logits = m(tokens, cache: cache)
            return mean(crossEntropy(logits: logits.asType(.float32), targets: targets))
          }
          let (loss, gradients) = try guardedMLX { error in
            let result = valueAndGradient(model, x, y)
            try error.check()
            eval(result.0, result.1)
            try error.check()
            return result
          }
          try safety.check("gradient_ready")
          let lossValue = try checkedScalarDouble { _ in loss }
          guard lossValue.isFinite else { throw ContractError.invalid("nonfinite training loss") }
          try guardedMLX { error in
            optimizer.update(model: model, gradients: gradients)
            try error.check()
            eval(model.trainableParameters(), optimizer)
            try error.check()
          }
          try safety.check("optimizer_updated")
          losses.append(lossValue)
          used.insert(row.image_id)
          updatedSteps += 1
          announce("optimizer_update_complete")
          Memory.clearCache()
        }
      }
      model.train(false)
      let final = model.trainableParameters()
      let current = Dictionary(uniqueKeysWithValues: final.flattened())
      guard current.count == initial.count else {
        throw ContractError.invalid("adapter parameter keys changed")
      }
      var deltaSquared = 0.0
      for (key, before) in initial {
        guard let value = current[key], value.shape == before.shape else {
          throw ContractError.invalid("adapter parameter key/shape mismatch")
        }
        deltaSquared += try checkedScalarDouble { _ in sum(square(value - before)) }
      }
      guard deltaSquared.isFinite, deltaSquared > 0 else {
        throw ContractError.invalid("optimizer did not change adapter weights")
      }
      try safety.check("checkpoint_save")
      let adapterURL = output.appendingPathComponent("adapters.safetensors")
      try guardedMLX { error in
        try MLX.save(arrays: current, url: adapterURL)
        try error.check()
      }
      let encoder = JSONEncoder()
      encoder.outputFormatting = [.sortedKeys, .prettyPrinted]
      try encoder.encode(config).write(
        to: output.appendingPathComponent("adapter_config.json"), options: .atomic)
      let hash = try fileSHA256(adapterURL)
      var referenceLogits: MLXArray?
      if let (prefix, sequence) = firstCheck {
        try safety.check("checkpoint_reference_logits")
        referenceLogits = try guardedMLX { error in
          let x = MLXArray(sequence.inputs).expandedDimensions(axis: 0)
          try error.check()
          let value = model(x, cache: prefix.map { $0.copy() })
          try error.check()
          eval(value)
          try error.check()
          return value
        }
      }
      try safety.check("checkpoint_reload")
      let restored = try guardedMLX { error in
        let value = try LoRAContainer.from(directory: output)
        try error.check()
        return value
      }
      // Verify keys, shapes and tensor values before using reloaded parameters.
      let reloaded = Dictionary(uniqueKeysWithValues: restored.parameters.flattened())
      guard Set(reloaded.keys) == Set(current.keys) else {
        throw ContractError.invalid("reloaded adapter parameter keys mismatch")
      }
      var reloadError = 0.0
      for (key, value) in current {
        guard let loaded = reloaded[key], loaded.shape == value.shape else {
          throw ContractError.invalid("reloaded adapter parameter shape mismatch")
        }
        reloadError = max(reloadError, try checkedScalarDouble { _ in max(abs(loaded - value)) })
      }
      // Reload the serialized adapter, then compare with logits captured before replacement.
      try guardedMLX { error in
        try model.load(adapter: restored)
        try error.check()
      }
      var logitsError: Double = 0
      if let (prefix, sequence) = firstCheck, let expected = referenceLogits {
        try safety.check("checkpoint_reloaded_logits")
        let afterReload = try guardedMLX { error in
          let x = MLXArray(sequence.inputs).expandedDimensions(axis: 0)
          try error.check()
          let value = model(x, cache: prefix.map { $0.copy() })
          try error.check()
          eval(value)
          try error.check()
          return value
        }
        logitsError = try checkedScalarDouble { _ in max(abs(afterReload - expected)) }
      }
      guard reloadError <= 1e-6, logitsError <= 1e-3, hash != initialHash else {
        throw ContractError.invalid("adapter save/reload verification failed")
      }
      var evidence: [String: Any] = [
        "schema_version": options.command == "smoke"
          ? "beverage-preflight-v1" : "beverage-training-v1", "updated_steps": updatedSteps,
        "training_method": "image-conditioned-detached-prefix-response-only-lora",
        "initial_adapter_sha256": initialHash, "adapter_sha256": hash,
        "parameter_delta_l2": sqrt(deltaSquared),
        "save_reload_max_abs_error": max(reloadError, logitsError),
        "train_image_ids": used.sorted(), "loss_history": losses, "settings": settings,
        "memory": memoryRecord("training_finished"), "layers": layers, "rank": rank,
        "learning_rate": learningRate,
        "train_manifest_sha256": try options.required("train-manifest-sha256"),
        "split_policy_sha256": try options.required("split-policy-sha256"),
        "completed_utc": ISO8601DateFormatter().string(from: Date()),
      ]
      evidence["training_wall_seconds"] = Date().timeIntervalSince(trainingStarted)
      evidence["trainable_parameter_count"] = initial.reduce(0) { $0 + $1.1.size }
      evidence["visual_conditioning"] =
        "frozen image encoder and frozen prompt prefix KV caches; gradients only through response positions in last language layer adapters"
      try writeJSON(evidence, output.appendingPathComponent("training.json"))
      settings["adapter_sha256"] = hash
    }
    try safety.check("finished")
    settings["memory"] = memoryRecord("finished")
    try writeJSON(settings, output.appendingPathComponent("runtime.json"))
    announce("finished")
  } catch {
    let detail = String(describing: error).lowercased()
    let kind =
      error is MLXError
      ? ((detail.contains("alloc") || detail.contains("memory"))
        ? "backend_allocation_failed" : "backend_mlx_failed")
      : "contract_or_runtime_failed"
    safety.recordFailure(kind)
    throw error
  }
}

@main
struct Launcher {
  static func main() async {
    do { try await run() } catch {
      let reason =
        (error as? ContractError).map(String.init(describing:))
        ?? String(describing: type(of: error))
      FileHandle.standardError.write(Data("meta-beverage failed: \(reason)\n".utf8))
      exit(1)
    }
  }
}
