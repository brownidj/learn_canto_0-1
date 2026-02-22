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
  testWidgets('Main screen loads', (WidgetTester tester) async {
    final state = MainState.initial().copyWith(
      loading: false,
      hanzi: '你好',
      jyutping: 'nei5 hou2',
      toneBlocks: const [],
    );

    await tester.pumpWidget(
      MaterialApp(
        home: BlocProvider<MainCubit>(
          create: (_) => _TestCubit(state),
          child: const MainView(),
        ),
      ),
    );
    await tester.pump();

    expect(find.text('My Cantonese Words'), findsOneWidget);
    expect(find.text('Transliteration (Jyutping)'), findsOneWidget);
  });
}
