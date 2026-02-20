import 'dart:core';

final RegExp _syllableRe = RegExp(r'^[a-z]+[0-6]$', caseSensitive: false);

String normalizeJyutping(String? jy) {
  final text = (jy ?? '').trim().toLowerCase();
  return text.split(RegExp(r'\s+')).where((p) => p.isNotEmpty).join(' ');
}

List<String> _splitSyllables(String text) {
  final normalized = text.replaceAll('-', ' ');
  return normalized.split(RegExp(r'\s+')).where((p) => p.isNotEmpty).toList();
}

List<dynamic> validateJyutSyllables(String? jy) {
  if (jy == null) {
    return [false, 'Jyutping is missing'];
  }
  final text = jy.trim();
  if (text.isEmpty) {
    return [false, 'Jyutping is empty'];
  }
  final parts = _splitSyllables(text);
  if (parts.isEmpty) {
    return [false, 'Jyutping is empty'];
  }
  for (var i = 0; i < parts.length; i++) {
    final token = parts[i].trim();
    if (token.isEmpty) {
      continue;
    }
    if (token.contains(',') ||
        token.contains('.') ||
        token.contains(';') ||
        token.contains(':') ||
        token.contains('!') ||
        token.contains('?') ||
        token.contains('（') ||
        token.contains('）') ||
        token.contains('(') ||
        token.contains(')')) {
      return [false, 'Unexpected punctuation in syllable ${i + 1}: $token'];
    }

    if (RegExp(r'\d').hasMatch(token) && !_syllableRe.hasMatch(token)) {
      return [false, 'Tone digit must be at the end of syllable ${i + 1}: $token'];
    }

    if (!_syllableRe.hasMatch(token)) {
      if (RegExp(r'^[A-Za-z]+$').hasMatch(token)) {
        return [false, 'Missing tone digit (0–6) in syllable ${i + 1}: $token'];
      }
      return [false, 'Invalid Jyutping syllable ${i + 1}: $token'];
    }
  }
  return [true, null];
}
