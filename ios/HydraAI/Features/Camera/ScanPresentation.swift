import SwiftUI
import UIKit

struct BeverageScanStage: View {
    let image: UIImage?
    let scanning: Bool
    var compact = false
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        ZStack {
            HydraStyle.ink
            if let image {
                Image(uiImage: image).resizable().scaledToFit()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .accessibilityLabel("Selected beverage photo")
            } else {
                FloatingBottle()
            }
            if scanning {
                Color.black.opacity(0.3)
                TimelineView(.animation(minimumInterval: 1.0 / 30, paused: reduceMotion)) { context in
                    GeometryReader { geometry in
                        let position = reduceMotion ? 0.5 : (sin(context.date.timeIntervalSinceReferenceDate * 2) + 1) / 2
                        Rectangle()
                            .fill(LinearGradient(colors: [.clear, HydraStyle.aqua.opacity(0.45)], startPoint: .top, endPoint: .bottom))
                            .frame(height: 60)
                            .overlay(alignment: .bottom) { Rectangle().fill(HydraStyle.aqua).frame(height: 3).shadow(color: HydraStyle.aqua, radius: 12) }
                            .offset(y: 25 + (geometry.size.height - 115) * position)
                    }
                }
                .accessibilityHidden(true)
                Image(systemName: "viewfinder").font(.system(size: 100, weight: .ultraLight))
                    .foregroundStyle(HydraStyle.aqua).accessibilityHidden(true)
            } else if image == nil && !dynamicTypeSize.isAccessibilitySize {
                VStack { Spacer(); Text("BOTTLE, CUP, CAN. ALL WELCOME.").font(.system(.caption2, design: .rounded, weight: .bold)).tracking(1.4) }
                    .foregroundStyle(HydraStyle.aqua).padding(22)
            }
        }
        .frame(height: compact ? 160 : 320)
        .clipShape(RoundedRectangle(cornerRadius: 32))
    }
}

struct ScanCandidateCard: View {
    let candidate: RecognitionCandidate
    let onReview: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(candidate.identity).font(.system(.title2, design: .rounded, weight: .bold))
                    Text("\(candidate.confidence.capitalized) confidence · uncalibrated")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Image(systemName: "waterbottle.fill").font(.title).foregroundStyle(HydraStyle.teal)
            }
            LabeledContent("Estimated capacity", value: candidate.containerMl.map { "\($0) mL" } ?? "Unknown")
                .font(.subheadline)
            if let nutrition = candidate.nutrition {
                Divider()
                Text("Nutrition per \(nutrition.basisMl.formatted()) mL").font(.subheadline.bold())
                LabeledContent("Sodium", value: nutrition.sodiumMg.map { "\($0.formatted()) mg" } ?? "Unknown")
                LabeledContent("Carbohydrate", value: nutrition.carbohydrateG.map { "\($0.formatted()) g" } ?? "Unknown")
                ForEach(nutrition.provenance, id: \.self) { Text($0).font(.caption).foregroundStyle(.secondary) }
            } else {
                Text("Nutrition not verified").font(.footnote).foregroundStyle(.secondary)
            }
            ForEach(candidate.uncertaintyReasons, id: \.self) { Text($0).font(.caption).foregroundStyle(.secondary) }
            Button(action: onReview) {
                HStack { Text("Review & log"); Spacer(); Image(systemName: "arrow.right") }
            }
            .buttonStyle(HydraPressStyle())
            .accessibilityLabel("Review \(candidate.identity) (\(candidate.confidence) confidence)")
            .accessibilityIdentifier("recognitionCandidate-\(candidate.id.uuidString)")
        }.hydraCard()
    }
}
