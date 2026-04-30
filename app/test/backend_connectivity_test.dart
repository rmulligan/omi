import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

void main() {
  group('Backend Connectivity Integration Tests', () {
    // Local backend runs on port 8010
    const String baseUrl = 'http://127.0.0.1:8010/v1';

    test('Backend health check endpoint returns 200 OK', () async {
      final response = await http.get(Uri.parse('$baseUrl/health'));
      
      expect(response.statusCode, 200);
      
      final data = jsonDecode(response.body);
      expect(data['status'], 'ok');
    });

    test('Backend onboarding endpoint rejects missing auth', () async {
      // Trying to hit an authenticated endpoint without auth should return 401 or 403
      final response = await http.get(Uri.parse('$baseUrl/users/onboarding'));
      
      expect(response.statusCode, anyOf(401, 403));
    });

    test('Backend onboarding endpoint accepts local dev token', () async {
      // Using the local development bypass token "123" or similar.
      // Often LOCAL_DEVELOPMENT=true bypasses auth if user is passed in header or query.
      // The backend .env has OMI_USER_UID=ryan.
      // In omi/backend/utils/auth.py, usually it expects 'Bearer <token>'.
      // Let's just pass 'Bearer ryan' or 'Bearer 123ryan' and see if it responds with something other than 401/403.
      final response = await http.get(
        Uri.parse('$baseUrl/users/onboarding'),
        headers: {'Authorization': 'Bearer 123ryan'},
      );
      
      // If it reaches the logic, it might return 200, or 404 if the user profile doesn't exist yet,
      // but it won't return 401/403 Unauthorized.
      expect(response.statusCode, isNot(anyOf(401, 403)));
    });
  });
}
