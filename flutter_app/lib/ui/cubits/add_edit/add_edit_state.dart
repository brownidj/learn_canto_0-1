enum AddEditPhase {
  empty,
  jyutpingCommitted,
  categoryCommitted,
  readyToSave,
}

class AddEditState {
  final String jyutping;
  final String hanzi;
  final String meaningText;
  final String notes;
  final List<String> categories;
  final bool saveEnabled;
  final AddEditPhase phase;
  final bool saving;
  final bool manualHanzi;
  final Map<String, String> errors;
  final List<CandidateItem> candidateItems;
  final String selectedHanzi;
  final List<String> meaningsPreview;
  final String meaningSourceTag;
  final List<String> meaningsFull;
  final String register;
  final List<String> availableCategories;
  final String? toastMessage;
  final String? duplicateWarning;

  const AddEditState({
    required this.jyutping,
    required this.hanzi,
    required this.meaningText,
    required this.notes,
    required this.categories,
    required this.saveEnabled,
    required this.phase,
    required this.saving,
    required this.manualHanzi,
    required this.errors,
    required this.candidateItems,
    required this.selectedHanzi,
    required this.meaningsPreview,
    required this.meaningSourceTag,
    required this.meaningsFull,
    required this.register,
    required this.availableCategories,
    this.toastMessage,
    this.duplicateWarning,
  });

  factory AddEditState.initial() {
    return const AddEditState(
      jyutping: '',
      hanzi: '',
      meaningText: '',
      notes: '',
      categories: <String>[],
      saveEnabled: false,
      phase: AddEditPhase.empty,
      saving: false,
      manualHanzi: false,
      errors: <String, String>{},
      candidateItems: <CandidateItem>[],
      selectedHanzi: '',
      meaningsPreview: <String>[],
      meaningSourceTag: '',
      meaningsFull: <String>[],
      register: '',
      availableCategories: <String>['greetings', 'food', 'people', 'places', 'time', 'weather'],
      toastMessage: null,
      duplicateWarning: null,
    );
  }

  AddEditState copyWith({
    String? jyutping,
    String? hanzi,
    String? meaningText,
    String? notes,
    List<String>? categories,
    bool? saveEnabled,
    AddEditPhase? phase,
    bool? saving,
    bool? manualHanzi,
    Map<String, String>? errors,
    List<CandidateItem>? candidateItems,
    String? selectedHanzi,
    List<String>? meaningsPreview,
    String? meaningSourceTag,
    List<String>? meaningsFull,
    String? register,
    List<String>? availableCategories,
    String? toastMessage,
    String? duplicateWarning,
  }) {
    return AddEditState(
      jyutping: jyutping ?? this.jyutping,
      hanzi: hanzi ?? this.hanzi,
      meaningText: meaningText ?? this.meaningText,
      notes: notes ?? this.notes,
      categories: categories ?? this.categories,
      saveEnabled: saveEnabled ?? this.saveEnabled,
      phase: phase ?? this.phase,
      saving: saving ?? this.saving,
      manualHanzi: manualHanzi ?? this.manualHanzi,
      errors: errors ?? this.errors,
      candidateItems: candidateItems ?? this.candidateItems,
      selectedHanzi: selectedHanzi ?? this.selectedHanzi,
      meaningsPreview: meaningsPreview ?? this.meaningsPreview,
      meaningSourceTag: meaningSourceTag ?? this.meaningSourceTag,
      meaningsFull: meaningsFull ?? this.meaningsFull,
      register: register ?? this.register,
      availableCategories: availableCategories ?? this.availableCategories,
      toastMessage: toastMessage,
      duplicateWarning: duplicateWarning,
    );
  }
}

class CandidateItem {
  final String hanzi;
  final String source;
  final String label;
  final String? hkBadge;
  final String? sourceTag;

  const CandidateItem({
    required this.hanzi,
    required this.source,
    required this.label,
    this.hkBadge,
    this.sourceTag,
  });
}
