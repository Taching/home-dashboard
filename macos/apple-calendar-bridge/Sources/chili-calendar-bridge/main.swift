import EventKit
import Foundation

enum BridgeError: LocalizedError {
    case missingEnvironment(String)
    case invalidDate(String)
    case calendarPermissionDenied
    case invalidResponse

    var errorDescription: String? {
        switch self {
        case .missingEnvironment(let name): return "Missing required environment variable: \(name)"
        case .invalidDate(let value): return "CALENDAR_BRIDGE_TEST_DATE must use YYYY-MM-DD, received \(value)."
        case .calendarPermissionDenied: return "Calendar access was not granted. Run this command interactively and approve the macOS permission prompt."
        case .invalidResponse: return "The dashboard rejected the calendar sync. Check the URL and bridge token."
        }
    }
}

struct DashboardEvent: Encodable {
    let id: String
    let title: String
    let start_at: Date
    let end_at: Date
    let is_all_day: Bool
}

struct SyncPayload: Encodable {
    let synced_at: Date
    let events: [DashboardEvent]
}

@main
struct ChiliCalendarBridge {
    static func main() async {
        do {
            let dashboardURL = try requiredEnvironment("DASHBOARD_URL")
            let token = try requiredEnvironment("CALENDAR_BRIDGE_TOKEN")
            let events = try await readEvents(from: try selectedDate(), days: 30)
            try await upload(
                payload: SyncPayload(synced_at: Date(), events: events),
                dashboardURL: dashboardURL,
                token: token
            )
            print("Synced \(events.count) Apple Calendar events.")
        } catch {
            fputs("Calendar bridge failed: \(error.localizedDescription)\n", stderr)
            Foundation.exit(1)
        }
    }

    static func requiredEnvironment(_ name: String) throws -> String {
        guard let value = ProcessInfo.processInfo.environment[name], !value.isEmpty else {
            throw BridgeError.missingEnvironment(name)
        }
        return value
    }

    static func selectedDate() throws -> Date {
        guard let value = ProcessInfo.processInfo.environment["CALENDAR_BRIDGE_TEST_DATE"], !value.isEmpty else {
            return Date()
        }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = Calendar.current.timeZone
        formatter.dateFormat = "yyyy-MM-dd"
        guard let date = formatter.date(from: value) else { throw BridgeError.invalidDate(value) }
        return date
    }

    static func readEvents(from date: Date, days: Int) async throws -> [DashboardEvent] {
        let store = EKEventStore()
        if EKEventStore.authorizationStatus(for: .event) != .fullAccess {
            let granted = try await store.requestFullAccessToEvents()
            guard granted else { throw BridgeError.calendarPermissionDenied }
        }

        let calendar = Calendar.current
        let start = calendar.startOfDay(for: date)
        let end = calendar.date(byAdding: .day, value: days, to: start)!
        let predicate = store.predicateForEvents(withStart: start, end: end, calendars: nil)
        return store.events(matching: predicate)
            .sorted { $0.startDate < $1.startDate }
            .map {
                let trimmedTitle = $0.title?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                return DashboardEvent(
                    id: $0.eventIdentifier,
                    title: trimmedTitle.isEmpty ? "Untitled event" : trimmedTitle,
                    start_at: $0.startDate,
                    end_at: $0.endDate,
                    is_all_day: $0.isAllDay
                )
            }
    }

    static func upload(payload: SyncPayload, dashboardURL: String, token: String) async throws {
        let base = dashboardURL.hasSuffix("/") ? String(dashboardURL.dropLast()) : dashboardURL
        guard let url = URL(string: base + "/api/v1/calendar/apple/sync") else {
            throw BridgeError.invalidResponse
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(token, forHTTPHeaderField: "X-Chili-Bridge-Token")
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        request.httpBody = try encoder.encode(payload)
        let (_, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 204 else {
            throw BridgeError.invalidResponse
        }
    }
}
