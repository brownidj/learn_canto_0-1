import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_app/domain/jyutping_validation.dart';
import 'package:flutter_app/domain/category_rules.dart';
import 'package:flutter_app/domain/duplicate_rules.dart';
import 'package:flutter_app/domain/meaning_sources_cleaning.dart';
import 'package:flutter_app/domain/hanzi_candidate_types.dart';
import 'package:flutter_app/domain/hanzi_candidate_utils.dart';
import 'package:flutter_app/domain/hanzi_candidate_ranker.dart';
import 'package:flutter_app/domain/hanzi_candidate_pipeline_core.dart';
import 'package:flutter_app/domain/meaning_sources_models.dart';
import 'package:flutter_app/domain/entry_validation.dart';
import 'package:flutter_app/domain/vocabulary_service.dart';

bool deepEqual(dynamic a, dynamic b) {
  if (a is Map && b is Map) {
    if (a.length != b.length) {
      return false;
    }
    for (final key in a.keys) {
      if (!b.containsKey(key)) {
        return false;
      }
      if (!deepEqual(a[key], b[key])) {
        return false;
      }
    }
    return true;
  }
  if (a is List && b is List) {
    if (a.length != b.length) {
      return false;
    }
    for (var i = 0; i < a.length; i++) {
      if (!deepEqual(a[i], b[i])) {
        return false;
      }
    }
    return true;
  }
  return a == b;
}

