import '../../../domain/category_rules.dart';
import '../../../domain/hanzi_candidate_pipeline_core.dart';
import '../../../domain/hanzi_candidate_utils.dart';
import '../../../domain/jyutping_validation.dart';
import '../../../domain/meaning_sources_models.dart';
import '../../../domain/meaning_sources_cleaning.dart';
import '../../../data/asset_data_repository.dart';
import 'add_edit_state.dart';

class CandidateResolution {
  final List<CandidateItem> candidates;
  final String selectedHanzi;
  final String meaningText;
  final List<String> meaningsPreview;
  final List<String> meaningsFull;
  final String meaningSourceTag;
  final bool manualHanzi;
  final String notes;

  const CandidateResolution({
    required this.candidates,
    required this.selectedHanzi,
    required this.meaningText,
    required this.meaningsPreview,
    required this.meaningsFull,
    required this.meaningSourceTag,
    required this.manualHanzi,
    required this.notes,
  });
}

class AddEditCandidateService {
  final MeaningFacade meaningFacade;
  final Map<String, List<List<dynamic>>> reverseIndex;
  final HkWordsData hkWords;
  final Map<String, List<String>> cccantoMap;
  final Map<String, List<String>> cedictMap;

  const AddEditCandidateService({
    required this.meaningFacade,
    required this.reverseIndex,
    required this.hkWords,
    required this.cccantoMap,
    required this.cedictMap,
  });

  CandidateResolution resolve({
    required String jyutping,
    required List<String> activeCategories,
  }) {
    final jy = jyutping.trim();
    if (jy.isEmpty) {
      return const CandidateResolution(
        candidates: <CandidateItem>[],
        selectedHanzi: '',
        meaningText: '',
        meaningsPreview: <String>[],
        meaningsFull: <String>[],
        meaningSourceTag: '',
        manualHanzi: false,
        notes: '',
      );
    }

    final deps = HanziPipelineDeps(
      normalizeJyutping: normalizeJyutping,
      reverseIndex: reverseIndex,
      tier1ReverseCandidates: (jyNorm) => reverseIndex[jyNorm] ?? <List<dynamic>>[],
      ccGlossesFor: (hz) => meaningFacade.meaningsForDisplay(hz),
      glossCleaner: cleanGlossesForDisplay,
      activeCategoryProvider: () => activeCategories.isNotEmpty ? activeCategories.first : '',
      hkFreqMap: hkWords.freqMap,
      hkColloquial: hkWords.colloquial,
      hkAttested: hkWords.attested,
      maxCandidates: 10,
    );
    final pipeline = HanziCandidatePipeline(deps);
    final ranked = pipeline.run(jy);

    final items = <CandidateItem>[];
    for (var i = 0; i < ranked.length; i++) {
      final row = ranked[i];
      final hz = row[0].toString();
      final src = row[1].toString();
      final hk = _hkBadgeFor(hz);
      final tag = _sourceChipFor(src);
      final label = meaningFacade.candidateLabel(
        hz,
        src,
        preferred: i == 0,
        maxItems: 2,
      );
      items.add(CandidateItem(hanzi: hz, source: src, label: label, hkBadge: hk, sourceTag: tag));
    }

    if (items.isEmpty) {
      return CandidateResolution(
        candidates: const <CandidateItem>[],
        selectedHanzi: '',
        meaningText: '',
        meaningsPreview: const <String>[],
        meaningsFull: const <String>[],
        meaningSourceTag: '',
        manualHanzi: true,
        notes: _computeNotes(jy, const <String>[]),
      );
    }

    final selected = items.first.hanzi;
    final full = meaningFacade.meaningsForDisplay(selected);
    final preview = full.take(3).toList();
    final tag = _sourceTagFor(selected);
    final joined = full.isEmpty ? '' : full.join(', ');

    return CandidateResolution(
      candidates: items,
      selectedHanzi: selected,
      meaningText: joined,
      meaningsPreview: preview,
      meaningsFull: full,
      meaningSourceTag: full.isEmpty ? '' : tag,
      manualHanzi: false,
      notes: _computeNotes(jy, items.map((e) => e.hanzi).toList()),
    );
  }

  String _sourceTagFor(String hanzi) {
    if (hanzi.isEmpty) {
      return '';
    }
    if (cccantoMap.containsKey(hanzi)) {
      return 'CC';
    }
    if (cedictMap.containsKey(hanzi)) {
      return 'CE';
    }
    return '';
  }

  String meaningSourceTagFor(String hanzi) {
    return _sourceTagFor(hanzi.trim());
  }

  String? _hkBadgeFor(String hanzi) {
    if (hanzi.isEmpty) {
      return null;
    }
    final attested = hkWords.attested.contains(hanzi);
    final colloq = hkWords.colloquial.contains(hanzi);
    if (colloq) {
      return 'HK Colloq';
    }
    if (attested) {
      return 'HK';
    }
    return null;
  }

  String? _sourceChipFor(String source) {
    final s = source.trim().toLowerCase();
    if (s.isEmpty) {
      return null;
    }
    if (s.contains('tier1')) {
      return 'T1';
    }
    if (s.contains('tier2')) {
      return 'T2';
    }
    if (s.contains('cccanto')) {
      return 'CC';
    }
    if (s.contains('cedict')) {
      return 'CE';
    }
    return s.length > 3 ? s.substring(0, 3).toUpperCase() : s.toUpperCase();
  }

  String _computeNotes(String jyutping, List<String> candidates) {
    final jy = jyutping.trim();
    if (jy.isEmpty) {
      return '';
    }
    final norm = normalizeJyutping(jy);
    final nSyllables = splitSyllables(norm).length;
    final ambiguous = detectAmbiguity(
      candidates: candidates,
      nSyllables: nSyllables,
      meaningsForHanzi: (hz) => meaningFacade.meaningsForDisplay(hz),
    );
    if (!ambiguous) {
      return '';
    }
    if (candidates.isEmpty) {
      return 'No clear candidates found. Please confirm Hanzi and meaning.';
    }
    if (candidates.length > 1) {
      return 'Multiple candidates found. Please confirm Hanzi and meaning.';
    }
    return 'Multiple meanings found. Please confirm the intended meaning.';
  }
}
