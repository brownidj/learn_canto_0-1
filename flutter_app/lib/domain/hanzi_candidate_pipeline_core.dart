import 'hanzi_candidate_types.dart';
import 'hanzi_candidate_utils.dart';
import 'hanzi_candidate_ranker.dart';
import 'meaning_sources_cleaning.dart';
import 'jyutping_validation.dart';

typedef NormalizeJyutping = String Function(String);
typedef Tier1Candidates = dynamic Function(String);
typedef Tier2Compose = dynamic Function(String, Map<String, dynamic>);
typedef Tier2Shortlist = dynamic Function(dynamic);
typedef GlossesFor = List<String> Function(String);
typedef CurateFn = List<HanziCandidate> Function(List<HanziCandidate>);
typedef ActiveCategoryProvider = String Function();

class HanziPipelineDeps {
  final NormalizeJyutping normalizeJyutping;
  final Tier1Candidates? tier1ReverseCandidates;
  final Map<String, dynamic>? reverseIndex;
  final Tier2Compose? tier2Compose;
  final Tier2Shortlist? tier2Shortlist;
  final Map<String, dynamic>? charMap;
  final GlossesFor? ccGlossesFor;
  final GlossesFor? cedictMeaningsFor;
  final List<String> Function(List<String>)? glossCleaner;
  final CurateFn? curate;
  final ActiveCategoryProvider? activeCategoryProvider;
  final Map<String, Map<String, double>>? categoryProfiles;
  final Map<String, num>? hkFreqMap;
  final Set<String>? hkColloquial;
  final Set<String>? hkAttested;
  final int maxCandidates;

  const HanziPipelineDeps({
    required this.normalizeJyutping,
    this.tier1ReverseCandidates,
    this.reverseIndex,
    this.tier2Compose,
    this.tier2Shortlist,
    this.charMap,
    this.ccGlossesFor,
    this.cedictMeaningsFor,
    this.glossCleaner,
    this.curate,
    this.activeCategoryProvider,
    this.categoryProfiles,
    this.hkFreqMap,
    this.hkColloquial,
    this.hkAttested,
    this.maxCandidates = 10,
  });
}

class HanziCandidatePipeline {
  final NormalizeJyutping _normalize;
  final Tier1Candidates? _tier1;
  final Tier2Compose? _tier2Compose;
  final Tier2Shortlist? _tier2Shortlist;
  final Map<String, dynamic> _charMap;
  final GlossesFor? _ccGlossesFor;
  final GlossesFor? _cedictMeaningsFor;
  final List<String> Function(List<String>)? _glossCleaner;
  final CurateFn? _curate;
  final ActiveCategoryProvider? _activeCategoryProvider;
  final Map<String, Map<String, double>>? _categoryProfiles;
  final Map<String, num>? _hkFreqMap;
  final Set<String>? _hkColloquial;
  final Set<String>? _hkAttested;
  final int _max;

  HanziCandidatePipeline(HanziPipelineDeps deps)
      : _normalize = deps.normalizeJyutping,
        _tier1 = deps.tier1ReverseCandidates ??
            (deps.reverseIndex != null
                ? (String jyNorm) => (deps.reverseIndex![jyNorm] ?? [])
                : null),
        _tier2Compose = deps.tier2Compose,
        _tier2Shortlist = deps.tier2Shortlist,
        _charMap = deps.charMap ?? <String, dynamic>{},
        _ccGlossesFor = deps.ccGlossesFor,
        _cedictMeaningsFor = deps.cedictMeaningsFor,
        _glossCleaner = deps.glossCleaner,
        _curate = deps.curate,
        _activeCategoryProvider = deps.activeCategoryProvider,
        _categoryProfiles = deps.categoryProfiles,
        _hkFreqMap = deps.hkFreqMap,
        _hkColloquial = deps.hkColloquial,
        _hkAttested = deps.hkAttested,
        _max = deps.maxCandidates > 0 ? deps.maxCandidates : 10;

  List<List<dynamic>> run(String jyut, {bool manualHanziMode = false}) {
    final cands = candidatesFor(jyut, manualHanziMode: manualHanziMode);
    return cands.map((c) => [c.hanzi, c.source, c.freq]).toList();
  }

