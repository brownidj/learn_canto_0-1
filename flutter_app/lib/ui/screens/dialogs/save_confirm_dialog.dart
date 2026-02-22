import 'package:flutter/material.dart';

enum SaveDecision { save, edit, cancel }

Future<SaveDecision?> showSaveDecision(BuildContext context, Map<String, dynamic> payload) {
  final jy = payload['jyutping'] as String? ?? '';
  final hz = payload['hanzi'] as String? ?? '';
  final meanings = (payload['meanings'] as List?)?.join(', ') ?? '';
  final cats = (payload['categories'] as List?)?.join(', ') ?? '';
  final reg = payload['register'] as String? ?? '';
  final notes = (payload['notes'] as String? ?? '').trim();
  return showDialog<SaveDecision>(
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
            if (notes.isNotEmpty) Text('Notes: $notes'),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(SaveDecision.cancel),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(SaveDecision.edit),
            child: const Text('Edit'),
          ),
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(SaveDecision.save),
            child: const Text('Save'),
          ),
        ],
      );
    },
  );
}

Future<bool?> showSaveConfirm(BuildContext context, Map<String, dynamic> payload) async {
  final decision = await showSaveDecision(context, payload);
  if (decision == SaveDecision.save) {
    return true;
  }
  if (decision == SaveDecision.cancel) {
    return false;
  }
  return null;
}
