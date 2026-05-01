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
          'text': 'Lilly, remember that we have a meeting with the design team on Friday at 2 PM.',
          'title': 'Matrix: Design Meeting',
        }),
      );
      expect(response.statusCode, 200);
    });

    test('2. Ingest Photo', () async {
      const String pixel = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+nz1sAAAAASUVORK5CYII=';
      final response = await http.post(
        Uri.parse('$baseUrl/lilly/ingest'),
        headers: authHeaders,
        body: jsonEncode({
          'source': 'photo_share',
          'category': 'media',
          'text': 'A photo of a whiteboard.',
          'base64_photos': [pixel],
        }),
      );
      expect(response.statusCode, 200);
    });

    test('3. Ingest Watchdog Error', () async {
      final response = await http.post(
        Uri.parse('$baseUrl/lilly/ingest'),
        headers: authHeaders,
        body: jsonEncode({
          'source': 'watchdog_error',
          'category': 'system',
          'text': 'Service failure detected.',
        }),
      );
      expect(response.statusCode, 200);
    });

    test('4. Ingest LinkedIn', () async {
      final response = await http.post(
        Uri.parse('$baseUrl/lilly/ingest'),
        headers: authHeaders,
        body: jsonEncode({
          'source': 'linkedin',
          'category': 'communication',
          'text': 'New connection request.',
        }),
      );
      expect(response.statusCode, 200);
    });

    test('5. Ingest Zotero Learning', () async {
      final response = await http.post(
        Uri.parse('$baseUrl/lilly/ingest'),
        headers: authHeaders,
        body: jsonEncode({
          'source': 'zotero',
          'category': 'research',
          'text': 'Added new research paper.',
        }),
      );
      expect(response.statusCode, 200);
    });

    test('6. Ingest Skill Event', () async {
      final response = await http.post(
        Uri.parse('$baseUrl/lilly/ingest'),
        headers: authHeaders,
        body: jsonEncode({
          'source': 'skill_event',
          'category': 'internal',
          'text': 'Skill updated successfully.',
        }),
      );
      expect(response.statusCode, 200);
    });

    test('7. Ingest Google Drive Handwritten Note', () async {
      final response = await http.post(
        Uri.parse('$baseUrl/lilly/ingest'),
        headers: authHeaders,
        body: jsonEncode({
          'source': 'google_drive',
          'category': 'other',
          'text': 'Handwritten note captured from Google Drive. Content: "Buy more sensors for the lab, check voltage on battery array B, and call Sarah about the silicon shipment."',
          'title': 'Google Drive: Handwritten Note',
          'metadata': {
            'file_id': 'drive_file_123',
            'mime_type': 'image/jpeg',
          }
        }),
      );

      expect(response.statusCode, 200);
      final data = jsonDecode(response.body);
      expect(data['conversation']['source'], 'google_drive');
    });
  });
}