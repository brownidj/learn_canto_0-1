import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import 'package:flutter_app/ui/screens/add/add_focus_policy.dart';
import 'package:flutter_app/ui/cubits/add_edit/add_edit_cubit.dart';
import 'package:flutter_app/ui/cubits/add_edit/add_edit_state.dart';
import 'package:flutter_app/domain/entry_validation.dart';
import 'package:flutter_app/domain/vocabulary_service.dart';

void main() {
  testWidgets('Category applied focuses candidates when multiple exist', (WidgetTester tester) async {
    final vocab = <String, dynamic>{};
    final cats = <String, List<String>>{'food': []};
    final cubit = AddEditCubit(
      validator: EntryValidator(),
      vocabService: VocabularyService(vocab: vocab, categories: cats),
      vocabMap: vocab,
      categoriesMap: cats,
    );

    final focusPolicy = AddFocusPolicy();
    final hanziFocus = FocusNode();
    final meaningFocus = FocusNode();
    final candidateFocus = FocusNode();

    await tester.pumpWidget(MaterialApp(
      home: BlocProvider.value(
        value: cubit,
        child: Builder(
          builder: (context) {
            return Scaffold(
              body: FocusScope(
                child: Builder(
                  builder: (ctx) {
                    return TextButton(
                      onPressed: () {
                        cubit.setJyutping('jam2');
                        cubit.setCategories(['food']);
                        focusPolicy.handleCategoryApplied(
                          ctx,
                          cubit,
                          hanziFocus: hanziFocus,
                          meaningFocus: meaningFocus,
                          candidateFocus: candidateFocus,
                        );
                      },
                      child: const Text('Go'),
                    );
                  },
                ),
              ),
            );
          },
        ),
      ),
    ));

    await tester.tap(find.text('Go'));
    await tester.pumpAndSettle();

    expect(candidateFocus.hasFocus, true);

    hanziFocus.dispose();
    meaningFocus.dispose();
    candidateFocus.dispose();
  });
}
