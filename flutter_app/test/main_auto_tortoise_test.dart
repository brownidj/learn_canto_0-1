import 'dart:async';

import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_app/ui/cubits/main/main_cubit.dart';
import 'package:flutter_app/ui/cubits/main/main_state.dart';

class _AutoTestCubit extends MainCubit {
  int playCount = 0;
  int nextCount = 0;

  @override
  Future<void> loadData() async {}

  @override
  Future<void> playSequence() async {
    if (state.isPlaying) {
      return;
    }
    playCount += 1;
    emit(state.copyWith(isPlaying: true));
    await Future.delayed(const Duration(milliseconds: 100));
    emit(state.copyWith(isPlaying: false));
  }

  @override
  void nextItem() {
    nextCount += 1;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test('Auto stops and does not advance after toggling off', () {
    fakeAsync((async) {
      final cubit = _AutoTestCubit();
      cubit.emit(MainState.initial().copyWith(ttsArmed: true, autoDelay: 0));

      cubit.toggleAuto(true);
      async.elapse(const Duration(milliseconds: 250));

      final playedAtStop = cubit.playCount;
      final advancedAtStop = cubit.nextCount;

      cubit.toggleAuto(false);
      async.elapse(const Duration(seconds: 1));

      expect(cubit.state.autoMode, isFalse);
      expect(cubit.state.isPlaying, isFalse);
      expect(cubit.playCount, playedAtStop);
      expect(cubit.nextCount, advancedAtStop);
    });
  });

  test('Slow mode toggles wpm only when allowed', () {
    final cubit = _AutoTestCubit();
    final base = MainState.initial().copyWith(
      ttsArmed: true,
      autoMode: false,
      isPlaying: false,
      wpm: 120,
    );
    cubit.emit(base);

    cubit.toggleTortoise(true);
    expect(cubit.state.tortoise, isTrue);
    expect(cubit.state.wpm, 60);

    cubit.toggleTortoise(false);
    expect(cubit.state.tortoise, isFalse);
    expect(cubit.state.wpm, 120);

    cubit.emit(base.copyWith(autoMode: true));
    cubit.toggleTortoise(true);
    expect(cubit.state.tortoise, isFalse);
    expect(cubit.state.wpm, 120);
  });
}
