import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_app/ui/cubits/main/main_state.dart';
import 'helpers/main_test_harness.dart';

void main() {
  testWidgets('Main screen renders key sections', (WidgetTester tester) async {
    final state = MainState.initial().copyWith(
      loading: false,
      hanzi: '你好',
      jyutping: 'nei5 hou2',
      toneBlocks: const [],
      meanings: const ['hello'],
    );

    final cubit = TestMainCubit();
    await pumpMainView(tester, cubit: cubit, state: state);

    expect(find.text('My Cantonese Words'), findsOneWidget);
    expect(find.text('Translation'), findsOneWidget);
  });

  testWidgets('Drawer shows controls', (WidgetTester tester) async {
    final state = MainState.initial().copyWith(
      loading: false,
      hanzi: '你好',
      jyutping: 'nei5 hou2',
      toneBlocks: const [],
    );

    final cubit = TestMainCubit();
    await pumpMainView(tester, cubit: cubit, state: state);

    final scaffold = tester.state<ScaffoldState>(find.byType(Scaffold));
    scaffold.openDrawer();
    await tester.pumpAndSettle();

    expect(find.text('Voices', skipOffstage: false), findsOneWidget);
    expect(find.text('WPM (60-220): 120', skipOffstage: false), findsOneWidget);
    expect(find.text('Reset', skipOffstage: false), findsOneWidget);
  });
}
