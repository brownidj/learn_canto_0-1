import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_app/ui/cubits/main/main_state.dart';
import 'helpers/main_test_harness.dart';

void main() {
  testWidgets('Buttons gated by ttsArmed and auto mode', (WidgetTester tester) async {
    final base = MainState.initial().copyWith(
      loading: false,
      hanzi: '你好',
      jyutping: 'nei5 hou2',
      toneBlocks: const [],
      isPlaying: false,
    );

    final cubit = TestMainCubit();

    // ttsArmed=false, autoMode=false
    await pumpMainView(tester, cubit: cubit, state: base.copyWith(ttsArmed: false, autoMode: false));
    final playBtn1 = tester.widget<ElevatedButton>(find.byKey(const Key('btnPlay')));
    expect(playBtn1.onPressed != null, isTrue);
    final prevBtn1 = tester.widget<ElevatedButton>(find.byKey(const Key('btnPrev')));
    final nextBtn1 = tester.widget<ElevatedButton>(find.byKey(const Key('btnNext')));
    expect(prevBtn1.onPressed, isNull);
    expect(nextBtn1.onPressed, isNull);
    final slowChip1 = tester.widget<FilterChip>(find.byKey(const Key('chipSlow')));
    final autoChip1 = tester.widget<FilterChip>(find.byKey(const Key('chipAuto')));
    expect(slowChip1.onSelected, isNull);
    expect(autoChip1.onSelected, isNull);

    // ttsArmed=true, autoMode=false
    await pumpMainView(tester, cubit: cubit, state: base.copyWith(ttsArmed: true, autoMode: false));
    final playBtn2 = tester.widget<ElevatedButton>(find.byKey(const Key('btnPlay')));
    expect(playBtn2.onPressed != null, isTrue);
    final prevBtn2 = tester.widget<ElevatedButton>(find.byKey(const Key('btnPrev')));
    final nextBtn2 = tester.widget<ElevatedButton>(find.byKey(const Key('btnNext')));
    expect(prevBtn2.onPressed != null, isTrue);
    expect(nextBtn2.onPressed != null, isTrue);
    final slowChip2 = tester.widget<FilterChip>(find.byKey(const Key('chipSlow')));
    final autoChip2 = tester.widget<FilterChip>(find.byKey(const Key('chipAuto')));
    expect(slowChip2.onSelected != null, isTrue);
    expect(autoChip2.onSelected != null, isTrue);

    // autoMode=true
    await pumpMainView(tester, cubit: cubit, state: base.copyWith(ttsArmed: true, autoMode: true));
    final playBtn3 = tester.widget<ElevatedButton>(find.byKey(const Key('btnPlay')));
    expect(playBtn3.onPressed, isNull);
    final prevBtn3 = tester.widget<ElevatedButton>(find.byKey(const Key('btnPrev')));
    final nextBtn3 = tester.widget<ElevatedButton>(find.byKey(const Key('btnNext')));
    expect(prevBtn3.onPressed, isNull);
    expect(nextBtn3.onPressed, isNull);
    final slowChip3 = tester.widget<FilterChip>(find.byKey(const Key('chipSlow')));
    final autoChip3 = tester.widget<FilterChip>(find.byKey(const Key('chipAuto')));
    expect(slowChip3.onSelected, isNull);
    expect(autoChip3.onSelected != null, isTrue);
  });

  testWidgets('Category dropdown disabled in auto mode', (WidgetTester tester) async {
    final base = MainState.initial().copyWith(
      loading: false,
      hanzi: '你好',
      jyutping: 'nei5 hou2',
      toneBlocks: const [],
    );
    final cubit = TestMainCubit();
    await pumpMainView(tester, cubit: cubit, state: base.copyWith(autoMode: true, ttsArmed: true));

    final dropdown = tester.widget<DropdownButtonFormField<String>>(
      find.byType(DropdownButtonFormField<String>),
    );
    expect(dropdown.onChanged, isNull);
  });
}
