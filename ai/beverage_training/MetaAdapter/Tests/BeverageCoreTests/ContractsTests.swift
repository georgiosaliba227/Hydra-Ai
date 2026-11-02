import XCTest

@testable import BeverageCore

final class ContractsTests: XCTestCase {
  func testResponseOnlyTeacherForcingIncludesFirstAnswerToken() throws {
    let sequence = try TeacherForcing(prompt: [1, 2, 3], answer: [10, 11, 99], maxAnswerTokens: 4)
    XCTAssertEqual(sequence.prefix, [1, 2])
    XCTAssertEqual(sequence.inputs, [3, 10, 11])
    XCTAssertEqual(sequence.targets, [10, 11, 99])
  }
  func testTeacherForcingRejectsEmptyAndOversizeResponses() {
    XCTAssertThrowsError(try TeacherForcing(prompt: [], answer: [1], maxAnswerTokens: 3))
    XCTAssertThrowsError(try TeacherForcing(prompt: [1], answer: [], maxAnswerTokens: 3))
    XCTAssertThrowsError(try TeacherForcing(prompt: [1], answer: [1, 2, 3, 4], maxAnswerTokens: 3))
  }
  func testStrictOutputPreservesUnknownAndRejectsInventedUnitsAndExtras() throws {
    XCTAssertEqual(
      try BeverageAnswer.parse("{\"brand\":null,\"product\":\"water\",\"capacity_ml\":null}")
        .capacity_ml, nil)
    for bad in [
      "{\"brand\":\"A\",\"product\":\"B\",\"capacity_ml\":-1}",
      "{\"brand\":\"A\",\"product\":\"B\",\"capacity_ml\":12.5}",
      "{\"brand\":\"A\",\"product\":\"B\",\"capacity_ml\":\"500\"}",
      "{\"brand\":\"A\",\"product\":\"B\",\"capacity_ml\":500,\"extra\":1}",
      "prefix {\"brand\":null,\"product\":null,\"capacity_ml\":null}",
    ] {
      XCTAssertThrowsError(try BeverageAnswer.parse(bad))
    }
  }
  func testImagePathCannotEscapeRoot() throws {
    let root = URL(fileURLWithPath: "/private/tmp/dataset")
    XCTAssertEqual(
      try safeImageURL(root: root, relativePath: "images/abc.jpg").path,
      "/private/tmp/dataset/images/abc.jpg")
    for bad in ["../answer.jpg", "/tmp/answer.jpg", "images/../../answer.jpg"] {
      XCTAssertThrowsError(try safeImageURL(root: root, relativePath: bad))
    }
  }
}
