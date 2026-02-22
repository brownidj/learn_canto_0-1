import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_app/ui/cubits/main/main_state.dart';
import 'helpers/main_test_harness.dart';

void main() {
  testWidgets('Bottom bar does not overflow on small device', (WidgetTester tester) async {
    tester.binding.window.physicalSizeTestValue = const Size(360, 640);
    tester.binding.window.devicePixelRatioTestValue = 1.0;
    addTearDown(() {
      tester.binding.window.clearPhysicalSizeTestValue();
      tester.binding.window.clearDevicePixelRatioTestValue();
    });

    final state = MainState.initial().copyWith(
      loading: false,
      hanzi: '你好',
      jyutping: 'nei5 hou2',
      toneBlocks: const [],
    );

    final cubit = TestMainCubit();
    await pumpMainView(tester, cubit: cubit, state: state);

    expect(find.text('Play'), findsOneWidget);
  });
}
