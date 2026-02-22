import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_app/ui/screens/dialogs/category_dialog.dart';
import 'package:flutter_app/ui/cubits/add_edit/add_edit_state.dart';

void main() {
  testWidgets('Category dialog enables Select after a choice', (WidgetTester tester) async {
    final state = AddEditState.initial().copyWith(availableCategories: ['greetings']);

    await tester.pumpWidget(MaterialApp(
      home: Builder(
        builder: (context) {
          return Scaffold(
            body: TextButton(
              onPressed: () {
                showCategoryDialog(
                  context,
                  state: state,
                  onChanged: (_) {},
                  onAddCategory: (_) {},
                );
              },
              child: const Text('Open'),
            ),
          );
        },
      ),
    ));

    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();

    final selectButton = tester.widget<TextButton>(find.widgetWithText(TextButton, 'Select'));
    expect(selectButton.onPressed, isNull);

    await tester.tap(find.widgetWithText(CheckboxListTile, 'greetings'));
    await tester.pumpAndSettle();

    final tile = tester.widget<CheckboxListTile>(find.widgetWithText(CheckboxListTile, 'greetings'));
    expect(tile.value, true);

    final selectButtonAfter = tester.widget<TextButton>(find.widgetWithText(TextButton, 'Select'));
    expect(selectButtonAfter.onPressed, isNotNull);
  });
}
