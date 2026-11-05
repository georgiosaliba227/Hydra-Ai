import Foundation
import CoreML
import Vision
import ImageIO

enum OnDeviceRecognitionError: LocalizedError {
    case modelUnavailable, invalidImage, invalidOutput
    var errorDescription: String? {
        switch self {
        case .modelUnavailable: "The bundled on-device model is unavailable. Log manually or install the complete Hydra build."
        case .invalidImage: "This photo could not be read on this iPhone. Choose another photo or log manually."
        case .invalidOutput: "On-device recognition could not produce a valid suggestion. No photo was sent and no drink was saved."
        }
    }
}

/// Serialized local inference. This type has no network or credential dependency.
actor OnDeviceRecognizer {
    static let shared=OnDeviceRecognizer()
    static let modelID="dinov2-small-beverage-v1"
    private var model: VNCoreMLModel?
    private let modelURL: URL?

    init(modelURL: URL? = Bundle.main.url(forResource:"HydraBeverage",withExtension:"mlmodelc")) {
        self.modelURL=modelURL
    }

    static var isAvailable: Bool { Bundle.main.url(forResource:"HydraBeverage",withExtension:"mlmodelc") != nil }

    private func loadModel() throws -> VNCoreMLModel {
        if let model { return model }
        guard let url=modelURL else { throw OnDeviceRecognitionError.modelUnavailable }
        let config=MLModelConfiguration(); config.computeUnits = .all
        let loaded=try MLModel(contentsOf:url,configuration:config)
        let metadata=loaded.modelDescription.metadata[.creatorDefinedKey] as? [String:String]
        guard metadata?["hydra.model_id"]==Self.modelID,
              metadata?["hydra.base_revision"]=="ed25f3a31f01632728cabb09d1542f84ab7b0056",
              let labelData=metadata?["hydra.families"]?.data(using:.utf8),
              try JSONDecoder().decode([String].self,from:labelData)==OnDeviceLabel.families,
              let image=loaded.modelDescription.inputDescriptionsByName["image"]?.imageConstraint,
              image.pixelsWide==224,image.pixelsHigh==224,
              loaded.modelDescription.outputDescriptionsByName["scores"]?.multiArrayConstraint?.shape.map(\.intValue)==[1,12] else {
            throw OnDeviceRecognitionError.modelUnavailable
        }
        let ready=try VNCoreMLModel(for:loaded); model=ready; return ready
    }

    func analyze(jpeg: Data) async throws -> RecognitionResult {
        try Task.checkCancellation()
        guard jpeg.count<=1_048_576,jpeg.starts(with:[0xff,0xd8]),jpeg.suffix(2)==Data([0xff,0xd9]) else { throw OnDeviceRecognitionError.invalidImage }
        guard let source=CGImageSourceCreateWithData(jpeg as CFData,nil),CGImageSourceGetCount(source)==1,
              let properties=CGImageSourceCopyPropertiesAtIndex(source,0,nil) as? [CFString:Any],
              let width=properties[kCGImagePropertyPixelWidth] as? Int,
              let height=properties[kCGImagePropertyPixelHeight] as? Int,
              (1...1600).contains(width),(1...1600).contains(height) else { throw OnDeviceRecognitionError.invalidImage }
        let request=VNCoreMLRequest(model:try loadModel())
        request.imageCropAndScaleOption = .scaleFill
        let text=VNRecognizeTextRequest(); text.recognitionLevel = .accurate
        text.usesLanguageCorrection = false; text.recognitionLanguages=["en-US"]
        // Vision/Core ML execute locally. Prepared JPEG has no original metadata.
        do { try VNImageRequestHandler(data:jpeg,options:[:]).perform([request,text]) }
        catch { throw OnDeviceRecognitionError.invalidImage }
        try Task.checkCancellation()
        guard let observations=request.results as? [VNCoreMLFeatureValueObservation],
              let output=observations.first(where:{$0.featureName=="scores"})?.featureValue.multiArrayValue,
              output.count==12 else { throw OnDeviceRecognitionError.invalidOutput }
        let scores=(0..<12).map { output[$0].doubleValue }
        guard scores.allSatisfy(\.isFinite) else { throw OnDeviceRecognitionError.invalidOutput }
        let lines=(text.results ?? []).compactMap { observation -> String? in
            guard let value=observation.topCandidates(1).first,value.confidence>=0.4 else { return nil }
            return value.string
        }
        // Check complete recognized context. Truncating can hide a second size,
        // serving qualifier or multipack. The label boundary abstains above600.
        let evidence=lines.joined(separator:"\n")
        let candidate=OnDeviceLabel.candidate(scores:scores,text:evidence)
        let result=RecognitionResult(version:"recognition-v1",mode:"on_device",model:Self.modelID,
                                     candidates:[candidate],requiresConfirmation:true,recognitionId:UUID())
        try result.validate(); return result
    }
}
