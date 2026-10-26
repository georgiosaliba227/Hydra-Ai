# Hydra AI iPhone client

Open `HydraAI.xcodeproj` in Xcode 27. The SwiftUI app targets iOS 17 or later. To build and test on the iPhone 17 Pro simulator:

```sh
xcodebuild -project ios/HydraAI.xcodeproj -scheme HydraAI \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro,OS=26.5' \
  CODE_SIGNING_ALLOWED=NO test
```

Manual logs use a local mock of the draft v1 `POST /v1/beverages` and `GET /v1/beverages` contract. The mock persists confirmed logs in this app's Application Support directory. It sends no network requests and has no Meta credentials. The app shows confirmed beverage volume; it does not calculate water content, fluid goals, retention, or forecasts.

Camera photos remain in memory, with explicit discard or handoff to manual entry. Photo recognition is unavailable in this build. HealthKit access is optional and initiated only from the Health tab; the current client reads a daily step total locally and does not upload Health records. A physical-device HealthKit test and signing profile are still needed. Before API integration, freeze the OpenAPI schema and review authentication, deletion, image consent, and transport policy with the backend owner.