dynamic runFixture(String fn, dynamic input) {
  switch (fn) {
    case 'normalize_jyutping':
      return normalizeJyutping(input as String?);
    case 'validate_jyut_syllables':
      return validateJyutSyllables(input as String?);
    case 'is_category_placeholder':
      return isCategoryPlaceholder(input);
    case 'save_enabled_gate':
      final m = input as Map<String, dynamic>;
      return saveEnabledGate(
        jyut: m['jyut'],
        hanzi: m['hanzi'],
        meanings: m['meanings'],
        category: m['category'],
      );
    case 'should_show_custom_hanzi_button':
      return shouldShowCustomHanziButton(input);
    case 'prefer_meanings':
      final m = input as Map<String, dynamic>;
      return preferMeanings(m['primary'], m['fallback']);
    case 'detect_ambiguity':
      final m = input as Map<String, dynamic>;
      final meanings = m['meanings_for_hanzi'];
      List<String> Function(String)? fn;
      if (meanings is List) {
        fn = (_) => meanings.cast<String>();
      }
      return detectAmbiguity(
        candidates: m['candidates'],
        nSyllables: m['n_syllables'],
        meaningsForHanzi: fn,
      );
    case 'is_duplicate_jy':
      final m = input as Map<String, dynamic>;
      return isDuplicateJy(m['jy'] as String, vocab: m['vocab']);
    case 'is_exact_duplicate_entry':
      final m = input as Map<String, dynamic>;
      return isExactDuplicateEntry(m['vocab'], m['jy'], m['hz']);
    case 'clean_glosses_for_display':
      return cleanGlossesForDisplay(input);
    case 'norm_space':
      return normSpace(input as String);
    case 'split_syllables':
      return splitSyllables(input as String);
    case 'coerce_candidates':
      final m = input as Map<String, dynamic>;
      final out = coerceCandidates(m['raw'], m['default_source'] as String);
      return out.map((c) => [c.hanzi, c.source, c.freq]).toList();
    case 'dedupe_keep_first':
      final seed = coerceCandidates(
        ['飲', ['飲', 'tier1', 2], ['喝', 'tier2', 1]],
        'tier2',
      );
      final out = dedupeKeepFirst(seed);
      return out.map((c) => [c.hanzi, c.source, c.freq]).toList();
    case 'simple_rank':
      final seed = coerceCandidates(
        [
          ['喝', 'tier2', 1],
          ['飲', 'tier1', 3],
          ['啦', 'tier1', 3],
        ],
        'tier2',
      );
      final out = simpleRank(seed);
      return out.map((c) => [c.hanzi, c.source, c.freq]).toList();
    case 'rerank_candidates_with_meanings':
      final m = input as Map<String, dynamic>;
      final meaningMap = (m['meaning_map'] as Map).map(
        (k, v) => MapEntry(k.toString(), (v as List).cast<String>()),
      );
      final profilesRaw = (m['category_profiles'] as Map).map((k, v) {
        final inner = (v as Map).map(
          (kk, vv) => MapEntry(kk.toString(), (vv as num).toDouble()),
        );
        return MapEntry(k.toString(), inner);
      });
      final hkFreqRaw = (m['hk_freq_map'] as Map).map(
        (k, v) => MapEntry(k.toString(), (v as num)),
      );
      final hkCol = (m['hk_colloquial'] as List).map((e) => e.toString()).toSet();
      final hkAtt = (m['hk_attested'] as List).map((e) => e.toString()).toSet();
      return rerankCandidatesWithMeanings(
        (m['cands'] as List),
        meaningsForHanzi: (hz) => meaningMap[hz] ?? <String>[],
        activeCategory: m['active_category'] as String,
        categoryProfiles: profilesRaw,
        hkFreqMap: hkFreqRaw,
        hkColloquial: hkCol,
        hkAttested: hkAtt,
      );
    case 'rerank_candidates_with_meanings_nohk':
    case 'rerank_candidates_with_meanings_tagged':
      final m2 = input as Map<String, dynamic>;
      final meaningMap2 = (m2['meaning_map'] as Map).map(
        (k, v) => MapEntry(k.toString(), (v as List).cast<String>()),
      );
      final profilesRaw2 = (m2['category_profiles'] as Map).map((k, v) {
        final inner = (v as Map).map(
          (kk, vv) => MapEntry(kk.toString(), (vv as num).toDouble()),
        );
        return MapEntry(k.toString(), inner);
      });
      return rerankCandidatesWithMeanings(
        (m2['cands'] as List),
        meaningsForHanzi: (hz) => meaningMap2[hz] ?? <String>[],
        activeCategory: m2['active_category'] as String,
        categoryProfiles: profilesRaw2,
        hkFreqMap: const {},
        hkColloquial: const {},
        hkAttested: const {},
      );
    case 'coerce_candidates_freq':
      final m2 = input as Map<String, dynamic>;
      final out = coerceCandidates(m2['raw'], m2['default_source'] as String);
      return out.map((c) => [c.hanzi, c.source, c.freq]).toList();
    case 'pipeline_tier1':
      final t1Map = {
        'jam2': [
          ['飲', 'tier1', 1.0],
          ['喝', 'tier1', 1.0],
        ],
      };
      final meaningMap = {
        '飲': ['drink', 'beverage'],
        '喝': ['drink'],
      };
      final profiles = {
        'food': {'drink': 2.0, 'beverage': 1.0},
      };
      final deps = HanziPipelineDeps(
        normalizeJyutping: normalizeJyutping,
        tier1ReverseCandidates: (jy) => t1Map[jy] ?? [],
        ccGlossesFor: (hz) => meaningMap[hz] ?? <String>[],
        glossCleaner: (glosses) => cleanGlossesForDisplay(glosses),
        activeCategoryProvider: () => 'food',
        categoryProfiles: profiles,
        maxCandidates: 5,
      );
      final pipe = HanziCandidatePipeline(deps);
      return pipe.run('jam2');
    case 'pipeline_tier2':
      dynamic composeStub(String jyNorm, Map<String, dynamic> _charMap) {
        return [
          ['飲', 'tier2-char', 1.0],
          ['喝', 'tier2-char', 2.0],
        ];
      }

      dynamic shortlistStub(dynamic items) {
        if (items is List) {
          return items.take(1).toList();
        }
        return items;
      }

      final deps2 = HanziPipelineDeps(
        normalizeJyutping: normalizeJyutping,
        tier1ReverseCandidates: (jy) => [],
        tier2Compose: composeStub,
        tier2Shortlist: shortlistStub,
        charMap: {'飲': 'jam2'},
        maxCandidates: 5,
      );
      final pipe2 = HanziCandidatePipeline(deps2);
      return pipe2.run('jam2');
    case 'pipeline_manual':
      final t1Map2 = {
        'jam2': [
          ['飲', 'tier1', 1.0],
          ['喝', 'tier1', 1.0],
        ],
      };
      final deps3 = HanziPipelineDeps(
        normalizeJyutping: normalizeJyutping,
        tier1ReverseCandidates: (jy) => t1Map2[jy] ?? [],
      );
      final pipe3 = HanziCandidatePipeline(deps3);
      return pipe3.run('jam2', manualHanziMode: true);
    case 'build_pipeline_from_category_manager':
      final meaningMap = {
        '飲': ['drink', 'beverage'],
      };
      final dialog = <String, dynamic>{
        '_normalize_jy': normalizeJyutping,
        '_candidate_provider': {
          'get_candidates': (String jy) {
            if (jy == 'jam2') {
              return [
                ['飲', 'tier1', 1.0],
              ];
            }
            return [];
          }
        },
        '_reverse_index': {},
        '_char_map': {'飲': 'jam2'},
        '_cc_glosses_for': (String hz) => meaningMap[hz] ?? <String>[],
        '_cedict_meanings_for': (String _hz) => <String>[],
        '_candidate_curator': null,
        '_selected_categories': ['food'],
        '_last_committed_category': '',
        '_add_cat_current_text': '',
        '_hk_word_freq_map': {'飲': 10},
        '_hk_word_colloq': <String>{},
        '_hk_word_attested': <String>{'飲'},
        'MAX_HANZI_CANDIDATES': 5,
      };
      final pipe = buildPipelineFromCategoryManager(dialog);
      return pipe.run('jam2');
    case 'meaning_resolver_glosses_for':
      final m = input as Map<String, dynamic>;
      final ccMap = {
        '飲': ['drink', 'beverage', ''],
        '喝': ['drink'],
      };
      final ceMap = {
        '飲': ['to drink'],
        '話': ['speech'],
      };
      final resolver = MeaningResolver(
        ccGlossesFor: (hz) => ccMap[hz] ?? <String>[],
        cedictMeaningsFor: (hz) => ceMap[hz] ?? <String>[],
      );
      return resolver.glossesFor(m['hanzi'] as String, limit: m['limit'] as int);
    case 'meaning_resolver_glosses_fallback':
      final m2 = input as Map<String, dynamic>;
      final ccMap2 = {
        '飲': ['drink', 'beverage', ''],
        '喝': ['drink'],
      };
      final ceMap2 = {
        '飲': ['to drink'],
        '話': ['speech'],
      };
      final resolver2 = MeaningResolver(
        ccGlossesFor: (hz) => ccMap2[hz] ?? <String>[],
        cedictMeaningsFor: (hz) => ceMap2[hz] ?? <String>[],
      );
      return resolver2.glossesFor(m2['hanzi'] as String, limit: m2['limit'] as int);
    case 'meaning_facade_meanings_for_display':
      final ccMap3 = {
        '飲': ['drink', 'beverage', ''],
      };
      final ceMap3 = {
        '飲': ['to drink'],
      };
      final resolver3 = MeaningResolver(
        ccGlossesFor: (hz) => ccMap3[hz] ?? <String>[],
        cedictMeaningsFor: (hz) => ceMap3[hz] ?? <String>[],
      );
      final facade = MeaningFacade(
        resolver: resolver3,
        cleaner: (items) => cleanGlossesForDisplay(items),
      );
      final m3 = input as Map<String, dynamic>;
      return facade.meaningsForDisplay(m3['hanzi'] as String);
    case 'meaning_facade_preview':
      final ccMap4 = {
        '飲': ['drink', 'beverage', ''],
      };
      final resolver4 = MeaningResolver(
        ccGlossesFor: (hz) => ccMap4[hz] ?? <String>[],
        cedictMeaningsFor: (hz) => <String>[],
      );
      final facade2 = MeaningFacade(
        resolver: resolver4,
        cleaner: (items) => cleanGlossesForDisplay(items),
      );
      final m4 = input as Map<String, dynamic>;
      return facade2.previewForDisplay(m4['hanzi'] as String, maxItems: m4['max_items'] as int);
    case 'meaning_facade_candidate_label':
      final ccMap5 = {
        '飲': ['drink', 'beverage', ''],
      };
      final resolver5 = MeaningResolver(
        ccGlossesFor: (hz) => ccMap5[hz] ?? <String>[],
        cedictMeaningsFor: (hz) => <String>[],
      );
      final facade3 = MeaningFacade(
        resolver: resolver5,
        cleaner: (items) => cleanGlossesForDisplay(items),
      );
      final m5 = input as Map<String, dynamic>;
      return facade3.candidateLabel(
        m5['hanzi'] as String,
        m5['source'] as String,
        preferred: m5['preferred'] as bool,
        maxItems: 2,
      );
    case 'meaning_facade_select_candidate':
      final ccMap6 = {
        '飲': ['drink', 'beverage', ''],
      };
      final resolver6 = MeaningResolver(
        ccGlossesFor: (hz) => ccMap6[hz] ?? <String>[],
        cedictMeaningsFor: (hz) => <String>[],
      );
      final facade4 = MeaningFacade(
        resolver: resolver6,
        cleaner: (items) => cleanGlossesForDisplay(items),
      );
      final m6 = input as Map<String, dynamic>;
      final sel = facade4.selectCandidate(
        m6['hanzi'] as String,
        m6['source'] as String,
        preferred: true,
        maxItems: 2,
      );
      return {
        'hanzi': sel.hanzi,
        'source': sel.source,
        'meanings': sel.meanings,
        'label': sel.label,
      };
    case 'entry_validator_validate_all':
      final ev = EntryValidator();
      final res = ev.validateAll(
        jyutping: 'nei5 hou2',
        hanzi: '你好',
        meanings: 'hello, hi',
        category: 'greetings',
      );
      return res.map((k, v) => MapEntry(k, v.toMap()));
    case 'entry_validator_is_valid_entry':
      final ev2 = EntryValidator();
      return ev2.isValidEntry(
        jyutping: 'nei5 hou2',
        hanzi: '你好',
        meanings: 'hello',
        category: 'greetings',
      );
    case 'vocab_service_add_entry':
      final vocab = <String, dynamic>{};
      final cats = <String, List<String>>{'unassigned': []};
      final svc = VocabularyService(vocab: vocab, categories: cats);
      final entry = svc.addEntry(
        jyutping: 'nei5 hou2',
        hanzi: '你好',
        meanings: ['hello'],
        categories: ['greetings'],
      );
      return {
        'entry': entry.toMap(),
        'vocab': vocab,
        'categories': cats,
      };
    case 'vocab_service_update_entry':
      final vocab2 = <String, dynamic>{};
      final cats2 = <String, List<String>>{'unassigned': []};
      final svc2 = VocabularyService(vocab: vocab2, categories: cats2);
      svc2.addEntry(
        jyutping: 'nei5 hou2',
        hanzi: '你好',
        meanings: ['hello'],
        categories: ['greetings'],
      );
      final updated = svc2.updateEntry(
        originalHanzi: '你好',
        jyutping: 'nei5 hou2',
        hanzi: '你好呀',
        meanings: ['hello there'],
        categories: ['greetings'],
      );
      return {
        'entry': updated.toMap(),
        'vocab': vocab2,
        'categories': cats2,
      };
    default:
      throw StateError('Unknown function: $fn');
  }
}

void main() {
  test('domain fixtures parity', () {
    final file = File('test/fixtures/domain_fixtures.json');
    final raw = file.readAsStringSync();
    final fixtures = jsonDecode(raw) as List<dynamic>;

    for (final item in fixtures) {
      final f = item as Map<String, dynamic>;
      final fn = f['function'] as String;
      final input = f['input'];
      final expected = f['output'];
      final actual = runFixture(fn, input);
      final ok = deepEqual(actual, expected);
      expect(ok, true, reason: 'Mismatch for $fn input=$input actual=$actual expected=$expected');
    }
  });
}
