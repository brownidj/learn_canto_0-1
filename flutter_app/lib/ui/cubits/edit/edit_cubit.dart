import 'package:flutter/foundation.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import '../../../domain/entry_validation.dart';
import '../../../domain/vocabulary_service.dart';
import '../../../domain/exceptions.dart';
import '../../../data/asset_data_repository.dart';
import '../add_edit/add_edit_vocab_service.dart';
import '../shared/vocab_row.dart';
import 'edit_state.dart';

class EditCubit extends Cubit<EditState> {
  final EntryValidator _validator;
  final VocabularyService _vocabService;
  final Map<String, dynamic> _vocabMap;
  final Map<String, List<String>> _categoriesMap;
  final AddEditVocabService _vocabServiceHelper;
  AssetDataRepository? _repo;

  EditCubit({
    required EntryValidator validator,
    required VocabularyService vocabService,
    required Map<String, dynamic> vocabMap,
    required Map<String, List<String>> categoriesMap,
  })  : _validator = validator,
        _vocabService = vocabService,
        _vocabMap = vocabMap,
        _categoriesMap = categoriesMap,
        _vocabServiceHelper = AddEditVocabService(
          vocabMap: vocabMap,
          categoriesMap: categoriesMap,
        ),
        super(EditState.initial());

  Future<void> loadData(AssetDataRepository repo) async {
    _repo = repo;
    try {
      debugPrint('[EditCubit] loadData start');
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
      emit(state.copyWith(vocabRows: _vocabServiceHelper.buildRows()));
    } catch (_) {
      // Keep defaults if asset loading fails.
    }
  }

  void setSearchQuery(String value) {
    emit(state.copyWith(searchQuery: value));
  }

  bool updateEntry({
    required VocabRow row,
    required String hanzi,
    required String jyutping,
    required String meaningsText,
    required List<String> categories,
  }) {
    final results = _validator.validateAll(
      jyutping: jyutping,
      hanzi: hanzi,
      meanings: meaningsText,
      category: categories.isNotEmpty ? categories.first : '',
    );
    if (results.values.any((r) => !r.valid)) {
      emit(state.copyWith(toastMessage: 'Invalid entry'));
      return false;
    }
    try {
      _vocabService.updateEntry(
        originalHanzi: row.hanzi,
        jyutping: jyutping,
        hanzi: hanzi,
        meanings: meaningsText,
        categories: categories,
        notes: '',
      );
      emit(state.copyWith(vocabRows: _vocabServiceHelper.buildRows(), toastMessage: 'Updated'));
      return true;
    } on VocabularyError {
      emit(state.copyWith(toastMessage: 'Update failed'));
      return false;
    }
  }
}
