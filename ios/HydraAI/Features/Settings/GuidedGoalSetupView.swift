import SwiftUI
import UniformTypeIdentifiers

/// Manual profile answers stay on this iPhone. Only a separately confirmed integer goal uses the existing API.
struct GuidedGoalSetupView: View {
    @EnvironmentObject private var store: BeverageStore
    @EnvironmentObject private var units: DisplayUnits
    @ObservedObject var profileStore: GoalProfileStore
    @State private var draft = GoalSetupDraft()
    @State private var status: String?
    @State private var busy = false
    @State private var operation = UUID()
    @State private var submission: Task<Void, Never>?
    @State private var customGoal: Double?
    @State private var customInputValid = true
    @State private var export: ExportDocument?
    @State private var deletingCurrent = false
    @State private var deletingAll = false
    @State private var deletionGeneration: UUID?
    @State private var fieldReset = UUID()
    @FocusState private var focused: Bool

    var body: some View {
        Form {
            Section {
                Text("Set a starting beverage goal").font(.title2.bold()).accessibilityIdentifier("guidedGoalTitle")
                Text("Review an approximate published adult reference, then choose whether to use it. This is not a measured individual requirement, minimum intake, or a hydration-status test.")
                Text("These manual answers stay on this iPhone. No extra Apple Health access is needed.").font(.footnote)
            }
            profileQuestions.disabled(busy)
            bodyQuestions.disabled(busy)
            Section {
                Button("Calculate starting reference") { calculate() }
                    .accessibilityIdentifier("calculateGoalReference").disabled(busy)
                if let review = draft.currentReview { reviewSection(review) }
            }
            if let status { Section { Text(status).accessibilityIdentifier("goalApplyStatus") } }
            customSection.disabled(busy)
            localProfileSection
        }
        .navigationTitle("Guided goal setup")
        .toolbar {
            if focused { ToolbarItemGroup(placement: .keyboard) { Spacer(); Button("Done") { focused = false } } }
        }
        .onAppear { loadDraft() }
        .onChange(of: store.configurationGeneration) { _, _ in
            cancelSubmission(); deletingCurrent = false; deletingAll = false; deletionGeneration = nil; export = nil; loadDraft()
        }
        .onChange(of: units.system) { _, system in draft.switchHeightSystem(system) }
        .onChange(of: draft.inputRevision) { _, _ in status = nil }
        .onDisappear { cancelSubmission(); deletingCurrent = false; deletingAll = false; deletionGeneration = nil; export = nil }
        .fileExporter(isPresented: Binding(get: { export != nil }, set: { if !$0 { export = nil } }),
                      document: export, contentType: .json, defaultFilename: "hydra-goal-profile") { result in
            if case .failure = result { status = "Profile export was not saved." }
        }
        .confirmationDialog("Delete this connection's saved profile?", isPresented: $deletingCurrent, titleVisibility: .visible) {
            Button("Delete saved profile", role: .destructive) { deleteProfile(all: false) }
        } message: { Text("This deletes local answers for this connection and clears this form. Your confirmed backend goal and beverage records are unchanged.") }
        .confirmationDialog("Delete every saved goal profile on this iPhone?", isPresented: $deletingAll, titleVisibility: .visible) {
            Button("Delete all saved goal profiles", role: .destructive) { deleteProfile(all: true) }
        } message: { Text("This removes local goal profiles for every connection and clears this form. Backend goals and beverage records are unchanged. This cannot be undone.") }
    }

