import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_app/ui/cubits/add_edit/add_edit_cubit.dart';
import 'package:flutter_app/domain/entry_validation.dart';
import 'package:flutter_app/domain/vocabulary_service.dart';

void main() {
  test('AddEditCubit enables save only when valid and saves entry', () {
    final vocab = <String, dynamic>{};
    final cats = <String, List<String>>{'unassigned': []};
    final cubit = AddEditCubit(
      validator: EntryValidator(),
      vocabService: VocabularyService(vocab: vocab, categories: cats),
      vocabMap: vocab,
      categoriesMap: cats,
    );

    expect(cubit.state.saveEnabled, false);

    cubit.setJyutping('nei5 hou2');
    cubit.setHanzi('你好');
    cubit.setMeaning('hello');
    cubit.setCategories(['greetings']);
    cubit.selectCandidate('你好');

    expect(cubit.state.saveEnabled, true);

    final ok = cubit.save();
    expect(ok, true);
    expect(vocab.containsKey('你好'), true);
  });

  test('AddEditCubit sets notes when ambiguous', () {
    final vocab = <String, dynamic>{};
    final cats = <String, List<String>>{'unassigned': []};
    final cubit = AddEditCubit(
      validator: EntryValidator(),
      vocabService: VocabularyService(vocab: vocab, categories: cats),
      vocabMap: vocab,
      categoriesMap: cats,
    );

    cubit.setJyutping('nei5 hou2');
    expect(cubit.state.notes.isNotEmpty, true);
  });

  test('AddEditCubit blocks reserved categories', () {
    final vocab = <String, dynamic>{};
    final cats = <String, List<String>>{'unassigned': []};
    final cubit = AddEditCubit(
      validator: EntryValidator(),
      vocabService: VocabularyService(vocab: vocab, categories: cats),
      vocabMap: vocab,
      categoriesMap: cats,
    );

    cubit.setJyutping('nei5 hou2');
    cubit.setHanzi('你好');
    cubit.setMeaning('hello');
    cubit.setCategories(['unassigned']);

    expect(cubit.state.saveEnabled, false);
  });

}
