import 'dart:core';

typedef MeaningsForHanzi = List<String> Function(String);

List<List<dynamic>> rerankCandidatesWithMeanings(
  List<dynamic> cands, {
  required MeaningsForHanzi meaningsForHanzi,
  String activeCategory = '',
  Map<String, Map<String, double>>? categoryProfiles,
  Map<String, num>? hkFreqMap,
  Set<String>? hkColloquial,
  Set<String>? hkAttested,
}) {
  final activeCat = activeCategory.trim();
  final profiles = categoryProfiles ?? {};
  final tokenRe = RegExp(r'[a-z]+');

  double categoryScoreForGlosses(List<String> glosses, String catName) {
    if (catName.isEmpty) {
      return 0.0;
    }
    final kw = profiles[catName] ?? profiles[catName.toLowerCase()];
    if (kw == null || kw.isEmpty) {
      return 0.0;
    }
    final seen = <String>{};
    var score = 0.0;
    for (final g in glosses) {
      final text = g.toLowerCase();
      for (final match in tokenRe.allMatches(text)) {
        final tok = match.group(0);
        if (tok == null) {
          continue;
        }
        if (seen.contains(tok)) {
          continue;
        }
        seen.add(tok);
        final v = kw[tok] ?? 0.0;
        score += v;
      }
    }
    return score;
  }

  int sourceScore(String src) {
    final order = [
      'andys_list',
      'builtin',
      'hkcancor',
      'subtitles',
      'cccanto',
      'pycantonese',
      'tier2-char-ranked',
      'tier2',
      'tier2-char',
      'tier1',
    ];
    final idx = order.indexOf(src);
    if (idx < 0) {
      return 0;
    }
    return order.length - idx;
  }

  List<List<String>> splitClean(List<String> glosses) {
    final clean = <String>[];
    final tagged = <String>[];
    for (final g in glosses) {
      final s = g;
      if ((s.contains('[') && s.contains(']')) || (s.contains('(') && s.contains(')'))) {
        tagged.add(s);
      } else {
        clean.add(s);
      }
    }
    return [clean, tagged];
  }

  int registerScoreFromResolvedGlosses(List<String> glosses) {
    if (glosses.isEmpty) {
      return 1;
    }
    final text = glosses.join(' ').toLowerCase();
    final yueMarkers = ['[yue]', '[粵]', '[粵語]', ' cantonese ', '(cantonese)', '(colloquial)'];
    final litMarkers = ['[lit]', ' literary ', '(literary)', '(written)'];
    final isYue = yueMarkers.any((m) => text.contains(m));
    final isLit = litMarkers.any((m) => text.contains(m));
    if (isYue && !isLit) {
      return 2;
    }
    if (isYue && isLit) {
      return 2;
    }
    if (!isYue && isLit) {
      return 0;
    }
    return 1;
  }

  final hasHk = (hkFreqMap != null && hkFreqMap.isNotEmpty) ||
      (hkColloquial != null && hkColloquial.isNotEmpty) ||
      (hkAttested != null && hkAttested.isNotEmpty);
  final hkFreq = hkFreqMap ?? {};
  final hkCol = hkColloquial ?? <String>{};
  final hkAtt = hkAttested ?? <String>{};

  final scored = <List<dynamic>>[];

  for (final item in cands) {
    if (item is! List || item.length < 3) {
      continue;
    }
    final hz = item[0].toString();
    final src = item[1].toString();
    final freq = (item[2] is num) ? (item[2] as num).toDouble() : 0.0;

    List<String> glosses;
    try {
      glosses = meaningsForHanzi(hz);
    } catch (_) {
      glosses = [];
    }

    final regScore = registerScoreFromResolvedGlosses(glosses);
    final catScore = categoryScoreForGlosses(glosses, activeCat);
    final split = splitClean(glosses);
    final clean = split[0];
    final hasCleanPhrase = clean.isNotEmpty ? 1 : 0;
    final hasAnyPhrase =
        glosses.isNotEmpty && glosses.any((g) => !g.contains('[char]')) ? 1 : 0;
    final colloquialBonus = hz.startsWith('阿') ? 1 : 0;

    final freqInt = freq.toInt();
    final hkFreqVal = (hkFreq[hz] ?? 0).toInt();
    final hkColVal = hkCol.contains(hz) ? 1 : 0;
    final hkKnown = hasHk ? (hkAtt.contains(hz) ? 1 : 0) : 1;

    final scoreTuple = [
      regScore.toDouble(),
      catScore > 0.0 ? 1 : 0,
      hkColVal,
      hkKnown,
      hasCleanPhrase,
      hasAnyPhrase,
      colloquialBonus,
      hkFreqVal,
      freqInt,
      sourceScore(src),
    ];

    scored.add([scoreTuple, [hz, src, freq]]);
  }

  scored.sort((a, b) {
    final sa = a[0] as List<dynamic>;
    final sb = b[0] as List<dynamic>;
    for (var i = 0; i < sa.length && i < sb.length; i++) {
      final va = (sa[i] as num).toDouble();
      final vb = (sb[i] as num).toDouble();
      if (va != vb) {
        return vb.compareTo(va);
      }
    }
    return 0;
  });

  return scored.map((e) => (e[1] as List<dynamic>)).toList();
}