    private var profileQuestions: some View {
        Section {
            Picker("Age entry", selection: $draft.ageMethod) {
                Text("Birthday").tag(GoalSetupDraft.AgeMethod.birthday)
                Text("Age only").tag(GoalSetupDraft.AgeMethod.age)
            }.pickerStyle(.segmented).accessibilityIdentifier("profileAgeMethod")
            if draft.ageMethod == .birthday {
                TextField("Birthday (MM/DD/YYYY)", text: $draft.birthdayText)
                    .keyboardType(.numbersAndPunctuation).focused($focused).accessibilityIdentifier("profileBirthday")
                if let profile = try? draft.resolve(), let age = try? GoalProfileValidation.age(profile) {
                    Text("Age derived locally: \(age) years").font(.footnote).accessibilityIdentifier("profileDerivedAge")
                }
            } else {
                TextField("Self-entered age in years", text: $draft.ageText)
                    .keyboardType(.numberPad).focused($focused).accessibilityIdentifier("profileAgeYears")
                Text("Age-only answers stay as entered until you edit them.").font(.footnote)
            }
            Picker("Published reference group", selection: $draft.referenceGroup) {
                Text("Choose a group or custom goal").tag(nil as GoalReferenceGroup?)
                Text("Men (published reference)").tag(GoalReferenceGroup.men as GoalReferenceGroup?)
                Text("Women (published reference)").tag(GoalReferenceGroup.women as GoalReferenceGroup?)
                Text("Prefer not to say / custom goal").tag(GoalReferenceGroup.preferNotToSay as GoalReferenceGroup?)
            }.pickerStyle(.menu).accessibilityIdentifier("profileReferenceGroup")
            Text("Choose a source-table row explicitly. This does not infer your gender identity.").font(.footnote)
            Picker("Does this source apply?", selection: $draft.eligibility) {
                Text("Choose applicability").tag(nil as GoalEligibility?)
                Text("General adult reference applies").tag(GoalEligibility.generalAdult as GoalEligibility?)
                Text("Pregnant or breastfeeding").tag(GoalEligibility.pregnantOrBreastfeeding as GoalEligibility?)
                Text("Clinician-directed fluid management").tag(GoalEligibility.clinicianDirectedFluid as GoalEligibility?)
                Text("Unsure / custom goal").tag(GoalEligibility.unsure as GoalEligibility?)
            }.pickerStyle(.menu).accessibilityIdentifier("profileEligibility")
        } header: { Text("Age and source applicability") }
        footer: { Text("This source covers generally healthy adults aged 19 or older in ordinary conditions. Missing, excluded, or uncertain applicability uses the custom-goal path.") }
    }

    private var bodyQuestions: some View {
        Section {
            if units.system == .us {
                HStack {
                    TextField("Height — feet", text: Binding(get: { draft.heightFeetText }, set: { draft.editHeightFeet($0) }))
                        .keyboardType(.numberPad).focused($focused).accessibilityIdentifier("profileHeightFeet")
                    Text("ft").foregroundStyle(.secondary)
                    TextField("inches", text: Binding(get: { draft.heightInchesText }, set: { draft.editHeightInches($0) }))
                        .keyboardType(.decimalPad).focused($focused).accessibilityIdentifier("profileHeightInches")
                    Text("in").foregroundStyle(.secondary)
                }
            } else {
                HStack {
                    TextField("Height (optional)", text: Binding(get: { draft.heightCentimetersText }, set: { draft.editHeightCentimeters($0) }))
                        .keyboardType(.decimalPad).focused($focused).accessibilityIdentifier("profileHeightCm")
                    Text("cm").foregroundStyle(.secondary)
                }
            }
            if !draft.heightInputValid {
                Text("Correct or clear the invalid height entry before continuing, including text entered before switching units.").font(.footnote).foregroundStyle(.red)
                Button("Clear optional height") {
                    draft.editHeightCentimeters(""); draft.switchHeightSystem(units.system)
                }.accessibilityIdentifier("clearProfileHeight")
            }
            CanonicalQuantityField("Weight (optional)", value: $draft.weightKg, quantity: .mass,
                                   accessibilityIdentifier: "profileWeight", isInputValid: $draft.weightInputValid)
                .id(fieldReset)
            Toggle("Creatine", isOn: supplement(.creatine)).accessibilityIdentifier("profileCreatine")
            Toggle("Electrolyte supplements", isOn: supplement(.electrolytes)).accessibilityIdentifier("profileElectrolytes")
            Toggle("Other supplements", isOn: supplement(.other)).accessibilityIdentifier("profileOtherSupplement")
        } header: { Text("Optional body and supplement context") }
        footer: { Text("Height, weight, and supplements apply no numerical adjustment. There is no body-weight multiplier or creatine addition. Leave these fields empty if you prefer.") }
    }

