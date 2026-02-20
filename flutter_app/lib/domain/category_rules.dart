bool isCategoryPlaceholder(dynamic category) {
  if (category == null || category is! String) {
    return true;
  }
  var catNorm = category.trim().toLowerCase();
  if (catNorm.isEmpty) {
    return true;
  }
  catNorm = catNorm.replaceAll('—', '-').replaceAll('–', '-');
  if (catNorm.contains('choose category')) {
    return true;
  }
  if (catNorm == '- choose category -' ||
      catNorm == 'choose category' ||
      catNorm == '-- choose category --') {
    return true;
  }
  return false;
}

bool saveEnabledGate({
  required dynamic jyut,
  required dynamic hanzi,
  required dynamic meanings,
  required dynamic category,
}) {
  if (jyut is! String || jyut.trim().isEmpty) {
    return false;
  }
  if (hanzi is! String || hanzi.trim().isEmpty) {
    return false;
  }
  if (meanings is! List || meanings.isEmpty) {
    return false;
  }
  final hasMeaning = meanings.any((m) => m is String && m.trim().isNotEmpty);
  if (!hasMeaning) {
    return false;
  }
  if (isCategoryPlaceholder(category)) {
    return false;
  }
  return true;
}

bool shouldShowCustomHanziButton(dynamic candidates) {
  if (candidates == null) {
    return true;
  }
  if (candidates is! List) {
    return true;
  }
  final usable =
      candidates.where((c) => c is String && c.trim().isNotEmpty).toList();
  return usable.isEmpty;
}

List<String> preferMeanings(dynamic primary, dynamic fallback) {
  List<String> out = [];
  if (primary is List) {
    out = primary
        .whereType<String>()
        .map((m) => m.trim())
        .where((m) => m.isNotEmpty)
        .toList();
  }
  if (out.isNotEmpty) {
    return out;
  }
  if (fallback is List) {
    return fallback
        .whereType<String>()
        .map((m) => m.trim())
        .where((m) => m.isNotEmpty)
        .toList();
  }
  return [];
}

bool detectAmbiguity({
  required dynamic candidates,
  required dynamic nSyllables,
  List<String> Function(String)? meaningsForHanzi,
}) {
  int n;
  try {
    if (nSyllables is int) {
      n = nSyllables;
    } else {
      n = int.parse(nSyllables.toString());
    }
  } catch (_) {
    n = 0;
  }

  List<dynamic> cands;
  if (candidates is List) {
    cands = candidates;
  } else if (candidates == null) {
    cands = [];
  } else {
    cands = [];
  }

  if (cands.length > 1) {
    return true;
  }
  if (n >= 2 && cands.isEmpty) {
    return true;
  }
  if (cands.length == 1 && meaningsForHanzi != null) {
    try {
      final only = cands[0];
      final hanzi =
          (only is List && only.isNotEmpty) ? only[0] : only;
      final glosses = meaningsForHanzi(hanzi.toString());
      final nonBlank =
          glosses.where((g) => g is String && g.trim().isNotEmpty).toList();
      if (nonBlank.length > 1) {
        return true;
      }
    } catch (_) {
      // ignore and do not force ambiguity
    }
  }
  return false;
}

String abbrForSource(String src) {
  final s = src.trim().toLowerCase();
  const mapping = {
    'cccanto': 'CC',
    'cedict': 'CE',
    'andys_list': 'AN',
    'builtin': 'BL',
    'hkcancor': 'HK',
    'subtitles': 'SUB',
    'pycantonese': 'PY',
    'reverse_manual': 'RM',
    'reverse_cache': 'RC',
    'tier2-char-ranked': 'T2',
    'tier2': 'T2',
  };
  if (mapping.containsKey(s)) {
    return mapping[s]!;
  }
  final s3 = s.replaceAll(RegExp(r'[^A-Za-z0-9]'), '').toUpperCase();
  final trimmed = s3.length > 3 ? s3.substring(0, 3) : s3;
  return trimmed.isNotEmpty ? trimmed : 'UNK';
}
