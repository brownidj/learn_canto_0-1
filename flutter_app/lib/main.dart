import 'package:flutter/material.dart';
import 'ui/screens/add/add_screen.dart';

void main() {
  runApp(const LearnCantoApp());
}

class LearnCantoApp extends StatelessWidget {
  const LearnCantoApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'LearnCanto',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF4B7BAA)),
      ),
      home: const AddScreen(),
    );
  }
}
