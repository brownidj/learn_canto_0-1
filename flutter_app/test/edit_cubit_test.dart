import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_app/ui/cubits/edit/edit_cubit.dart';
import 'package:flutter_app/ui/cubits/shared/vocab_row.dart';
import 'package:flutter_app/domain/entry_validation.dart';
import 'package:flutter_app/domain/vocabulary_service.dart';

void main() {
  test('EditCubit updates existing entry', () {
    final vocab = <String, dynamic>{
      '你好': [
        ['hello'],
        'nei5 hou2',
      ],
    };
    final cats = <String, List<String>>{'greetings': ['你好'], 'unassigned': []};
    final cubit = EditCubit(
      validator: EntryValidator(),
      vocabService: VocabularyService(vocab: vocab, categories: cats),
      vocabMap: vocab,
      categoriesMap: cats,
    );

    final row = VocabRow(
      hanzi: '你好',
      jyutping: 'nei5 hou2',
      meanings: const ['hello'],
      categories: const ['greetings'],
    );
    final ok = cubit.updateEntry(
      row: row,
      hanzi: '你好呀',
      jyutping: 'nei5 hou2',
      meaningsText: 'hello there',
      categories: const ['greetings'],
    );

    expect(ok, true);
    expect(vocab.containsKey('你好呀'), true);
  });
}
