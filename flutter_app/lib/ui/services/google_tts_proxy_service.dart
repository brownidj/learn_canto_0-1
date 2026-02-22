import 'dart:convert';
import 'package:http/http.dart' as http;

class GoogleTtsProxyService {
  final Uri endpoint;

  GoogleTtsProxyService(this.endpoint);

  Uri get voicesEndpoint => endpoint.replace(path: '/voices');

  Future<Map<String, dynamic>> synthesizeWithTimepoints({
    required String text,
    String? voiceName,
    int? rate,
  }) async {
    final body = {
      'text': text,
      if (voiceName != null && voiceName.isNotEmpty) 'voice': voiceName,
      if (rate != null) 'rate': rate,
    };
    final resp = await http.post(
      endpoint,
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(body),
    );
    if (resp.statusCode != 200) {
      throw StateError('TTS proxy failed: ${resp.statusCode} ${resp.body}');
    }
    try {
      return jsonDecode(resp.body) as Map<String, dynamic>;
    } catch (e) {
      throw StateError('TTS proxy invalid JSON: $e body=${resp.body}');
    }
  }

  Future<List<Map<String, String>>> listVoices() async {
    final resp = await http.get(voicesEndpoint);
    if (resp.statusCode != 200) {
      throw StateError('TTS proxy voices failed: ${resp.statusCode} ${resp.body}');
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