  List<HanziCandidate> candidatesFor(String jyut, {bool manualHanziMode = false}) {
    if (manualHanziMode) {
      return [];
    }
    final jyNorm = _normalize(jyut);
    final syllables = splitSyllables(jyNorm);
    final nSyllables = syllables.length;

    dynamic rawTier1 = [];
    if (_tier1 != null) {
      try {
        rawTier1 = _tier1!(jyNorm) ?? [];
      } catch (_) {
        rawTier1 = [];
      }
    }

    var cands = coerceCandidates(rawTier1, 'tier1');

    if (cands.isEmpty &&
        nSyllables >= 1 &&
        nSyllables <= 4 &&
        _tier2Compose != null &&
        _charMap.isNotEmpty) {
      dynamic rawTier2 = [];
      try {
        rawTier2 = _tier2Compose!(jyNorm, _charMap) ?? [];
      } catch (_) {
        rawTier2 = [];
      }
      try {
        if (_tier2Shortlist != null && (rawTier2 is List) && rawTier2.isNotEmpty) {
          rawTier2 = _tier2Shortlist!(rawTier2) ?? rawTier2;
        }
      } catch (_) {}

      cands = coerceCandidates(rawTier2, 'tier2-char');
    }

    cands = dedupeKeepFirst(cands);

    if (_curate != null) {
      try {
        final curated = _curate!(cands);
        cands = curated;
      } catch (_) {
        cands = simpleRank(cands);
      }
    } else {
      cands = simpleRank(cands);
    }

    try {
      var activeCat = '';
      if (_activeCategoryProvider != null) {
        try {
          activeCat = _activeCategoryProvider!().trim();
        } catch (_) {
          activeCat = '';
        }
      }
      final ranked = rerankCandidatesWithMeanings(
        cands.map((c) => [c.hanzi, c.source, c.freq]).toList(),
        meaningsForHanzi: glossesForCandidate,
        activeCategory: activeCat,
        categoryProfiles: _categoryProfiles,
        hkFreqMap: _hkFreqMap,
        hkColloquial: _hkColloquial,
        hkAttested: _hkAttested,
      );
      final bucket = <String, List<HanziCandidate>>{};
      for (final c in cands) {
        final key = '${c.hanzi}|||${c.source}';
        bucket.putIfAbsent(key, () => []).add(c);
      }
      final reordered = <HanziCandidate>[];
      for (final row in ranked) {
        final hz = row[0].toString();
        final src = row[1].toString();
        final key = '$hz|||$src';
        final list = bucket[key];
        if (list != null && list.isNotEmpty) {
          reordered.add(list.removeAt(0));
        }
      }
      for (final rest in bucket.values) {
        reordered.addAll(rest);
      }
      cands = reordered;
    } catch (_) {}

    if (cands.length > _max) {
      cands = cands.sublist(0, _max);
    }
    return cands;
  }

  List<String> glossesForCandidate(String hanzi) {
    final hz = hanzi.trim();
    if (hz.isEmpty) {
      return [];
    }
    List<String> out = [];
    if (_ccGlossesFor != null) {
      try {
        out = _ccGlossesFor!(hz);
      } catch (_) {
        out = [];
      }
    }
    if (out.isEmpty && _cedictMeaningsFor != null) {
      try {
        out = _cedictMeaningsFor!(hz);
      } catch (_) {
        out = [];
      }
    }
    out = out.map((x) => x.toString().trim()).where((x) => x.isNotEmpty).toList();
    if (_glossCleaner != null) {
      try {
        final cleaned = _glossCleaner!(out);
        out = cleaned.map((x) => x.toString().trim()).where((x) => x.isNotEmpty).toList();
      } catch (_) {}
    }
    return out;
  }

  List<HanziCandidate> attachGlosses(List<HanziCandidate> cands) {
    final out = <HanziCandidate>[];
    for (final c in cands) {
      try {
        final glosses = glossesForCandidate(c.hanzi);
        out.add(c.withGlosses(glosses));
      } catch (_) {
        out.add(c);
      }
    }
    return out;
  }
}

