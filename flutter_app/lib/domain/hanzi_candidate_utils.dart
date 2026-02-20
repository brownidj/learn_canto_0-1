import 'hanzi_candidate_types.dart';

String normSpace(String text) {
  return text.split(RegExp(r'\s+')).where((p) => p.isNotEmpty).join(' ');
}

List<String> splitSyllables(String jyNorm) {
  final normed = normSpace(jyNorm);
  if (normed.isEmpty) {
    return [];
  }
  return normed.split(' ');
}

List<HanziCandidate> coerceCandidates(dynamic raw, String defaultSource) {
  if (raw == null) {
    return [];
  }
  final out = <HanziCandidate>[];
  if (raw is List) {
    for (final item in raw) {
      if (item is String && item.trim().isNotEmpty) {
        out.add(HanziCandidate(item.trim(), defaultSource, 0.0));
        continue;
      }
      if (item is List && item.isNotEmpty) {
        final h = item[0];
        if (h is! String || h.trim().isEmpty) {
          continue;
        }
        final hanzi = h.trim();
        var src = defaultSource;
        var freq = 0.0;

        if (item.length >= 2) {
          final v = item[1];
          if (v is String && v.trim().isNotEmpty) {
            src = v.trim();
          } else if (v is num) {
            freq = v.toDouble();
          }
        }

        if (item.length >= 3 && item[2] is num) {
          freq = (item[2] as num).toDouble();
        }

        out.add(HanziCandidate(hanzi, src, freq));
      }
    }
  }
  return out;
}

List<HanziCandidate> dedupeKeepFirst(List<HanziCandidate> cands) {
  final seen = <String>{};
  final out = <HanziCandidate>[];
  for (final c in cands) {
    if (seen.contains(c.hanzi)) {
      continue;
    }
    seen.add(c.hanzi);
    out.add(c);
  }
  return out;
}

List<HanziCandidate> simpleRank(List<HanziCandidate> cands) {
  final out = List<HanziCandidate>.from(cands);
  out.sort((a, b) {
    final freqCmp = b.freq.compareTo(a.freq);
    if (freqCmp != 0) {
      return freqCmp;
    }
    final srcCmp = a.source.compareTo(b.source);
    if (srcCmp != 0) {
      return srcCmp;
    }
    return a.hanzi.compareTo(b.hanzi);
  });
  return out;
}
