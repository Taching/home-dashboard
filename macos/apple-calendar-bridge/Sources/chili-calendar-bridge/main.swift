import EventKit
import Foundation

enum BridgeError: LocalizedError {
    case missingEnvironment(String)
    case invalidDate(String)
    case calendarPermissionDenied
    case managedCalendarMissing(String)
    case invalidResponse

    var errorDescription: String? {
        switch self {
        case .missingEnvironment(let name): return "Missing required environment variable: \(name)"
        case .invalidDate(let value): return "CALENDAR_BRIDGE_TEST_DATE must use YYYY-MM-DD, received \(value)."
        case .calendarPermissionDenied: return "Calendar access was not granted. Run this command interactively and approve the macOS permission prompt."
        case .managedCalendarMissing(let name): return "Create a writable Google-backed calendar named \(name) and make it visible in Apple Calendar."
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
    let calendar_title: String
    let managed_session_id: String?
}

struct SyncPayload: Encodable {
    let synced_at: Date
    let events: [DashboardEvent]
}

struct ManagedPlan: Decodable {
    let calendar_name: String
    let events: [ManagedPlanEvent]
}

struct ManagedPlanEvent: Decodable {
    let session_id: String
    let title: String
    let start_at: Date
    let end_at: Date
    let is_all_day: Bool
    let notes: String
}

@main
struct ChiliCalendarBridge {
    static func main() async {
        do {
            let dashboardURL = try requiredEnvironment("DASHBOARD_URL")
            let token = try requiredEnvironment("CALENDAR_BRIDGE_TOKEN")
            let store = EKEventStore()
            try await authorize(store)
            do {
                let plan = try await fetchManagedPlan(dashboardURL: dashboardURL, token: token)
                try syncManagedEvents(plan, store: store)
            } catch {
                fputs("Training calendar write skipped: \(error.localizedDescription)\n", stderr)
            }
            let events = readEvents(store: store, from: try selectedDate(), days: 30)
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

    static func authorize(_ store: EKEventStore) async throws {
        if EKEventStore.authorizationStatus(for: .event) != .fullAccess {
            let granted = try await store.requestFullAccessToEvents()
            guard granted else { throw BridgeError.calendarPermissionDenied }
        }
    }

    static func readEvents(store: EKEventStore, from date: Date, days: Int) -> [DashboardEvent] {
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
                    is_all_day: $0.isAllDay,
                    calendar_title: $0.calendar.title,
                    managed_session_id: managedSessionID(from: $0.notes)
                )
            }
    }

    static func fetchManagedPlan(dashboardURL: String, token: String) async throws -> ManagedPlan {
        let base = dashboardURL.hasSuffix("/") ? String(dashboardURL.dropLast()) : dashboardURL
        guard let url = URL(string: base + "/api/v1/calendar/apple/training-plan") else {
            throw BridgeError.invalidResponse
        }
        var request = URLRequest(url: url)
        request.setValue(token, forHTTPHeaderField: "X-Chili-Bridge-Token")
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw BridgeError.invalidResponse
        }
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let value = try decoder.singleValueContainer().decode(String.self)
            let fractional = ISO8601DateFormatter()
            fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let date = fractional.date(from: value) { return date }
            let standard = ISO8601DateFormatter()
            guard let date = standard.date(from: value) else { throw BridgeError.invalidDate(value) }
            return date
        }
        return try decoder.decode(ManagedPlan.self, from: data)
    }

    static func syncManagedEvents(_ plan: ManagedPlan, store: EKEventStore) throws {
        let matches = store.calendars(for: .event).filter {
            $0.title == plan.calendar_name && $0.allowsContentModifications
        }
        guard matches.count == 1, let target = matches.first else {
            throw BridgeError.managedCalendarMissing(plan.calendar_name)
        }
        let calendar = Calendar.current
        let start = calendar.date(byAdding: .day, value: -1, to: Date())!
        let end = calendar.date(byAdding: .day, value: 60, to: Date())!
        let existing = store.events(matching: store.predicateForEvents(withStart: start, end: end, calendars: [target]))
            .filter { managedSessionID(from: $0.notes) != nil }
        var bySession: [String: [EKEvent]] = Dictionary(grouping: existing) {
            managedSessionID(from: $0.notes)!
        }
        let desiredIDs = Set(plan.events.map(\.session_id))
        for desired in plan.events {
            var copies = bySession.removeValue(forKey: desired.session_id) ?? []
            let event = copies.isEmpty ? EKEvent(eventStore: store) : copies.removeFirst()
            event.calendar = target
            event.title = desired.title
            event.startDate = desired.start_at
            event.endDate = desired.end_at
            event.isAllDay = desired.is_all_day
            event.notes = desired.notes
            try store.save(event, span: .thisEvent, commit: false)
            for duplicate in copies {
                try store.remove(duplicate, span: .thisEvent, commit: false)
            }
        }
        for (sessionID, events) in bySession where !desiredIDs.contains(sessionID) {
            for event in events where event.startDate >= start {
                try store.remove(event, span: .thisEvent, commit: false)
            }
        }
        try store.commit()
    }

    static func managedSessionID(from notes: String?) -> String? {
        guard let notes else { return nil }
        for line in notes.split(separator: "\n") {
            let value = String(line)
            if value.hasPrefix("chili-training:") {
                return String(value.dropFirst("chili-training:".count))
            }
        }
        return nil
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
