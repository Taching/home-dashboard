// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "ChiliCalendarBridge",
    platforms: [.macOS(.v14)],
    targets: [.executableTarget(name: "chili-calendar-bridge")]
)
