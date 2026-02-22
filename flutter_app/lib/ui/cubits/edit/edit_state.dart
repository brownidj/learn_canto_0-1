import '../shared/vocab_row.dart';

class EditState {
  final List<VocabRow> vocabRows;
  final String searchQuery;
  final String? toastMessage;

  const EditState({
    required this.vocabRows,
    required this.searchQuery,
    this.toastMessage,
  });

  factory EditState.initial() {
    return const EditState(
      vocabRows: <VocabRow>[],
      searchQuery: '',
      toastMessage: null,
    );
  }

  EditState copyWith({
    List<VocabRow>? vocabRows,
    String? searchQuery,
    String? toastMessage,
  }) {
    return EditState(
      vocabRows: vocabRows ?? this.vocabRows,
      searchQuery: searchQuery ?? this.searchQuery,
      toastMessage: toastMessage,
    );
  }
}
