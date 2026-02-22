import 'package:flutter/foundation.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import '../../../domain/entry_validation.dart';
import '../../../domain/vocabulary_service.dart';
import '../../../domain/exceptions.dart';
import '../../../domain/meaning_sources_models.dart';
import '../../../domain/meaning_sources_cleaning.dart';
import '../../../data/asset_data_repository.dart';
import 'add_edit_state.dart';
import 'add_edit_candidate_service.dart';
import 'add_edit_state_reducer.dart';
import 'add_edit_payload_mapper.dart';

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
  late AddEditCandidateService _candidateService;
  late AddEditStateReducer _stateReducer;
  late AddEditPayloadMapper _payloadMapper;

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
        super(AddEditState.initial()) {
    _initHelpers();
  }

  void _initHelpers() {
    _candidateService = AddEditCandidateService(
      meaningFacade: _meaningFacade,
      reverseIndex: _reverseIndex,
      hkWords: _hkWords,
      cccantoMap: _cccantoMap,
      cedictMap: _cedictMap,
    );
    _stateReducer = AddEditStateReducer(validator: _validator);
    _payloadMapper = const AddEditPayloadMapper();
  }

  void setJyutping(String value) {
    emit(_recalc(state.copyWith(jyutping: value, manualHanzi: false)));
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

  void setManualHanzi(bool enabled) {
    emit(_recalc(state.copyWith(manualHanzi: enabled)));
  }

  void selectCandidate(String hanzi) {
    final base = state.copyWith(selectedHanzi: hanzi, hanzi: hanzi);
    final withMeaning = _applyMeaningFromCandidate(base, hanzi);
    emit(_recalc(withMeaning));
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
      _initHelpers();
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
    debugPrint(
      '[AddEditCubit] refreshCandidates jy="${jy}" '
      'cats=${state.categories.length} reverseSize=${_reverseIndex.length}',
    );
    if (jy.isEmpty) {
      debugPrint('[AddEditCubit] refreshCandidates empty jy -> clear');
      emit(
        _recalc(
          state.copyWith(
            candidateItems: <CandidateItem>[],
            selectedHanzi: '',
            meaningsPreview: <String>[],
            meaningsFull: <String>[],
            meaningSourceTag: '',
            meaningText: '',
            hanzi: '',
            manualHanzi: false,
            notes: '',
          ),
        ),
      );
      return;
    }
    final resolution = _candidateService.resolve(
      jyutping: jy,
      activeCategories: state.categories,
    );
    if (resolution.candidates.isEmpty) {
      emit(
        _recalc(
          state.copyWith(
            candidateItems: const <CandidateItem>[],
            selectedHanzi: '',
            meaningsPreview: const <String>[],
            meaningsFull: const <String>[],
            meaningSourceTag: '',
            manualHanzi: resolution.manualHanzi,
            notes: resolution.notes,
          ),
        ),
      );
      return;
    }
    emit(
      _recalc(
        state.copyWith(
          candidateItems: resolution.candidates,
          selectedHanzi: resolution.selectedHanzi,
          hanzi: resolution.selectedHanzi,
          meaningText: resolution.meaningText,
          meaningsPreview: resolution.meaningsPreview,
          meaningsFull: resolution.meaningsFull,
          meaningSourceTag: resolution.meaningSourceTag,
          manualHanzi: resolution.manualHanzi,
          notes: resolution.notes,
        ),
      ),
    );
  }

  void _updateMeaningPreview(String hanzi) {
    final hz = hanzi.trim();
    if (hz.isEmpty) {
      emit(state.copyWith(meaningsPreview: <String>[], meaningsFull: <String>[], meaningSourceTag: ''));
      return;
    }
    final full = _meaningFacade.meaningsForDisplay(hz);
    final preview = full.take(3).toList();
    final tag = _candidateService.meaningSourceTagFor(hz);
    emit(state.copyWith(meaningsPreview: preview, meaningsFull: full, meaningSourceTag: tag));
  }

  AddEditState _applyMeaningFromCandidate(AddEditState base, String hanzi) {
    final hz = hanzi.trim();
    if (hz.isEmpty) {
      return base.copyWith(
        meaningText: '',
        meaningsPreview: <String>[],
        meaningsFull: <String>[],
        meaningSourceTag: '',
      );
    }
    final full = _meaningFacade.meaningsForDisplay(hz);
    final preview = full.take(3).toList();
    final tag = _candidateService.meaningSourceTagFor(hz);
    if (full.isEmpty) {
      return base.copyWith(
        meaningsPreview: <String>[],
        meaningsFull: <String>[],
        meaningSourceTag: '',
      );
    }
    final joined = full.join(', ');
    return base.copyWith(
      meaningText: joined,
      meaningsPreview: preview,
      meaningsFull: full,
      meaningSourceTag: tag,
    );
  }


  bool save() {
    try {
    _vocabService.addEntry(
      jyutping: state.jyutping,
      hanzi: state.hanzi,
      meanings: state.meaningText,
      categories: state.categories,
      notes: state.notes,
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
      emit(_resetEntryState(toastMessage: 'Saved'));
      return true;
    } on VocabularyError {
      emit(_recalc(state));
      return false;
    }
  }

  void resetEntry() {
    emit(_resetEntryState());
  }

  Map<String, dynamic> previewPayload() {
    return _payloadMapper.toPreviewPayload(state);
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
    return _stateReducer.recalc(next);
  }

  AddEditState _resetEntryState({String? toastMessage}) {
    final cleared = _stateReducer.resetEntry(state, toastMessage: toastMessage);
    return cleared;
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
