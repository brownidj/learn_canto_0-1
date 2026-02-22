import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_app/ui/cubits/main/main_cubit.dart';
import 'package:flutter_app/ui/cubits/main/main_state.dart';
import 'package:flutter_app/ui/screens/main/main_screen.dart';

class TestMainCubit extends MainCubit {
  TestMainCubit() : super();

  @override
  Future<void> loadData() async {}
}

Future<void> pumpMainView(
  WidgetTester tester, {
  required TestMainCubit cubit,
  required MainState state,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      home: BlocProvider<MainCubit>.value(
        value: cubit,
        child: const MainView(),
      ),
    ),
  );
  cubit.emit(state);
  await tester.pump();
  await tester.pump();
}