HanziCandidatePipeline buildPipelineFromCategoryManager(Map<String, dynamic> dialog) {
  NormalizeJyutping normalize;
  final normFn = dialog['_normalize_jy'];
  if (normFn is NormalizeJyutping) {
    normalize = normFn;
  } else {
    normalize = normalizeJyutping;
  }

  dynamic provider = dialog['_candidate_provider'];
  if (provider is Map && provider['type'] == 'CandidatePipelineProvider') {
    provider = null;
  }

  Tier1Candidates? tier1;
  if (provider is Function) {
    tier1 = (String jy) => provider(jy);
  } else if (provider is Map && provider['get_candidates'] is Function) {
    final fn = provider['get_candidates'] as Function;
    tier1 = (String jy) => fn(jy);
  }

  Tier2Compose? composeFn;
  Tier2Shortlist? shortlistFn;

  final getComp = dialog['_get_compose_and_rank'];
  if (getComp is Function) {
    try {
      final out = getComp();
      if (out is List && out.isNotEmpty) {
        composeFn = out[0] as Tier2Compose?;
        if (out.length > 1) {
          shortlistFn = out[1] as Tier2Shortlist?;
        }
      }
    } catch (_) {}
  }

  composeFn ??= dialog['compose_candidates_from_chars'] as Tier2Compose?;
  composeFn ??= dialog['_compose_candidates_from_chars'] as Tier2Compose?;
  shortlistFn ??= dialog['shortlist_hanzi_candidates'] as Tier2Shortlist?;
  shortlistFn ??= dialog['_shortlist_hanzi_candidates'] as Tier2Shortlist?;

  Map<String, dynamic>? reverseIndex;
  if (dialog['_reverse_index'] is Map) {
    reverseIndex = Map<String, dynamic>.from(dialog['_reverse_index'] as Map);
  }
  Map<String, dynamic> charMap = <String, dynamic>{};
  if (dialog['_char_map'] is Map) {
    charMap = Map<String, dynamic>.from(dialog['_char_map'] as Map);
  }

  GlossesFor? ccGlossesFor;
  final ccFn = dialog['get_cccanto_glosses_for'] ?? dialog['_cc_glosses_for'];
  if (ccFn is Function) {
    ccGlossesFor = (String hz) => List<String>.from(ccFn(hz) ?? <String>[]);
  }

  GlossesFor? cedictFor;
  final cedFn = dialog['get_cedict_meanings_for'] ?? dialog['_cedict_meanings_for'];
  if (cedFn is Function) {
    cedictFor = (String hz) => List<String>.from(cedFn(hz) ?? <String>[]);
  }

  CurateFn? curate;
  final curator = dialog['_candidate_curator'];
  if (curator is Function) {
    curate = (List<HanziCandidate> c) =>
        List<HanziCandidate>.from(curator(c) ?? c);
  } else if (curator is Map && curator['curate'] is Function) {
    final fn = curator['curate'] as Function;
    curate = (List<HanziCandidate> c) =>
        List<HanziCandidate>.from(fn(c) ?? c);
  }

  final maxCands =
      dialog['MAX_HANZI_CANDIDATES'] is int ? dialog['MAX_HANZI_CANDIDATES'] as int : 10;

  String activeCategoryProvider() {
    final cats = dialog['_selected_categories'];
    if (cats is List && cats.isNotEmpty) {
      final v = cats.first.toString().trim();
      if (v.isNotEmpty) {
        return v;
      }
    }
    final last = (dialog['_last_committed_category'] ?? '').toString().trim();
    if (last.isNotEmpty) {
      return last;
    }
    final addCat = dialog['_add_cat_current_text'];
    if (addCat != null) {
      return addCat.toString().trim();
    }
    return '';
  }

  Map<String, num>? hkFreqMap;
  if (dialog['_hk_word_freq_map'] is Map) {
    hkFreqMap = (dialog['_hk_word_freq_map'] as Map).map(
      (k, v) => MapEntry(k.toString(), v is num ? v : 0),
    );
  }
  final hkColloq = dialog['_hk_word_colloq'] is Set ? dialog['_hk_word_colloq'] as Set<String> : null;
  final hkAtt = dialog['_hk_word_attested'] is Set ? dialog['_hk_word_attested'] as Set<String> : null;

  final deps = HanziPipelineDeps(
    normalizeJyutping: normalize,
    tier1ReverseCandidates: tier1,
    reverseIndex: reverseIndex,
    tier2Compose: composeFn,
    tier2Shortlist: shortlistFn,
    charMap: charMap,
    ccGlossesFor: ccGlossesFor,
    cedictMeaningsFor: cedictFor,
    glossCleaner: (glosses) => cleanGlossesForDisplay(glosses),
    curate: curate,
    activeCategoryProvider: activeCategoryProvider,
    categoryProfiles: null,
    hkFreqMap: hkFreqMap,
    hkColloquial: hkColloq,
    hkAttested: hkAtt,
    maxCandidates: maxCands,
  );
  return HanziCandidatePipeline(deps);
}
