// swift-tools-version: 6.2
import PackageDescription

let package = Package(
  name: "HydraMetaBeverageAdapter", platforms: [.macOS(.v14)],
  products: [.executable(name: "meta-beverage", targets: ["MetaBeverage"])],
  dependencies: [
    .package(
      url: "https://github.com/ml-explore/mlx-swift-lm",
      revision: "b8d4935ab152169ac8cb0da5414b51447e78efb1", traits: []),
    .package(url: "https://github.com/ml-explore/mlx-swift", .upToNextMinor(from: "0.33.0")),
    .package(
      url: "https://github.com/huggingface/swift-transformers",
      revision: "b38443e44d93eca770f2eb68e2a4d0fa100f9aa2"),
  ],
  targets: [
    .target(name: "BeverageCore"),
    .target(
      name: "MemorySafety",
      dependencies: ["BeverageCore", .product(name: "MLX", package: "mlx-swift")]),
    .executableTarget(
      name: "MetaBeverage",
      dependencies: [
        "BeverageCore", "MemorySafety", .product(name: "MLXVLM", package: "mlx-swift-lm"),
        .product(name: "MLXLMCommon", package: "mlx-swift-lm"),
        .product(name: "MLX", package: "mlx-swift"), .product(name: "MLXNN", package: "mlx-swift"),
        .product(name: "MLXOptimizers", package: "mlx-swift"),
        .product(name: "Tokenizers", package: "swift-transformers"),
      ]),
    .testTarget(name: "BeverageCoreTests", dependencies: ["BeverageCore"]),
    .testTarget(
      name: "MetaRuntimeTests",
      dependencies: [
        "MemorySafety", .product(name: "MLXVLM", package: "mlx-swift-lm"),
        .product(name: "MLXLMCommon", package: "mlx-swift-lm"),
        .product(name: "MLX", package: "mlx-swift"), .product(name: "MLXNN", package: "mlx-swift"),
        .product(name: "MLXOptimizers", package: "mlx-swift"),
      ]),
  ])
