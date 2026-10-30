import SwiftUI
import UIKit

// MARK: - Design tokens
// One tint, one card style, one spacing scale. Every screen uses these so the app reads as one product.

extension Color {
    /// Teal-blue tint. Both variants keep at least 4.5:1 against their background and against white button text.
    static let hydraTint = Color(UIColor { traits in
        traits.userInterfaceStyle == .dark
            ? UIColor(red: 0.12, green: 0.56, blue: 0.71, alpha: 1)
            : UIColor(red: 0.00, green: 0.48, blue: 0.60, alpha: 1)
    })
    static let hydraBackground = Color(.systemGroupedBackground)
    static let hydraCard = Color(.secondarySystemGroupedBackground)
}

enum HydraSpacing {
    /// Between cards on a screen.
    static let section: CGFloat = 20
    /// Inside a card.
    static let item: CGFloat = 12
    static let cardPadding: CGFloat = 16
    static let cornerRadius: CGFloat = 22
}

struct HydraCardModifier: ViewModifier {
    var padding: CGFloat = HydraSpacing.cardPadding

    func body(content: Content) -> some View {
        content
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(padding)
            .background(Color.hydraCard, in: RoundedRectangle(cornerRadius: HydraSpacing.cornerRadius, style: .continuous))
    }
}

extension View {
    /// The single card style used across the app.
    func hydraCard(padding: CGFloat = HydraSpacing.cardPadding) -> some View {
        modifier(HydraCardModifier(padding: padding))
    }

    /// Scrollable screen of cards on the grouped background.
    func hydraScreen() -> some View {
        self
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
    }
}

// MARK: - Building blocks

/// Rounded tinted square holding an SF Symbol, used for rows and feature cards.
struct IconBadge: View {
    let systemName: String
    var tint: Color = .hydraTint
    @ScaledMetric(relativeTo: .body) private var size: CGFloat = 36

    var body: some View {
        Image(systemName: systemName)
            .font(.system(size: size * 0.48, weight: .semibold))
            .foregroundStyle(tint)
            .frame(width: size, height: size)
            .background(tint.opacity(0.14), in: RoundedRectangle(cornerRadius: size * 0.28, style: .continuous))
            .accessibilityHidden(true)
    }
}

/// Title above a group of cards.
struct SectionTitle: View {
    let text: String
    var trailing: String? = nil

    init(_ text: String, trailing: String? = nil) {
        self.text = text
        self.trailing = trailing
    }

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(text).font(.title3.bold())
                .accessibilityAddTraits(.isHeader)
            Spacer()
            if let trailing {
                Text(trailing).font(.subheadline).foregroundStyle(.secondary)
            }
        }
        .padding(.top, 4)
    }
}

/// Small secondary note with an info glyph. Used for required statements so they stay present but quiet.
struct InfoNote: View {
    let text: String
    var systemImage = "info.circle"

    init(_ text: String, systemImage: String = "info.circle") {
        self.text = text
        self.systemImage = systemImage
    }

    var body: some View {
        Label {
            Text(text).fixedSize(horizontal: false, vertical: true)
        } icon: {
            Image(systemName: systemImage).accessibilityHidden(true)
        }
        .font(.footnote)
        .foregroundStyle(.secondary)
        .labelStyle(.titleAndIcon)
    }
}

/// A navigation row for an AI feature: icon, title, one-line description, chevron.
struct FeatureRow: View {
    let title: String
    let subtitle: String
    let systemImage: String
    var badge: String? = nil

    var body: some View {
        HStack(spacing: 14) {
            IconBadge(systemName: systemImage)
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(title).font(.headline).foregroundStyle(.primary)
                    if let badge {
                        Text(badge)
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(Color.hydraTint)
                            .padding(.horizontal, 6).padding(.vertical, 2)
                            .background(Color.hydraTint.opacity(0.12), in: Capsule())
                    }
                }
                Text(subtitle)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 8)
            Image(systemName: "chevron.right")
                .font(.footnote.weight(.semibold))
                .foregroundStyle(.tertiary)
                .accessibilityHidden(true)
        }
        .frame(minHeight: 44)
        .padding(.vertical, 6)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }
}

