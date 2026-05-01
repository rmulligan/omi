import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

void main() {
  group('Lilly Omnimodal Ingestion Integration Tests', () {
    const String baseUrl = 'http://127.0.0.1:8010/v1';
    final Map<String, String> authHeaders = {
      'Authorization': 'Bearer 123ryan',
      'Content-Type': 'application/json',
    };

    test('1. Ingest Matrix Message', () async {
      final response = await http.post(
        Uri.parse('$baseUrl/lilly/ingest'),
        headers: authHeaders,
        body: jsonEncode({
          'source': 'matrix',
          'category': 'communication',
          'text': 'Lilly, remember that we have a meeting with the design team on Friday at 2 PM to discuss the new omnimodal pipeline.',
          'title': 'Matrix: Design Meeting',
          'metadata': {
            'room_id': '!abc:matrix.org',
            'sender': '@ryan:matrix.org',
          }
        }),
      );

      expect(response.statusCode, 200);
      final data = jsonDecode(response.body);
      expect(data['conversation']['source'], 'matrix');
      expect(data['conversation']['structured']['category'], 'communication');
    });

    test('2. Ingest Photo with Description', () async {
      const String pixel = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+nz1sAAAAASUVORK5CYII=';
      
      final response = await http.post(
        Uri.parse('$baseUrl/lilly/ingest'),
        headers: authHeaders,
        body: jsonEncode({
          'source': 'photo_share',
          'category': 'media',
          'text': 'A photo of a whiteboard containing the architecture diagram for the Lilly app.',
          'base64_photos': [pixel],
          'title': 'Shared Photo: Architecture',
        }),
      );

      expect(response.statusCode, 200);
      final data = jsonDecode(response.body);
      expect(data['conversation']['photos'].length, 1);
      expect(data['conversation']['source'], 'photo_share');
    });

    test('3. Ingest Watchdog Error', () async {
      final response = await http.post(
        Uri.parse('$baseUrl/lilly/ingest'),
        headers: authHeaders,
        body: jsonEncode({
          'source': 'watchdog_error',
          'category': 'system',
          'text': 'Service "VoiceCollector" failed to heartbeat for 60 seconds. Attempting automatic restart.',
          'title': 'System Error: VoiceCollector',
          'metadata': {
            'service': 'VoiceCollector',
            'severity': 'critical',
          }
        }),
      );

      expect(response.statusCode, 200);
      final data = jsonDecode(response.body);
      expect(data['conversation']['source'], 'watchdog_error');
    });
  });
}