    @ViewBuilder private func reviewSection(_ review: GoalSetupDraft.Review) -> some View {
        switch review.result {
        case .reference(let reference):
            Text("Starting beverage reference: approximately \(units.volume(reference.beverageMl)) per day")
                .font(.headline).accessibilityIdentifier("goalStartingReference")
            Text("Used to select the source row: age \(reference.ageYears) (19+), explicit published reference group, and general-adult applicability. Height, weight, and supplements are local context only: no numerical adjustment. No individualized workout or heat adjustment is included.")
                .font(.footnote).accessibilityIdentifier("goalReferenceContext")
            Text("Separate food-inclusive context: \(units.volume(reference.totalWaterMl)) total water per day includes water from food. That total is not the logged-beverage goal.").font(.footnote)
            Link("Source: National Academies (2005), Water, adult summaries pp. 145–150", destination: URL(string: reference.sourceURL)!).font(.footnote)
            Text("Choosing “Use as my goal” saves these profile answers on this iPhone and sends only the \(units.volume(reference.beverageMl)) goal to your configured Hydra backend. It does not send your profile to the backend or Meta.").font(.footnote)
            Button("Use as my goal") { useReference(review, reference: reference) }
                .accessibilityIdentifier("useGoalReference").disabled(busy || !profileStore.canSave || !store.isConfigured || store.isOffline)
        case .unavailable(let reason):
            Text(reason.message).accessibilityIdentifier("goalReferenceUnavailable")
            Text("Use the custom goal below. Optional height, weight, and supplements cannot make this reference applicable.").font(.footnote)
        }
    }

    private var customSection: some View {
        Section {
            HydraDisclosure(title: "Choose a custom goal instead", identifier: "guidedCustomAlternative") {
                CanonicalQuantityField("Custom beverage goal", value: $customGoal, quantity: .volume,
                                       accessibilityIdentifier: "guidedCustomGoal", isInputValid: $customInputValid)
                    .id(fieldReset)
                Text("Choose a goal from 100 to 10,000 mL (\(units.volume(100)) to \(units.volume(10000))). No profile answers are required. Confirmation sends only this goal to your Hydra backend.").font(.footnote)
                Button("Confirm custom goal") { confirmCustom() }
                    .disabled(busy || !customInputValid || CanonicalQuantityInput.wholeMilliliters(customGoal, range: 100...10_000) == nil || !store.isConfigured || store.isOffline)
                    .accessibilityIdentifier("guidedConfirmCustomGoal")
            }
        }
    }

    private var localProfileSection: some View {
        Section {
            Button("Save profile on this iPhone only") { saveProfile() }.disabled(busy || !profileStore.canSave)
                .accessibilityIdentifier("saveGoalProfileOnly")
            Button("Export saved profile answers (JSON)") {
                do { export = ExportDocument(data: try profileStore.exportData()); status = nil }
                catch { status = error.localizedDescription }
            }.disabled(busy || profileStore.profile == nil).accessibilityIdentifier("exportGoalProfile")
            Button("Delete this connection's saved profile", role: .destructive) {
                deletionGeneration = store.configurationGeneration; deletingCurrent = true
            }
                .disabled(busy).accessibilityIdentifier("deleteGoalProfile")
            Button("Delete all saved goal profiles", role: .destructive) {
                deletionGeneration = store.configurationGeneration; deletingAll = true
            }
                .disabled(busy).accessibilityIdentifier("deleteAllGoalProfiles")
            if let error = profileStore.errorMessage {
                Text(error).foregroundStyle(.red).font(.footnote)
                Button("Retry reading saved profile") {
                    do { try profileStore.reload(); loadDraft() } catch { status = error.localizedDescription }
                }.disabled(busy)
            }
        } header: { Text("Profile storage and privacy") }
        footer: {
            Text("Save is an explicit local-storage choice. Profiles are protected on this iPhone, excluded from backups, and separate for each backend connection. Export contains your birthday or age, body measurements, supplement, source-group, and applicability answers; choose where to save it. Local deletion does not delete a confirmed backend goal. Offline or unconfigured forms can calculate locally but cannot save profiles or confirm backend goals.")
        }
    }

