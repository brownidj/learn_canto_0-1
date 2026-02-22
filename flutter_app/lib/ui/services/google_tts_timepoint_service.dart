import 'dart:convert';
import 'package:http/http.dart' as http;

class GoogleTtsTimepointService {
  final String apiKey;

  GoogleTtsTimepointService(this.apiKey);

  Future<Map<String, dynamic>> synthesizeWithTimepoints({
    required String text,
    String languageCode = 'yue-HK',
    String? voiceName,
    double speakingRate = 1.0,
  }) async {
    final uri = Uri.parse('https://texttospeech.googleapis.com/v1/text:synthesize?key=$apiKey');
    final body = {
      'input': {
        'ssml': _buildSsml(text),
      },
      'voice': {
        'languageCode': languageCode,
        if (voiceName != null && voiceName.isNotEmpty) 'name': voiceName,
      },
      'audioConfig': {
        'audioEncoding': 'MP3',
        'speakingRate': speakingRate,
      },
      'enableTimePointing': ['SSML_MARK'],
    };

    final resp = await http.post(
      uri,
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(body),
    );
    if (resp.statusCode != 200) {
      throw StateError('TTS request failed: ${resp.statusCode} ${resp.body}');
    }
    return jsonDecode(resp.body) as Map<String, dynamic>;
  }

  String _buildSsml(String text) {
    final chars = text.split('');
    final buffer = StringBuffer('<speak>');
    for (var i = 0; i < chars.length; i++) {
      final ch = _escape(chars[i]);
      buffer.write("<mark name='s$i'/>$ch");
    }
    buffer.write('</speak>');
    return buffer.toString();
  }

  String _escape(String s) {
    return s
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;');
  }
}
