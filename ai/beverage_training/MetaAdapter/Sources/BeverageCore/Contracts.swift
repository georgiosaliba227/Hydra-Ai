import CoreFoundation
import CryptoKit
import Foundation

public enum ContractError: Error, CustomStringConvertible {
  case invalid(String)
  public var description: String {
    if case .invalid(let reason) = self { reason } else { "invalid contract" }
  }
}

public let recognitionPrompt = """
  Read the visible label of the single beverage container carefully. Return exactly one JSON object with keys "brand", "product", "capacity_ml". Brand and product are strings or null. Brand is the company or brand mark; put the named product range in product rather than appending it to brand. Product is a concise beverage name including visible type, flavor and distinguishing variant qualifiers such as organic, diet, fat percentage or ingredient variety. Do not copy slogans, serving instructions or the entire label. Do not add descriptions that are not printed. capacity_ml is the printed net capacity of ONE container in integer millilitres, or null when unreadable or unsupported. Inspect the label for a metric declaration even when US fluid ounces are more prominent. If metric and US units are both printed, use the printed metric value exactly rather than converting US units. Convert printed litres to mL; convert US fluid ounces only when no metric declaration is printed. Round fractional mL to the nearest integer with halves rounded upward. Do not use serving sizes, multipack totals, remaining liquid or consumed quantity. Use null instead of guessing unreadable evidence or relying on product memory. Output JSON only.
  """
public let generationHeader = " to=user<|message|>"
public let templateCurrentDate = "2026-11-02"
public let reasoningStrength = "low"
public let baseModelID = "mlx-community/Muse-Glimmer-30B-4bit"
public let baseRevision = "3e7677d7a40d348a3daba263a2b1c0aa41910710"
public let runtimeRevision = "b8d4935ab152169ac8cb0da5414b51447e78efb1"

/// Prefill every prompt token except the final token without an autodiff trace.
/// The final prompt token predicts answer[0], so every answer token receives loss.
public struct TeacherForcing {
  public let prefix: [Int]
  public let inputs: [Int]
  public let targets: [Int]
  public init(prompt: [Int], answer: [Int], maxAnswerTokens: Int) throws {
    guard prompt.count >= 2, !answer.isEmpty, answer.count <= maxAnswerTokens else {
      throw ContractError.invalid("empty prompt/answer or answer exceeds token budget")
    }
    prefix = Array(prompt.dropLast())
    inputs = [prompt.last!] + answer.dropLast()
    targets = answer
  }
}

public struct BeverageAnswer: Codable, Equatable {
  public let brand: String?
  public let product: String?
  public let capacity_ml: Int?
  public init(brand: String?, product: String?, capacity_ml: Int?) {
    self.brand = brand
    self.product = product
    self.capacity_ml = capacity_ml
  }
  enum CodingKeys: String, CodingKey { case brand, product, capacity_ml }
  public func encode(to encoder: Encoder) throws {
    var c = encoder.container(keyedBy: CodingKeys.self)
    try c.encode(brand, forKey: .brand)
    try c.encode(product, forKey: .product)
    try c.encode(capacity_ml, forKey: .capacity_ml)
  }
  public static func parse(_ text: String) throws -> BeverageAnswer {
    let data = Data(text.utf8)
    guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any],
      Set(object.keys) == Set(["brand", "product", "capacity_ml"])
    else {
      throw ContractError.invalid("output must be exactly the requested JSON object")
    }
    for key in ["brand", "product"] {
      guard
        object[key] is NSNull
          || (object[key] as? String).map({
            !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && $0.count <= 200
          }) == true
      else {
        throw ContractError.invalid("invalid identity field")
      }
    }
    if !(object["capacity_ml"] is NSNull) {
      guard let value = object["capacity_ml"] as? NSNumber,
        CFGetTypeID(value) != CFBooleanGetTypeID(),
        String(cString: value.objCType) != "d", String(cString: value.objCType) != "f",
        value.intValue > 0, value.intValue <= 20_000
      else {
        throw ContractError.invalid("capacity must be integer mL or null")
      }
    }
    return try JSONDecoder().decode(Self.self, from: data)
  }
}

public func sha256(_ data: Data) -> String {
  SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}
public func fileSHA256(_ url: URL) throws -> String {
  let handle = try FileHandle(forReadingFrom: url)
  defer { try? handle.close() }
  var hash = SHA256()
  while let block = try handle.read(upToCount: 1 << 20), !block.isEmpty { hash.update(data: block) }
  return hash.finalize().map { String(format: "%02x", $0) }.joined()
}
public func safeImageURL(root: URL, relativePath: String) throws -> URL {
  guard !relativePath.hasPrefix("/"), !relativePath.split(separator: "/").contains("..") else {
    throw ContractError.invalid("image path escapes dataset root")
  }
  let resolvedRoot = root.standardizedFileURL.resolvingSymlinksInPath()
  let result = resolvedRoot.appendingPathComponent(relativePath).standardizedFileURL
  guard result.path.hasPrefix(resolvedRoot.path + "/"), result.resolvingSymlinksInPath() == result
  else {
    throw ContractError.invalid("image path escapes dataset root or uses a symlink")
  }
  return result
}

/// Inference intentionally decodes only this projection of the source manifest.
/// Labels, barcode, filename text and source metadata never enter the model input.
public struct InferenceRow: Decodable {
  public let image_id: String
  public let image_path: String?
  public let image_sha256: String
  public let split: String
  public let review_status: String
}
public struct TrainingLabel: Decodable {
  public let image_id: String
  public let brand: String?
  public let product: String?
  public let capacity_ml: Int?
  public let capacity_visible: Bool
  public let split: String
  public var answer: BeverageAnswer {
    BeverageAnswer(
      brand: brand, product: product, capacity_ml: capacity_visible ? capacity_ml : nil)
  }
}

public struct Prediction: Encodable {
  public let image_id: String
  public let model_id = baseModelID
  public let base_revision = baseRevision
  public let adapter_sha256: String?
  public let prompt_sha256 = sha256(Data(recognitionPrompt.utf8))
  public let outcome: String
  public let brand: String?
  public let product: String?
  public let capacity_ml: Int?
  public let latency_ms: Int
  public let error: String?
  public init(
    id: String, adapter: String?, answer: BeverageAnswer?, elapsedMS: Int, error: String? = nil
  ) {
    image_id = id
    adapter_sha256 = adapter
    outcome = error == nil ? "success" : "error"
    brand = answer?.brand
    product = answer?.product
    capacity_ml = answer?.capacity_ml
    latency_ms = elapsedMS
    self.error = error
  }
  public func encode(to encoder: Encoder) throws {
    var c = encoder.container(keyedBy: Keys.self)
    try c.encode(image_id, forKey: .image_id)
    try c.encode(model_id, forKey: .model_id)
    try c.encode(base_revision, forKey: .base_revision)
    try c.encode(adapter_sha256, forKey: .adapter_sha256)
    try c.encode(prompt_sha256, forKey: .prompt_sha256)
    try c.encode(outcome, forKey: .outcome)
    try c.encode(brand, forKey: .brand)
    try c.encode(product, forKey: .product)
    try c.encode(capacity_ml, forKey: .capacity_ml)
    try c.encode(latency_ms, forKey: .latency_ms)
    try c.encode(error, forKey: .error)
  }
  enum Keys: String, CodingKey {
    case image_id, model_id, base_revision, adapter_sha256, prompt_sha256, outcome, brand, product,
      capacity_ml, latency_ms, error
  }
}