    private func supplement(_ value: GoalSupplement) -> Binding<Bool> {
        Binding(get: { draft.supplements.contains(value) }, set: { selected in
            draft.supplements = GoalSupplement.allCases.filter { $0 == value ? selected : draft.supplements.contains($0) }
        })
    }
    private func loadDraft() { fieldReset = UUID(); draft.reset(profile: profileStore.profile); draft.switchHeightSystem(units.system); status = nil; customGoal = nil; customInputValid = true }
    private func calculate() {
        focused = false
        do { try draft.calculate(); status = nil } catch { status = error.localizedDescription }
    }
    private func saveProfile() {
        do { try profileStore.save(draft.resolve(), consent: true); status = "Profile saved on this iPhone only. Your backend goal was not changed by this action." }
        catch { status = error.localizedDescription }
    }
    private func deleteProfile(all: Bool) {
        guard deletionGeneration == store.configurationGeneration else { return }
        deletionGeneration = nil
        do {
            if all { try profileStore.deleteAll() } else { try profileStore.deleteCurrent() }
            loadDraft(); status = all ? "All local goal profiles deleted. Backend goals remain separate." : "Local profile deleted. Backend goal remains separate."
        } catch { status = error.localizedDescription }
    }
    private func useReference(_ review: GoalSetupDraft.Review, reference: GoalStartingReference) {
        guard !busy, draft.currentReview == review else { return }
        // Capture the reviewed candidate and connection synchronously at the tap, before creating a task.
        let generation = store.configurationGeneration, revision = draft.inputRevision
        let candidate = review.profile, goal = reference.beverageMl, ticket = UUID()
        operation = ticket; busy = true; status = "Saving profile and requesting goal confirmation…"
        submission = Task { @MainActor in
            defer { if operation == ticket { busy = false; submission = nil } }
            guard isCurrent(ticket, generation: generation), revision == draft.inputRevision, draft.currentReview == review else { return }
            do { try profileStore.save(candidate, consent: true) }
            catch {
                if isCurrent(ticket, generation: generation) { status = "Profile could not be saved. \(error.localizedDescription)"; busy = false }
                return
            }
            await submit(goal, ticket: ticket, generation: generation, revision: revision, savedProfile: true)
        }
    }
    private func confirmCustom() {
        guard !busy, customInputValid, let goal = CanonicalQuantityInput.wholeMilliliters(customGoal, range: 100...10_000) else { return }
        let generation = store.configurationGeneration, ticket = UUID()
        operation = ticket; busy = true; status = "Requesting custom goal confirmation…"
        submission = Task { @MainActor in
            defer { if operation == ticket { busy = false; submission = nil } }
            await submit(goal, ticket: ticket, generation: generation, revision: nil, savedProfile: false)
        }
    }
    private func submit(_ goal: Int, ticket: UUID, generation: UUID, revision: Int?, savedProfile: Bool) async {
        guard isCurrent(ticket, generation: generation), revision == nil || revision == draft.inputRevision else { return }
        do {
            try await store.setGoal(goal)
            guard isCurrent(ticket, generation: generation), revision == nil || revision == draft.inputRevision else { return }
            status = "Goal confirmed: \(units.volume(goal)) per day." + (savedProfile ? " Profile answers are saved only on this iPhone." : "")
        } catch {
            guard isCurrent(ticket, generation: generation), revision == nil || revision == draft.inputRevision else { return }
            status = "Goal confirmation failed. The server may have accepted the change; check your connection and current goal before trying again." + (savedProfile ? " Your local profile is preserved." : "")
        }
        if operation == ticket { busy = false; submission = nil }
    }
    private func isCurrent(_ ticket: UUID, generation: UUID) -> Bool {
        !Task.isCancelled && operation == ticket && generation == store.configurationGeneration
    }
    private func cancelSubmission() { submission?.cancel(); submission = nil; operation = UUID(); busy = false; status = nil }
}
