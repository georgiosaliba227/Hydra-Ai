import Foundation

/// Local OCR evidence, never a measurement of liquid or consumption.
enum OnDeviceLabel {
    static let families = ["beer", "coffee", "energy", "juice", "milk", "other", "plant_milk", "soda", "sports", "tea", "water", "wine"]
    static let names = ["Beer", "Coffee", "Energy drink", "Juice", "Milk", "Beverage", "Plant milk", "Soda", "Sports drink", "Tea", "Water", "Wine"]
    struct Capacity { let milliliters: Int; let evidence: String }
    private static let metricPattern = #"(?<![\w.,+\-])(\d{1,4}(?:\.\d{1,4})?)\s*(ml|millilit(?:er|re)s?|l|lit(?:er|re)s?)\b"#
    private static let ouncePattern = #"(?<![\w.,+\-])(\d{1,4}(?:\.\d{1,4})?)\s*(U\.?S\.?\s*)?(?:fl\.?\s*oz\.?|fluid\s+ounces?)\b"#

    private static func matches(_ pattern: String, _ text: String) -> [NSTextCheckingResult] {
        guard let expression = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) else { return [] }
        return expression.matches(in: text, range: NSRange(text.startIndex..., in: text))
    }
    private static func substring(_ text: String, _ range: NSRange) -> String {
        Range(range,in:text).map { String(text[$0]) } ?? ""
    }

    static func capacity(_ text: String) -> Capacity? {
        guard !text.isEmpty, text.count <= 600 else { return nil }
        let pack = #"\b\d+[\s-]*(?:[x×](?=\s*\d)|(?:packs?|pks?|bottles?|cans?)\b)"#
        let reversePack = #"(?:ml|millilit(?:er|re)s?|l|lit(?:er|re)s?|oz)\b\s*[x×]\s*\d+\b"#
        let qualifier = #"\b(?:per|each)\s+(?:serving|portion)\b"#
        let preparation = #"\b(?:use|usage|directions?|prepar(?:e|ation)|mix(?:ing)?|dilut(?:e|ion)|concentrate|yields?|makes?|add(?:ed)?|dissolv(?:e|ing))\b"#
        guard [pack,reversePack,qualifier,preparation].allSatisfy({matches($0,text).isEmpty}) else { return nil }
        let serving = #"\b(?:servings?|portions?|per|nutrition(?:al)?)\b"#
        let markers = matches(#"\b(?:net\s*(?:contents?|volume)?|(?:bottle|container|can)\s*(?:size|volume))\s*:?\s*"#,text)
        var sections = [text]
        if !markers.isEmpty {
            // A later NET marker must never erase an earlier conflicting size.
            let prefix=substring(text,NSRange(location:0,length:markers[0].range.location))
            guard matches(metricPattern,prefix).isEmpty,matches(ouncePattern,prefix).isEmpty else { return nil }
            sections = markers.enumerated().map { index, marker in
                let start=marker.range.location+marker.range.length
                let end=index+1<markers.count ? markers[index+1].range.location : (text as NSString).length
                let section=substring(text,NSRange(location:start,length:end-start))
                if let stop=matches(serving,section).first { return substring(section,NSRange(location:0,length:stop.range.location)) }
                return section
            }
        } else if !matches(serving,text).isEmpty { return nil }
        var metric: [(Int,String)] = [], ounces: [(Int,String)] = [], ambiguousOunces: [(Int,Int)] = []
        for section in sections {
            for match in matches(metricPattern,section) {
                let number=substring(section,match.range(at:1)), unit=substring(section,match.range(at:2)).lowercased()
                guard let amount=Double(number), amount.isFinite else { return nil }
                let ml=amount*(unit.hasPrefix("m") ? 1 : 1000)
                guard ml.rounded()==ml, (1...5000).contains(ml) else { return nil }
                metric.append((Int(ml),substring(section,match.range)))
            }
            for match in matches(ouncePattern,section) {
                guard let amount=Double(substring(section,match.range(at:1))),amount.isFinite else { return nil }
                let ml=(amount*29.5735295625).rounded()
                guard (1...5000).contains(ml) else { return nil }
                if match.range(at:2).location != NSNotFound {
                    ounces.append((Int(ml),substring(section,match.range)))
                } else {
                    ambiguousOunces.append((Int(ml),Int((amount*28.4130625).rounded())))
                }
            }
        }
        func compatible(_ ml: Int) -> Bool {
            ambiguousOunces.allSatisfy { abs($0.0-ml)<=max(1,ml/100) || abs($0.1-ml)<=max(1,ml/100) }
        }
        if let first=metric.first {
            guard metric.allSatisfy({$0.0==first.0}),ounces.allSatisfy({abs($0.0-first.0)<=max(1,first.0/100)}),compatible(first.0) else { return nil }
            return Capacity(milliliters:first.0,evidence:first.1)
        }
        guard let first=ounces.first,ounces.allSatisfy({$0.0==first.0}),compatible(first.0) else { return nil }
        return Capacity(milliliters:first.0,evidence:first.1)
    }

    static func candidate(scores: [Double], text: String) -> RecognitionCandidate {
        let ranked=scores.enumerated().sorted { $0.element > $1.element }
        let accepted=scores.count==families.count && scores.allSatisfy(\.isFinite) && ranked[0].element >= 0.35 && ranked[0].element-ranked[1].element >= 0.10
        let index=accepted ? ranked[0].offset : nil
        let name=index.map { names[$0] } ?? "Unknown beverage"
        // Only a small explicit beverage-brand vocabulary may survive OCR.
        // Arbitrary background text never becomes a durable name or receipt.
        let brands: [(String,String)] = [(#"\bdasani\b"#,"Dasani"),(#"\bevian\b"#,"Evian"),
            (#"\bcoca[\s-]*cola\b"#,"Coca-Cola"),(#"\bpepsi\b"#,"Pepsi"),(#"\bgatorade\b"#,"Gatorade"),
            (#"\bbodyarmor\b"#,"BODYARMOR"),(#"\bla\s*croix\b"#,"LaCroix"),(#"\bstarbucks\b"#,"Starbucks"),
            (#"\bred\s*bull\b"#,"Red Bull"),(#"\btropicana\b"#,"Tropicana")]
        let boundedText=text.count<=600 ? text : ""
        let found=brands.filter { !matches($0.0,boundedText).isEmpty }.map(\.1)
        let brand=found.count==1 ? found[0] : nil
        let size=capacity(text)
        var reasons=["Experimental on-device category suggestion; scores are uncalibrated. Verify every field.",
                     "Printed size is container capacity, not measured liquid or actual consumption."]
        if index==nil { reasons.append("No supported category match; enter the drink name and type.") }
        if size==nil { reasons.append("Printed size is unknown or ambiguous; enter it yourself.") }
        if text.count>600 { reasons.append("Label text exceeds the supported size; no partial label was used to infer capacity.") }
        let identity=brand.map { "\($0) \(index == nil ? "beverage" : name.lowercased())" } ?? name
        var result=RecognitionCandidate(identity:identity,productId:nil,containerMl:size?.milliliters,
                                        confidence:"low",uncertaintyReasons:reasons)
        result.category=index.map { names[$0] }; result.brand=brand
        result.labelCapacityMl=size?.milliliters; result.visibleLabelText=size?.evidence
        return result
    }
}
