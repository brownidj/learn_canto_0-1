List<String> _cleanList(dynamic xs) {
  if (xs is! List) {
    return [];
  }
  final out = <String>[];
  for (final x in xs) {
    if (x is String) {
      final s = x.trim();
      if (s.isNotEmpty) {
        out.add(s);
      }
    }
  }
  return out;
}

List<String> cleanGlossesForDisplay(dynamic glosses) {
  if (glosses is List) {
    return _cleanList(glosses);
  }
  return [];
}
