import XCTest
import UIKit
@testable import HydraAI

final class OnDeviceCameraTests: XCTestCase {
    func testPrintedSizesRequireUnambiguousContainerEvidence() {
        for (text, ml) in [("NET 500 mL",500),("1 L",1000),("Net contents 12 US fl oz",355),
                           ("500 mL / 16.9 US fl oz",500)] {
            XCTAssertEqual(OnDeviceLabel.capacity(text)?.milliliters,ml,text)
        }
        for text in ["Serving size 250 mL", "Nutrition per 100 ml", "6 x 330 mL", "6 cans 330 mL",
                     "6-pack 330 mL", "6pk 330 mL",
                     "250 mL x 6", "NET 250 mL per serving", "250 mL\nNET 500 mL",
                     "NET 500 mL (32 fl oz)", "USAGE: mix with 250 mL of water",
                     "500 mL 1 L", "12 fl oz", "-500 ml", "1,500 ml", "50000ml", "0 ml", "5.1 L"] {
            XCTAssertNil(OnDeviceLabel.capacity(text),text)
        }
        XCTAssertEqual(OnDeviceLabel.capacity("Net 500 mL Nutrition per 100 mL")?.milliliters,500)
        XCTAssertNil(OnDeviceLabel.capacity("Net 500 mL / 12 US fl oz"))
        let long="NET 500 mL\n"+String(repeating:"background words ",count:50)+"NET 1 L"
        XCTAssertNil(OnDeviceLabel.candidate(scores:Array(repeating:0,count:12),text:long).containerMl)
    }

    func testContainerCorrectionsPreserveOriginalAndSeparateAmount() {
        var candidate=RecognitionCandidate(identity:"Water",productId:nil,containerMl:500,confidence:"low",uncertaintyReasons:["Verify"])
        candidate.labelCapacityMl=500
        for size in [355,750] {
            var draft=RecognitionEntryDraft(candidate:candidate,allowsCapacityCorrection:true)
            draft.setCapacity(String(size))
            XCTAssertTrue(draft.valid)
            XCTAssertEqual(draft.confirmedCapacityMl,size)
            XCTAssertEqual(draft.consumedMl,size)
            XCTAssertEqual(draft.assumption,"full_container")
            XCTAssertEqual(draft.candidate.containerMl,500)
        }
        var cleared=RecognitionEntryDraft(candidate:candidate,allowsCapacityCorrection:true)
        cleared.setCapacity("")
        XCTAssertNil(cleared.confirmedCapacityMl); XCTAssertNil(cleared.consumedMl)
        cleared.setVolume("240")
        XCTAssertEqual(cleared.consumedMl,240); XCTAssertTrue(cleared.valid)
        XCTAssertEqual(cleared.assumption,"entire_liquid")
        var partial=RecognitionEntryDraft(candidate:candidate,allowsCapacityCorrection:true)
        partial.setDrankAll(false); partial.setVolume("125"); partial.setCapacity("355")
        XCTAssertEqual(partial.consumedMl,125); XCTAssertEqual(partial.confirmedCapacityMl,355)
        partial.setCapacity(""); XCTAssertNil(partial.confirmedCapacityMl); XCTAssertEqual(partial.consumedMl,125)
        var tooLarge=RecognitionEntryDraft(candidate:candidate,allowsCapacityCorrection:true)
        tooLarge.setVolume("750"); XCTAssertFalse(tooLarge.valid)
        tooLarge.setCapacity("750"); XCTAssertTrue(tooLarge.valid)
        var typing=RecognitionEntryDraft(candidate:candidate,allowsCapacityCorrection:true)
        typing.setCapacity("");typing.setCapacity("3");typing.setCapacity("35");typing.setCapacity("355")
        XCTAssertEqual(typing.consumedMl,355,"Replacing capacity text must retain the full-container assumption through intermediate empty input")
    }

    func testUnrelatedOCRIsNeverReturnedAsDrinkIdentity() {
        let candidate = OnDeviceLabel.candidate(scores: Array(repeating: 0.0,count:12), text:"PRIVATE PERSON ADDRESS 123 ROAD")
        XCTAssertEqual(candidate.identity,"Unknown beverage")
        XCTAssertNil(candidate.visibleLabelText)
        XCTAssertNil(candidate.brand)
        XCTAssertNil(candidate.containerMl)
    }

