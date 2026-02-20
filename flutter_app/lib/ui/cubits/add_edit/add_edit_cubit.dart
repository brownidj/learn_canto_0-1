import 'package:flutter/foundation.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import '../../../domain/entry_validation.dart';
import '../../../domain/vocabulary_service.dart';
import '../../../domain/exceptions.dart';
import '../../../domain/jyutping_validation.dart';
import '../../../domain/meaning_sources_models.dart';
import '../../../domain/meaning_sources_cleaning.dart';
import '../../../domain/hanzi_candidate_pipeline_core.dart';
import '../../../data/asset_data_repository.dart';
import 'add_edit_state.dart';

class AddEditCubit extends Cubit<AddEditState> {
  final EntryValidator _validator;
  final VocabularyService _vocabService;
  MeaningFacade _meaningFacade;
  Map<String, List<List<dynamic>>> _reverseIndex;
  HkWordsData _hkWords;
  Map<String, List<String>> _cccantoMap = {};
  Map<String, List<String>> _cedictMap = {};
  AssetDataRepository? _repo;
  final Map<String, dynamic> _vocabMap;
  final Map<String, List<String>> _categoriesMap;

  AddEditCubit({
    required EntryValidator validator,
    required VocabularyService vocabService,
    required Map<String, dynamic> vocabMap,
    required Map<String, List<String>> categoriesMap,
    MeaningFacade? meaningFacade,
    Map<String, List<List<dynamic>>>? reverseIndex,
    HkWordsData? hkWords,
  })  : _validator = validator,
        _vocabService = vocabService,
        _vocabMap = vocabMap,
        _categoriesMap = categoriesMap,
        _meaningFacade = meaningFacade ??
            MeaningFacade(
              resolver: MeaningResolver(
                ccGlossesFor: (_) => <String>[],
                cedictMeaningsFor: (_) => <String>[],
              ),
              cleaner: cleanGlossesForDisplay,
            ),
        _reverseIndex = reverseIndex ?? _defaultReverseIndex,
        _hkWords = hkWords ?? const HkWordsData(freqMap: {}, colloquial: {}, attested: {}),
        super(AddEditState.initial());

  void setJyutping(String value) {
    emit(_recalc(state.copyWith(jyutping: value)));
    _updateDuplicateWarning(value);
    _refreshCandidates(value);
  }

  void setHanzi(String value) {
    emit(_recalc(state.copyWith(hanzi: value, selectedHanzi: value)));
    _updateMeaningPreview(value);
  }

  void setMeaning(String value) {
    emit(_recalc(state.copyWith(meaningText: value)));
  }

  void setRegister(String value) {
    emit(_recalc(state.copyWith(register: value)));
  }

  void setCategories(List<String> values) {
    emit(_recalc(state.copyWith(categories: values)));
    _refreshCandidates(state.jyutping);
  }

  void selectCandidate(String hanzi) {
    emit(_recalc(state.copyWith(selectedHanzi: hanzi, hanzi: hanzi)));
    _updateMeaningPreview(hanzi);
  }

  Future<void> loadData(AssetDataRepository repo) async {
    _repo = repo;
    try {
      debugPrint('[AddEditCubit] loadData start');
      final legacy = await repo.loadLegacyVocab();
      final vocab = legacy['vocab'];
      final catsMap = legacy['categories'];
      if (vocab is Map) {
        _vocabMap
          ..clear()
          ..addAll(vocab.map((k, v) => MapEntry(k.toString(), v)));
      }
      if (catsMap is Map) {
        _categoriesMap
          ..clear()
          ..addAll(catsMap.map((k, v) => MapEntry(k.toString(), List<String>.from(v))));
      }
      final cats = _categoriesMap.keys.toList()..sort();
      final rev = await repo.loadReverseIndex();
      final hk = await repo.loadHkWords();
      final cc = await repo.loadCccantoMeanings();
      final ce = await repo.loadCedictMeanings();
      _reverseIndex = rev;
      _hkWords = hk;
      _cccantoMap = cc;
      _cedictMap = ce;
      debugPrint(
        '[AddEditCubit] loadData done: vocab=${_vocabMap.length} cats=${_categoriesMap.length} '
        'reverse=${_reverseIndex.length} hkFreq=${_hkWords.freqMap.length} '
        'cccanto=${_cccantoMap.length} cedict=${_cedictMap.length}',
      );
      _meaningFacade = MeaningFacade(
        resolver: MeaningResolver(
          ccGlossesFor: (hz) => _cccantoMap[hz] ?? <String>[],
          cedictMeaningsFor: (hz) => _cedictMap[hz] ?? <String>[],
        ),
        cleaner: cleanGlossesForDisplay,
      );
      emit(state.copyWith(availableCategories: cats));
      _refreshCandidates(state.jyutping);
    } catch (_) {
      // Keep defaults if asset loading fails.
    }
  }

  void addCategory(String value) {
    final trimmed = value.trim();
    if (trimmed.isEmpty) {
      return;
    }
    if (!state.availableCategories.contains(trimmed)) {
      final next = List<String>.from(state.availableCategories)..add(trimmed);
      emit(state.copyWith(availableCategories: next));
    }
    final selected = List<String>.from(state.categories);
    if (!selected.contains(trimmed)) {
      selected.add(trimmed);
      setCategories(selected);
    }
    final repo = _repo;
    if (repo != null) {
      repo.persistCategories(state.availableCategories);
    }
  }

