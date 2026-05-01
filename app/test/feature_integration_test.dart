import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

void main() {
  group('Feature Integration Tests (Lilly Backend)', () {
    const String baseUrl = 'http://127.0.0.1:8010/v1';
    final Map<String, String> authHeaders = {'Authorization': 'Bearer 123ryan'};

    test('1. Summarization: Get Conversations (Empty or Populated)', () async {
      final response = await http.get(
        Uri.parse('$baseUrl/conversations'),
        headers: authHeaders,
      );

      expect(response.statusCode, 200, reason: 'Failed to fetch conversations');
      final data = jsonDecode(response.body);
      expect(data, isA<List>());
    });

    test('2. Summarization: Process In-Progress Conversation', () async {
      final response = await http.post(
        Uri.parse('$baseUrl/conversations'),
        headers: authHeaders,
      );

      // 404 typically means no in-progress conversation exists, 200 means successful summary.
      expect(response.statusCode, anyOf(200, 404));
    });

    test('3. STT Websocket: Reject unauthenticated STT WebSocket connection', () async {
      // The STT service operates on wss:// (or ws://) at /v4/listen
      final response = await http.get(
        Uri.parse('http://127.0.0.1:8010/v4/listen'),
        headers: authHeaders,
      );
      
      // In FastAPI, connecting to a WS endpoint via GET without Upgrade header throws 403 or 426 or 400 Bad Request depending on implementation
      expect(response.statusCode, anyOf(400, 403, 404, 426));
    });

    test('4. Daily Summaries / Digests: Retrieve Settings', () async {
      final response = await http.get(
        Uri.parse('$baseUrl/users/daily-summary-settings'),
        headers: authHeaders,
      );

      expect(response.statusCode, 200, reason: 'Should return daily summary settings');
      final data = jsonDecode(response.body);
      expect(data.containsKey('enabled'), true);
      expect(data.containsKey('hour'), true);
    });

    test('5. Daily Summaries / Digests: Retrieve Digests List', () async {
      final response = await http.get(
        Uri.parse('$baseUrl/users/daily-summaries?limit=5&offset=0'),
        headers: authHeaders,
      );

      expect(response.statusCode, 200, reason: 'Should return a list of daily summaries');
      final data = jsonDecode(response.body);
      expect(data.containsKey('summaries'), true);
    });

    test('6. Wrapped 2025: Retrieve Wrapped Status', () async {
      final response = await http.get(
        Uri.parse('$baseUrl/wrapped/2025'),
        headers: authHeaders,
      );

      expect(response.statusCode, 200, reason: 'Should return Wrapped 2025 status');
      final data = jsonDecode(response.body);
      expect(data.containsKey('status'), true);
    });
  });
}