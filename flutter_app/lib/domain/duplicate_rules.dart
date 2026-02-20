String _defaultNorm(String x) {
  return x.trim().toLowerCase().split(RegExp(r'\s+')).where((p) => p.isNotEmpty).join(' ');
}

String Function(String) _normFn(String Function(String)? normalize) {
  return normalize ?? _defaultNorm;
}

Map<String, dynamic>? _asEntriesMapping(dynamic vocab) {
  if (vocab is! Map) {
    return null;
  }
  final entries = vocab['entries'];
  if (entries is Map) {
    return Map<String, dynamic>.from(entries);
  }

  // Tolerant: sometimes callers pass entries directly.
  final sample = vocab.entries.take(5).toList();
  var looksLikeEntries = false;
  for (final kv in sample) {
    final v = kv.value;
    if (v is Map && (v.containsKey('senses') || v.containsKey('jyutping') || v.containsKey('headword') || v.containsKey('hanzi'))) {
      looksLikeEntries = true;
      break;
    }
  }
  if (looksLikeEntries) {
    return Map<String, dynamic>.from(vocab);
  }
  return null;
}

bool _legacyHanziKeyed(dynamic vocab) {
  if (vocab is! Map || vocab.isEmpty) {
    return false;
  }
  final firstKey = vocab.keys.first;
  final firstVal = vocab[firstKey];
  if (firstKey is! String) {
    return false;
  }
  return firstVal is List;
}

bool isDuplicateJy(
  String jy, {
  dynamic reverseIndex,
  dynamic vocab,
  String Function(String)? normalize,
}) {
  try {
    final jyS = (jy).trim();
    if (jyS.isEmpty || vocab == null) {
      return false;
    }
    final norm = _normFn(normalize);
    final jyN = norm(jyS);

    final entries = _asEntriesMapping(vocab);
    if (entries != null) {
      if (entries.containsKey(jyS)) {
        return true;
      }
      for (final k in entries.keys) {
        if (norm(k.toString()) == jyN) {
          return true;
        }
      }
      return false;
    }

    if (_legacyHanziKeyed(vocab)) {
      for (final kv in vocab.entries) {
        final val = kv.value;
        if (val is List && val.length > 1) {
          final vjy = val[1]?.toString() ?? '';
          if (norm(vjy) == jyN) {
            return true;
          }
        }
      }
    }

    return false;
  } catch (_) {
    return false;
  }
}

bool isExactDuplicateEntry(
  dynamic vocab,
  String jy,
  String hz, {
  String Function(String)? normalize,
}) {
  try {
    final hzS = hz.trim();
    final jyS = jy.trim();
    if (hzS.isEmpty || jyS.isEmpty) {
      return false;
    }
    final norm = _normFn(normalize);
    final jyN = norm(jyS);

    final entries = _asEntriesMapping(vocab);
    if (entries != null) {
      dynamic entry;
      if (entries.containsKey(jyS)) {
        entry = entries[jyS];
      } else {
        for (final kv in entries.entries) {
          if (norm(kv.key.toString()) == jyN) {
            entry = kv.value;
            break;
          }
        }
      }
      if (entry is! Map) {
        return false;
      }
      final head = (entry['headword'] ?? entry['hanzi'] ?? entry['hz'] ?? '').toString();
      if (head.trim().isNotEmpty && head.trim() == hzS) {
        return true;
      }
      final senses = entry['senses'];
      if (senses is List) {
        for (final s in senses) {
          if (s is Map) {
            final shz = (s['hanzi'] ?? '').toString().trim();
            if (shz.isNotEmpty && shz == hzS) {
              return true;
            }
          }
        }
      }
      return false;
    }

    if (vocab is! Map) {
      return false;
    }
    final val = vocab[hzS];
    if (val is! List || val.length < 2) {
      return false;
    }
    final vjy = val[1]?.toString() ?? '';
    return norm(vjy) == jyN;
  } catch (_) {
    return false;
  }
}