/// Collapsed-by-default disclosure built from a plain button, so it behaves the same inside
/// scroll views and forms and its button keeps a stable accessibility identifier.
struct HydraDisclosure<Content: View>: View {
    let title: String
    var systemImage: String = "info.circle"
    var identifier: String? = nil
    @ViewBuilder var content: () -> Content
    @State private var expanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Button {
                withAnimation(.snappy) { expanded.toggle() }
            } label: {
                HStack {
                    Label(title, systemImage: systemImage)
                        .font(.subheadline.weight(.medium))
                    Spacer()
                    Image(systemName: "chevron.down")
                        .font(.footnote.weight(.semibold))
                        .rotationEffect(.degrees(expanded ? 0 : -90))
                        .accessibilityHidden(true)
                }
                .frame(minHeight: 44)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .foregroundStyle(.secondary)
            .accessibilityValue(expanded ? "Expanded" : "Collapsed")
            .accessibilityHint(expanded ? "Hides the details" : "Shows the details")
            .modifier(OptionalIdentifier(identifier: identifier))
            if expanded {
                VStack(alignment: .leading, spacing: 6) { content() }
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .transition(.opacity)
            }
        }
    }
}

private struct OptionalIdentifier: ViewModifier {
    let identifier: String?
    func body(content: Content) -> some View {
        if let identifier { content.accessibilityIdentifier(identifier) } else { content }
    }
}

/// One labelled fact inside "How this was made".
struct ProvenanceLine: View {
    let label: String
    let value: String

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(label)
            Spacer(minLength: 12)
            Text(value).multilineTextAlignment(.trailing).foregroundStyle(.primary)
        }
        .font(.footnote)
        .accessibilityElement(children: .combine)
    }
}

/// Numbered step header for guided flows.
struct StepHeader: View {
    let number: Int
    let title: String

    var body: some View {
        HStack(spacing: 8) {
            Text("\(number)")
                .font(.caption.bold())
                .foregroundStyle(.white)
                .frame(minWidth: 20, minHeight: 20)
                .background(Color.hydraTint, in: Circle())
                .accessibilityHidden(true)
            Text(title)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Step \(number), \(title)")
        .accessibilityAddTraits(.isHeader)
    }
}

/// Banner for errors, pending saves and connection hints.
struct StatusBanner<Actions: View>: View {
    let text: String
    var systemImage = "exclamationmark.triangle.fill"
    var tint: Color = .orange
    @ViewBuilder var actions: () -> Actions

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label {
                Text(text).fixedSize(horizontal: false, vertical: true)
            } icon: {
                Image(systemName: systemImage).foregroundStyle(tint)
            }
            .font(.subheadline)
            actions()
        }
        .hydraCard()
    }
}

extension StatusBanner where Actions == EmptyView {
    init(text: String, systemImage: String = "exclamationmark.triangle.fill", tint: Color = .orange) {
        self.init(text: text, systemImage: systemImage, tint: tint) { EmptyView() }
    }
}

// MARK: - Beverage presentation

enum BeverageStyle {
    static func symbol(for category: String) -> String {
        let name = category.lowercased()
        if name.contains("coffee") || name.contains("espresso") { return "cup.and.saucer.fill" }
        if name.contains("tea") { return "leaf.fill" }
        if name.contains("milk") { return "mug.fill" }
        if name.contains("juice") { return "carrot.fill" }
        if name.contains("soda") || name.contains("cola") { return "takeoutbag.and.cup.and.straw.fill" }
        if name.contains("sport") { return "bolt.fill" }
        if name.contains("water") { return "drop.fill" }
        return "waterbottle.fill"
    }
}

// MARK: - Formatting

enum HydraFormat {
    static func milliliters(_ value: Double) -> String {
        value.formatted(.number.precision(.fractionLength(0...1)))
    }

    static func usd(micro: Double) -> String {
        "$" + (micro / 1_000_000).formatted(.number.precision(.fractionLength(4)))
    }
}
