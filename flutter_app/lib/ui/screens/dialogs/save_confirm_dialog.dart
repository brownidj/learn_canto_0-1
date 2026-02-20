import 'package:flutter/material.dart';

Future<bool?> showSaveConfirm(BuildContext context, Map<String, dynamic> payload) {
  final jy = payload['jyutping'] as String? ?? '';
  final hz = payload['hanzi'] as String? ?? '';
  final meanings = (payload['meanings'] as List?)?.join(', ') ?? '';
  final cats = (payload['categories'] as List?)?.join(', ') ?? '';
  final reg = payload['register'] as String? ?? '';
  return showDialog<bool>(
    context: context,
    builder: (ctx) {
      return AlertDialog(
        title: const Text('Confirm Save'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Jyutping: $jy'),
            Text('Hanzi: $hz'),
            Text('Meanings: $meanings'),
            Text('Categories: $cats'),
            if (reg.isNotEmpty) Text('Register: $reg'),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Save'),
          ),
        ],
      );
    },
  );
}
