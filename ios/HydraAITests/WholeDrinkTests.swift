import XCTest
@testable import HydraAI

final class WholeDrinkTests: XCTestCase {
    private func coffee(_ lower: Int? = 175, _ upper: Int? = 225, capacity: Int? = 250) -> RecognitionCandidate {
        RecognitionCandidate(identity: "Coffee", productId: nil, containerMl: capacity,
            confidence: "low", uncertaintyReasons: ["Verify the estimate"],
            estimatedLiquidMlMin: lower, estimatedLiquidMlMax: upper,
            volumeBasis: lower == nil ? "unknown" : "visual_estimate")
    }
    func testWholeLiquidUsesEstimateOrExactPhotoCorrectionAndNeverCapacityAlone() {
        XCTAssertEqual(coffee().wholeLiquidMl, 200)
        XCTAssertEqual(coffee(100, 201).wholeLiquidMl, 151)
        XCTAssertNil(coffee(nil, nil, capacity: 500).wholeLiquidMl)
        XCTAssertEqual(coffee(175, 225, capacity: nil).wholeLiquidMl, 200)
        var candidate = coffee()
        candidate.personalCorrection = PersonalRecognitionCorrection(identity: "Coffee", containerMl: 300,
            liquidMl: 240, matchBasis: "exact_image", confirmedAt: "2026-11-01T12:00:00Z")
        XCTAssertEqual(candidate.wholeLiquidMl, 240)
        candidate.personalCorrection = PersonalRecognitionCorrection(identity: "Coffee", containerMl: nil,
            liquidMl: nil, matchBasis: "product_label", confirmedAt: "2026-11-01T12:00:00Z")
        XCTAssertEqual(candidate.wholeLiquidMl, 200)
    }
    func testLabelSizeStaysSeparateAndContradictoryLiquidDoesNotPrefill() {
        var candidate = coffee(300, 400, capacity: 600)
        candidate.labelCapacityMl = 350
        XCTAssertEqual(candidate.containerMl, 600)
        XCTAssertEqual(candidate.suggestedCapacity, 350)
        XCTAssertNil(candidate.wholeLiquidMl)
    }
    func testUnknownCapacityAndWholeDrinkAssumptionSurvivePendingSerialization() throws {
        let data = Data("""
        {"category":"Coffee","consumed_ml":200,"consumed_at":"2026-11-01T12:00:00Z","timezone":"UTC","source":"confirmed_recognition","consumption_assumption":"entire_liquid"}
        """.utf8)
        let decoder = JSONDecoder(); decoder.dateDecodingStrategy = .iso8601
        let request = try decoder.decode(CreateBeverageRequest.self, from: data)
        XCTAssertNoThrow(try request.validate())
        let encoder = JSONEncoder(); encoder.dateEncodingStrategy = .iso8601
        let encoded = try XCTUnwrap(JSONSerialization.jsonObject(with: encoder.encode(request)) as? [String: Any])
        XCTAssertEqual(encoded["consumption_assumption"] as? String, "entire_liquid")
        XCTAssertNil(encoded["container_ml"])
    }
    func testSimpleDraftDefaultsToWholeLiquidAndSupportsPartialVolumeAndUnits() {
        var draft = RecognitionEntryDraft(candidate: coffee())
        XCTAssertEqual(draft.consumedMl, 200)
        XCTAssertEqual(draft.assumption, "entire_liquid")
        draft.setVolume("240")
        XCTAssertEqual(draft.correctedLiquidMl, 240)
        draft.setDrankAll(false)
        XCTAssertNil(draft.consumedMl)
        draft.setVolume("125")
        XCTAssertEqual(draft.consumedMl, 125)
        XCTAssertNil(draft.assumption)
        XCTAssertEqual(draft.correctedLiquidMl, 240)
        draft.setUnit(.usFlOz); draft.setVolume("16")
        XCTAssertEqual(draft.consumedMl, 473)
        draft.setUnit(.litres); draft.setVolume("0.5")
        XCTAssertEqual(draft.consumedMl, 500)
        draft.selectPreset(355)
        XCTAssertEqual(draft.consumedMl, 355)
        XCTAssertEqual(draft.unit, .litres)
    }
    func testHiddenFillRequiresExplicitFullContainerChoiceAndTypeEditsPersist() {
        var draft = RecognitionEntryDraft(candidate: coffee(nil, nil, capacity: 500))
        XCTAssertNil(draft.consumedMl)
        draft.useFullContainer()
        XCTAssertEqual(draft.consumedMl, 500)
        XCTAssertEqual(draft.assumption, "full_container")
        XCTAssertNil(draft.correctedLiquidMl, "An assumption must not become a training measurement")
        draft.chooseType("Tea")
        XCTAssertEqual(draft.drinkType, "Tea")
        XCTAssertEqual(draft.identity, "Tea")
        draft.setVolume("600")
        XCTAssertNil(draft.confirmedCapacityMl, "A corrected liquid amount must not invent larger capacity")
        XCTAssertEqual(draft.correctedLiquidMl, 600)
    }
    func testInvalidAndFractionalVolumeInputIsBoundedInEveryUnit() {
        XCTAssertNil(RecognitionVolumeUnit.millilitres.millilitres("nan"))
        XCTAssertNil(RecognitionVolumeUnit.millilitres.millilitres("1e3"))
        XCTAssertNil(RecognitionVolumeUnit.litres.millilitres("6"))
        XCTAssertNil(RecognitionVolumeUnit.usFlOz.millilitres("0"))
        XCTAssertEqual(RecognitionVolumeUnit.usFlOz.millilitres("16.9"), 500)
    }
    func testPrintedLitreLabelPrefillsExplicitFullContainerInsteadOf950Estimate() {
        var candidate = coffee(900, 1000, capacity: 1000)
        candidate.visibleLabelText = "DASANI PURIFIED WATER 1 LITER"
        candidate.labelCapacityMl = 1000
        let draft = RecognitionEntryDraft(candidate: candidate)
        XCTAssertEqual(draft.consumedMl, 1000)
        XCTAssertEqual(draft.assumption, "full_container")
        XCTAssertNil(draft.correctedLiquidMl, "Full label capacity is a user assumption, never a measured training label")
    }
    func testPrintedCapacityWithHiddenFillUsesDisclosedFullContainerAssumption() {
        var candidate = coffee(nil, nil, capacity: 1000)
        candidate.labelCapacityMl = 1000
        var draft = RecognitionEntryDraft(candidate: candidate)
        XCTAssertEqual(draft.consumedMl, 1000)
        XCTAssertEqual(draft.assumption, "full_container")
        draft.setDrankAll(false)
        XCTAssertNil(draft.consumedMl)
        draft.setDrankAll(true)
        XCTAssertEqual(draft.consumedMl, 1000)
        XCTAssertEqual(draft.assumption, "full_container")
    }
    func testPartialLiquidAndExactPhotoCorrectionKeepPriorityOverPrintedCapacity() {
        var candidate = coffee(300, 400, capacity: 1000)
        candidate.labelCapacityMl = 1000
        var draft = RecognitionEntryDraft(candidate: candidate)
        XCTAssertEqual(draft.consumedMl, 350)
        XCTAssertEqual(draft.assumption, "entire_liquid")
        candidate.personalCorrection = PersonalRecognitionCorrection(identity: "Water", containerMl: 1000,
            liquidMl: 500, matchBasis: "exact_image", confirmedAt: "2026-11-02T12:00:00Z")
        draft = RecognitionEntryDraft(candidate: candidate)
        XCTAssertEqual(draft.consumedMl, 500)
        XCTAssertEqual(draft.assumption, "entire_liquid")
        draft.setDrankAll(false)
        draft.setDrankAll(true)
        XCTAssertEqual(draft.consumedMl, 500)
    }
    func testConflictingLabelAndLiquidRangeDoesNotBecomeFullAssumption() {
        var candidate = coffee(1100, 1200, capacity: 1500)
        candidate.labelCapacityMl = 1000
        let draft = RecognitionEntryDraft(candidate: candidate)
        XCTAssertNil(draft.consumedMl)
    }

    func testUSUnitSurvivesPresetsWholeDrinkAndPartialActions() {
        var candidate = coffee(nil, nil, capacity: 1000)
        candidate.labelCapacityMl = 1000
        var draft = RecognitionEntryDraft(candidate: candidate)
        draft.setUnit(.usFlOz)
        XCTAssertEqual(draft.consumedMl, 1000)
        draft.selectPreset(355)
        XCTAssertEqual(draft.unit, .usFlOz)
        XCTAssertEqual(draft.consumedMl, 355)
        draft.useFullContainer()
        XCTAssertEqual(draft.unit, .usFlOz)
        XCTAssertEqual(draft.consumedMl, 1000)
        XCTAssertEqual(draft.assumption, "full_container")
        draft.setDrankAll(false)
        XCTAssertEqual(draft.unit, .usFlOz)
        XCTAssertNil(draft.consumedMl)
        draft.setVolume("16.9")
        XCTAssertEqual(draft.consumedMl, 500)
        XCTAssertNil(draft.assumption)
        XCTAssertNil(draft.correctedLiquidMl)
        draft.setDrankAll(true)
        XCTAssertEqual(draft.unit, .usFlOz)
        XCTAssertEqual(draft.consumedMl, 1000)
    }

}