    func testLearnedCategoriesKeepTheirTypeInReview() {
        for category in ["Beer","Wine","Plant milk"] {
            var candidate=RecognitionCandidate(identity:category,productId:nil,containerMl:nil,confidence:"low",uncertaintyReasons:["Verify"])
            candidate.category=category
            XCTAssertEqual(RecognitionEntryDraft(candidate:candidate).drinkType,category)
        }
    }

    func testUncalibratedScoresAndInvalidModelOutputStayUncertain() {
        var scores=Array(repeating:0.0,count:12); scores[10]=0.8
        let candidate=OnDeviceLabel.candidate(scores:scores,text:"DASANI WATER NET 500 mL")
        XCTAssertEqual(candidate.brand,"Dasani")
        XCTAssertEqual(candidate.containerMl,500)
        XCTAssertEqual(candidate.confidence,"low")
        XCTAssertNil(candidate.estimatedLiquidMlMin)
        XCTAssertEqual(candidate.visibleLabelText,"500 mL")
        let invalid=OnDeviceLabel.candidate(scores:[.nan],text:"")
        XCTAssertEqual(invalid.identity,"Unknown beverage")
    }

    func testLocalStorePersistsRealRecognitionAndOriginalSuggestionWithoutPhoto() async throws {
        let root=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at:root) }
        let url=root.appendingPathComponent("real.json")
        let original=RecognitionCandidate(identity:"Water",productId:nil,containerMl:500,confidence:"low",uncertaintyReasons:["Verify"])
        let provenance=OnDeviceRecognitionProvenance(modelID:"dinov2-small-beverage-v1",originalCandidate:original,processedAt:.now)
        var request=CreateBeverageRequest(category:"Corrected water",consumedMl:500,consumedAt:.now,timezone:"America/New_York",source:"confirmed_recognition",recognitionId:UUID(),containerMl:500,consumptionAssumption:"full_container")
        request.onDeviceRecognition=provenance
        let service=LocalBeverageService(fileURL:url)
        let key=UUID()
        let first=try await service.createBeverage(request,idempotencyKey:key)
        let replay=try await service.createBeverage(request,idempotencyKey:key)
        XCTAssertEqual(first,replay)
        let restored=LocalBeverageService(fileURL:url)
        let logs=try await restored.listBeverages()
        XCTAssertEqual(logs.count,1)
        XCTAssertEqual(logs[0].onDeviceRecognition?.originalCandidate.identity,"Water")
        XCTAssertEqual(logs[0].category,"Corrected water")
        XCTAssertEqual(logs[0].containerMl,500,"Confirmed size must survive separately from the original suggestion")
        XCTAssertEqual(logs[0].consumptionAssumption,"full_container")
        let exported=try await restored.exportData()
        let text=String(decoding:exported,as:UTF8.self)
        XCTAssertTrue(text.contains("dinov2-small-beverage-v1"))
        XCTAssertFalse(text.contains("photo_base64")); XCTAssertFalse(text.contains("synthetic"))
        let conflicting=CreateBeverageRequest(category:"Other",consumedMl:10,consumedAt:.now,timezone:"America/New_York",source:"manual")
        do { _=try await restored.createBeverage(conflicting,idempotencyKey:key); XCTFail("Conflicting replay accepted") } catch { }
        let deleted=try await restored.deleteAllData(); XCTAssertEqual(deleted,1)
        let after=try await restored.listBeverages(); XCTAssertTrue(after.isEmpty)
    }

    func testCorruptLocalStoreIsNeverSilentlyReset() async throws {
        let url=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at:url) }
        try Data("broken".utf8).write(to:url)
        do { _=try await LocalBeverageService(fileURL:url).listBeverages(); XCTFail("Corrupt records reset") } catch { }
        XCTAssertEqual(try Data(contentsOf:url),Data("broken".utf8))
    }

    @MainActor func testOnDeviceConfigurationNeverRequiresBackendAndPreservesDestination() async throws {
        let root=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at:root) }
        let service=LocalBeverageService(fileURL:root.appendingPathComponent("real.json"))
        let config=APIConfiguration(baseURL:"",token:"",offline:false,onDevice:true)
        let store=BeverageStore(service:service,pendingURL:root.appendingPathComponent("pending.json"),configuration:config)
        XCTAssertTrue(store.isOffline); XCTAssertTrue(store.isOnDevice)
        try await store.add(category:"Water",consumedMl:250,at:.now)
        XCTAssertEqual(store.logs.count,1)
        XCTAssertEqual(store.summary?.beverageTotalMl,250)
        XCTAssertNil(store.pending)
    }

    @MainActor func testOnDeviceSessionRejectsStaleResultsAndRequiresExplicitAnalysis() throws {
        let session=CameraSession(), generation=UUID()
        let capability=try XCTUnwrap(session.beginCapabilities(generation:generation))
        XCTAssertTrue(session.completeCapabilities("on_device",ticket:capability,currentGeneration:generation))
        XCTAssertNil(session.beginAnalysis(generation:generation))
        session.consent=true
        let ticket=try XCTUnwrap(session.beginAnalysis(generation:generation))
        XCTAssertNil(session.beginAnalysis(generation:generation))
        let changed=UUID(); session.bind(to:changed)
        let result=RecognitionResult(version:"recognition-v1",mode:"on_device",model:OnDeviceRecognizer.modelID,candidates:[],requiresConfirmation:true,recognitionId:UUID())
        XCTAssertFalse(session.completeAnalysis(result,ticket:ticket,currentGeneration:changed))
        XCTAssertNil(session.result)
    }

    @MainActor func testBundledRealCoreMLAndOCRAnalyzeLocallyAndRejectInvalidPhoto() async throws {
        XCTAssertTrue(OnDeviceRecognizer.isAvailable)
        let image=UIGraphicsImageRenderer(size:CGSize(width:500,height:700)).image { context in
            UIColor.white.setFill(); context.fill(CGRect(x:0,y:0,width:500,height:700))
            ("DASANI\nWATER\nNET 500 mL" as NSString).draw(in:CGRect(x:50,y:180,width:400,height:300),
                withAttributes:[.font:UIFont.boldSystemFont(ofSize:40),.foregroundColor:UIColor.black])
        }
        let photo=try PhotoPreparation.jpeg(image)
        do { _=try await OnDeviceRecognizer(modelURL:nil).analyze(jpeg:photo); XCTFail("Missing model accepted") }
        catch { guard case OnDeviceRecognitionError.modelUnavailable=error else { return XCTFail("Unexpected missing-model error") } }
        let started=Date()
        let result=try await OnDeviceRecognizer.shared.analyze(jpeg:photo)
        try result.validate()
        XCTAssertEqual(result.mode,"on_device")
        XCTAssertEqual(result.model,"dinov2-small-beverage-v1")
        XCTAssertEqual(result.candidates.first?.containerMl,500)
        XCTAssertEqual(result.candidates.first?.brand,"Dasani")
        XCTAssertNil(result.candidates.first?.nutrition)
        XCTAssertNil(result.candidates.first?.estimatedLiquidMlMin)
        XCTAssertNotNil(result.recognitionId)
        print("ON_DEVICE_SIMULATOR_ANALYSIS_SECONDS",Date().timeIntervalSince(started))
        do { _=try await OnDeviceRecognizer.shared.analyze(jpeg:Data("invalid".utf8)); XCTFail("Invalid photo accepted") } catch { }
    }

    @MainActor func testCompleteOCRCannotLoseConflictingSizeAfterFortyLines() async throws {
        let image=UIGraphicsImageRenderer(size:CGSize(width:800,height:1600)).image { context in
            UIColor.white.setFill(); context.fill(CGRect(x:0,y:0,width:800,height:1600))
            let attributes:[NSAttributedString.Key:Any]=[.font:UIFont.boldSystemFont(ofSize:24),.foregroundColor:UIColor.black]
            ("NET 500 mL" as NSString).draw(at:CGPoint(x:40,y:30),withAttributes:attributes)
            for index in 0..<45 {
                ("ROW \(index)" as NSString).draw(at:CGPoint(x:40,y:80+index*30),withAttributes:attributes)
            }
            ("NET 1 L" as NSString).draw(at:CGPoint(x:40,y:1500),withAttributes:attributes)
        }
        let result=try await OnDeviceRecognizer.shared.analyze(jpeg:PhotoPreparation.jpeg(image))
        XCTAssertNil(result.candidates.first?.containerMl,"Complete OCR must reject conflicting size beyond the old forty-line cutoff")
    }
}