  void _refreshCandidates(String jyutping) {
    final jy = jyutping.trim();
    final jyNorm = normalizeJyutping(jy);
    debugPrint(
      '[AddEditCubit] refreshCandidates jy="${jy}" norm="${jyNorm}" '
      'cats=${state.categories.length} reverseSize=${_reverseIndex.length} '
      'hasKey=${_reverseIndex.containsKey(jyNorm)}',
    );
    if (jy.isEmpty) {
      debugPrint('[AddEditCubit] refreshCandidates empty jy -> clear');
      emit(state.copyWith(candidateItems: <CandidateItem>[], selectedHanzi: '', meaningsPreview: <String>[]));
      return;
    }
    final deps = HanziPipelineDeps(
      normalizeJyutping: normalizeJyutping,
      reverseIndex: _reverseIndex,
      tier1ReverseCandidates: (jyNorm) => _reverseIndex[jyNorm] ?? <List<dynamic>>[],
      ccGlossesFor: (hz) => _meaningFacade.meaningsForDisplay(hz),
      glossCleaner: cleanGlossesForDisplay,
      activeCategoryProvider: () =>
          state.categories.isNotEmpty ? state.categories.first : '',
      hkFreqMap: _hkWords.freqMap,
      hkColloquial: _hkWords.colloquial,
      hkAttested: _hkWords.attested,
      maxCandidates: 10,
    );
    final pipeline = HanziCandidatePipeline(deps);
    final ranked = pipeline.run(jy);
    debugPrint('[AddEditCubit] refreshCandidates ranked=${ranked.length}');
    final items = <CandidateItem>[];
    for (var i = 0; i < ranked.length; i++) {
      final row = ranked[i];
      final hz = row[0].toString();
      final src = row[1].toString();
      final hk = _hkBadgeFor(hz);
      final tag = _sourceChipFor(src);
      final label = _meaningFacade.candidateLabel(
        hz,
        src,
        preferred: i == 0,
        maxItems: 2,
      );
      items.add(CandidateItem(hanzi: hz, source: src, label: label, hkBadge: hk, sourceTag: tag));
    }
    final selected = items.isNotEmpty ? items.first.hanzi : '';
    emit(state.copyWith(candidateItems: items, selectedHanzi: selected, hanzi: selected));
    _updateMeaningPreview(selected);
  }

  void _updateMeaningPreview(String hanzi) {
    final hz = hanzi.trim();
    if (hz.isEmpty) {
      emit(state.copyWith(meaningsPreview: <String>[], meaningsFull: <String>[], meaningSourceTag: ''));
      return;
    }
    final full = _meaningFacade.meaningsForDisplay(hz);
    final preview = full.take(3).toList();
    final tag = _sourceTagFor(hz);
    emit(state.copyWith(meaningsPreview: preview, meaningsFull: full, meaningSourceTag: tag));
  }

  String _sourceTagFor(String hanzi) {
    if (hanzi.isEmpty) {
      return '';
    }
    if (_cccantoMap.containsKey(hanzi)) {
      return 'CC';
    }
    if (_cedictMap.containsKey(hanzi)) {
      return 'CE';
    }
    return '';
  }

  String? _hkBadgeFor(String hanzi) {
    if (hanzi.isEmpty) {
      return null;
    }
    final attested = _hkWords.attested.contains(hanzi);
    final colloq = _hkWords.colloquial.contains(hanzi);
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

  bool save() {
    try {
      _vocabService.addEntry(
        jyutping: state.jyutping,
        hanzi: state.hanzi,
        meanings: state.meaningText,
        categories: state.categories,
      );
      final repo = _repo;
      if (repo != null) {
        repo.persistEntry(
          jyutping: state.jyutping.trim(),
          hanzi: state.hanzi.trim(),
          meanings: state.meaningText.split(',').map((e) => e.trim()).where((e) => e.isNotEmpty).toList(),
          categories: state.categories,
          register: state.register.trim(),
          headword: state.hanzi.trim(),
        );
      }
      emit(AddEditState.initial().copyWith(toastMessage: 'Saved'));
      return true;
    } on VocabularyError {
      emit(_recalc(state));
      return false;
    }
  }

  Map<String, dynamic> previewPayload() {
    return {
      'jyutping': state.jyutping.trim(),
      'hanzi': state.hanzi.trim(),
      'meanings': state.meaningText.split(',').map((e) => e.trim()).where((e) => e.isNotEmpty).toList(),
      'categories': List<String>.from(state.categories),
      'register': state.register.trim(),
    };
  }

  void _updateDuplicateWarning(String jyutping) {
    final jy = jyutping.trim();
    if (jy.isEmpty) {
      emit(state.copyWith(duplicateWarning: null));
      return;
    }
    final dup = _vocabService.checkDuplicateJyutping(jy);
    if (dup) {
      emit(state.copyWith(duplicateWarning: 'Jyutping already exists.'));
    } else {
      emit(state.copyWith(duplicateWarning: null));
    }
  }

  void clearToast() {
    emit(state.copyWith(toastMessage: null));
  }

  AddEditState _recalc(AddEditState next) {
    final results = _validator.validateAll(
      jyutping: next.jyutping,
      hanzi: next.hanzi,
      meanings: next.meaningText,
      category: next.categories.isNotEmpty ? next.categories.first : '',
    );
    final errors = <String, String>{};
    for (final entry in results.entries) {
      if (!entry.value.valid) {
        errors[entry.key] = entry.value.errorMessage ?? 'Invalid ${entry.key}';
      }
    }
    if (next.categories.isEmpty) {
      errors['category'] = 'Category is required';
    }
    final canSave = results.values.every((r) => r.valid) && next.categories.isNotEmpty;
    return next.copyWith(saveEnabled: canSave, errors: errors);
  }
}

const Map<String, List<List<dynamic>>> _defaultReverseIndex = {
  'jam2': [
    ['飲', 'tier1', 1.0],
    ['喝', 'tier1', 1.0],
    ['飲野', 'tier1', 1.0],
  ],
  'jam2 je5': [
    ['飲野', 'tier1', 1.0],
  ],
};
