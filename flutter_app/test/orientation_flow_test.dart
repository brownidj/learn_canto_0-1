import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_app/main.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  Future<void> _setSize(WidgetTester tester, Size size) async {
    tester.binding.window.physicalSizeTestValue = size;
    tester.binding.window.devicePixelRatioTestValue = 1.0;
    addTearDown(() {
      tester.binding.window.clearPhysicalSizeTestValue();
      tester.binding.window.clearDevicePixelRatioTestValue();
    });
    await tester.pump();
  }

  Future<void> _pumpUntilFound(WidgetTester tester, Finder finder, {int maxPumps = 10}) async {
    for (var i = 0; i < maxPumps; i += 1) {
      await tester.pump(const Duration(milliseconds: 50));
      if (finder.evaluate().isNotEmpty) {
        return;
      }
    }
  }

  testWidgets('Rotation flow switches between Main/Add/Edit', (tester) async {
    await _setSize(tester, const Size(400, 800)); // portrait
    await tester.pumpWidget(const LearnCantoApp());
    await tester.pump();
    expect(find.text('Start'), findsOneWidget);
    await tester.tap(find.text('Start'));
    await _pumpUntilFound(tester, find.text('My Cantonese Words'));
    expect(find.text('My Cantonese Words'), findsOneWidget);

    // Rotate to landscape -> Add
    await _setSize(tester, const Size(800, 400));
    await tester.pump();
    expect(find.text('Add (Prototype)'), findsOneWidget);

    // Tap Edit -> Edit screen (locked to portrait)
    await tester.tap(find.text('Edit'));
    await tester.pump();
    expect(find.text('Edit (Prototype)'), findsOneWidget);

    // Tap Return -> back to Main (portrait)
    await tester.tap(find.text('Return'));
    await tester.pump();
    await _setSize(tester, const Size(400, 800));
    await tester.pump();
    expect(find.text('My Cantonese Words'), findsOneWidget);

    // Rotate to landscape -> Add
    await _setSize(tester, const Size(800, 400));
    await tester.pump();
    expect(find.text('Add (Prototype)'), findsOneWidget);

    // Rotate to portrait -> Main
    await _setSize(tester, const Size(400, 800));
    await tester.pump();
    expect(find.text('My Cantonese Words'), findsOneWidget);
  });
}
