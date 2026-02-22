import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_app/ui/cubits/main/main_cubit.dart';
import 'package:flutter_app/ui/cubits/main/main_state.dart';
import 'package:flutter_app/ui/screens/main/main_screen.dart';

class _TestCubit extends MainCubit {
  _TestCubit(MainState state) : super() {
    emit(state);
  }

  @override
  Future<void> loadData() async {}
}

void main() {
  testWidgets('Tone grid renders 6 tiles for 6 syllables', (WidgetTester tester) async {
    final state = MainState.initial().copyWith(
      loading: false,
      jyutping: 'nei5 sik6 zo2 faan6 mei6 aa3',
      hanzi: '你食左飯未呀',
      toneBlocks: List.generate(
        6,
        (i) => ToneBlock(
          label: 'T$i',
          syllable: 'syl$i',
          tone: 1,
          hint: '',
        ),
      ),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: BlocProvider<MainCubit>(
          create: (_) => _TestCubit(state),
          child: const MainView(),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(GridView), findsOneWidget);
    expect(find.byType(ToneBlockTile), findsNWidgets(6));
  });
}
