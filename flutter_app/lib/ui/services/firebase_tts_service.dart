import 'dart:convert';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:http/http.dart' as http;

class FirebaseTtsService {
  final Uri endpoint;

  FirebaseTtsService(this.endpoint);

  Future<String> _ensureToken() async {
    var user = FirebaseAuth.instance.currentUser;
    if (user == null) {
      try {
        await FirebaseAuth.instance.signInAnonymously();
      } on FirebaseAuthException catch (e) {
        throw StateError('Firebase auth failed: ${e.code} ${e.message}');
      }
      user = FirebaseAuth.instance.currentUser;
    }
    if (user == null) {
      throw StateError('No Firebase user after sign-in');
    }
    final token = await user.getIdToken();
    if (token == null || token.isEmpty) {
      throw StateError('Firebase token missing after sign-in');
    }
    return token;
  }

  Future<Map<String, dynamic>> synthesizeWithTimepoints({
    required String text,
    String? voiceName,
    int? rate,
  }) async {
    final token = await _ensureToken();
    final body = {
      'text': text,
      if (voiceName != null && voiceName.isNotEmpty) 'voice': voiceName,
      if (rate != null) 'rate': rate,
    };
    final resp = await http.post(
      endpoint,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $token',
      },
      body: jsonEncode(body),
    );
    if (resp.statusCode != 200) {
      throw StateError('Firebase TTS failed: ${resp.statusCode} ${resp.body}');
    }
    return jsonDecode(resp.body) as Map<String, dynamic>;
  }

  Future<List<Map<String, String>>> listVoices() async {
    final token = await _ensureToken();
    final voicesEndpoint = endpoint.replace(path: '/voices');
    final resp = await http.get(
      voicesEndpoint,
      headers: {
        'Authorization': 'Bearer $token',
      },
    );
    if (resp.statusCode != 200) {
      throw StateError('Firebase voices failed: ${resp.statusCode} ${resp.body}');
    }
    final data = jsonDecode(resp.body) as Map<String, dynamic>;
    final voices = data['voices'];
    if (voices is! List) {
      return [];
    }
    return voices.map<Map<String, String>>((v) {
      if (v is Map) {
        return v.map((k, val) => MapEntry(k.toString(), val.toString()));
      }
      return <String, String>{};
    }).where((v) => v.isNotEmpty).toList();
  }
}
