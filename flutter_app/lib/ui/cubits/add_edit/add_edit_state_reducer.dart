import '../../../domain/entry_validation.dart';
import 'add_edit_state.dart';

class AddEditStateReducer {
  final EntryValidator validator;

  const AddEditStateReducer({required this.validator});

  AddEditState recalc(AddEditState next) {
    final rawCategory = next.categories.isNotEmpty ? next.categories.first : '';
    var category = rawCategory;
    final catLower = rawCategory.trim().toLowerCase();
    if (catLower == 'all' || catLower == 'unassigned') {
      category = '';
    }
    final results = validator.validateAll(
      jyutping: next.jyutping,
      hanzi: next.hanzi,
      meanings: next.meaningText,
      category: category,
    );
    final errors = <String, String>{};
    for (final entry in results.entries) {
      if (!entry.value.valid) {
        errors[entry.key] = entry.value.errorMessage ?? 'Invalid ${entry.key}';
      }
    }
    if (next.categories.isEmpty || catLower == 'all' || catLower == 'unassigned') {
      errors['category'] = 'Category is required';
    }
    final canSave = results.values.every((r) => r.valid) &&
        next.categories.isNotEmpty &&
        catLower != 'all' &&
        catLower != 'unassigned';
    final phase = _derivePhase(next, canSave: canSave, errors: errors);
    return next.copyWith(saveEnabled: canSave, errors: errors, phase: phase);
  }

  AddEditState resetEntry(AddEditState state, {String? toastMessage}) {
    final cleared = state.copyWith(
      jyutping: '',
      hanzi: '',
      meaningText: '',
      notes: '',
      categories: <String>[],
      saveEnabled: false,
      errors: <String, String>{},
      candidateItems: <CandidateItem>[],
      selectedHanzi: '',
      meaningsPreview: <String>[],
      meaningSourceTag: '',
      meaningsFull: <String>[],
      register: '',
      duplicateWarning: null,
      manualHanzi: false,
      phase: AddEditPhase.empty,
      saving: false,
      toastMessage: toastMessage,
    );
    return recalc(cleared);
  }

  AddEditPhase _derivePhase(
    AddEditState next, {
    required bool canSave,
    required Map<String, String> errors,
  }) {
    if (canSave) {
      return AddEditPhase.readyToSave;
    }
    final jyOk = next.jyutping.trim().isNotEmpty && !errors.containsKey('jyutping');
    if (!jyOk) {
      return AddEditPhase.empty;
    }
    if (next.categories.isNotEmpty) {
      return AddEditPhase.categoryCommitted;
    }
    return AddEditPhase.jyutpingCommitted;
  }
}
