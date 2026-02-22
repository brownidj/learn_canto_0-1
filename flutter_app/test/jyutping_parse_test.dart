import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_app/ui/cubits/main/main_cubit.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('Jyutping tokens are parsed by syllable pattern', () {
    final cubit = MainCubit();
    final tokens = cubit
        .debugToneTokens('nei5 sik6 zo2 faan6 mei6 aa3')
        .toList();
    expect(tokens.length, 6);
    expect(tokens[0], 'nei5');
    expect(tokens[5], 'aa3');
  });
}
