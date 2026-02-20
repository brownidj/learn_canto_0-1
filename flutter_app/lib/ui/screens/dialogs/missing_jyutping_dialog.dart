import 'package:flutter/material.dart';

enum MissingJyutpingChoice { chatgpt, manual }

Future<MissingJyutpingChoice?> showMissingJyutpingDialog(
  BuildContext context,
  String jyutping,
) {
  return showDialog<MissingJyutpingChoice>(
    context: context,
    builder: (ctx) {
      return AlertDialog(
        title: const Text('No candidates found', style: TextStyle(fontSize: 12)),
        content: Text(
          jyutping.isEmpty
              ? 'No candidates found for this Jyutping.'
              : 'No candidates found for "$jyutping".',
          style: const TextStyle(fontSize: 11),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(MissingJyutpingChoice.chatgpt),
            child: const Text('Use ChatGPT', style: TextStyle(fontSize: 11)),
          ),
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(MissingJyutpingChoice.manual),
            child: const Text('Enter manually', style: TextStyle(fontSize: 11)),
          ),
        ],
      );
    },
  );
}
