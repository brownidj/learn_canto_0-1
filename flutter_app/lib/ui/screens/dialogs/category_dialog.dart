import 'package:flutter/material.dart';
import '../../cubits/add_edit/add_edit_state.dart';

Future<void> showCategoryDialog(
  BuildContext context, {
  required AddEditState state,
  required ValueChanged<List<String>> onChanged,
  required ValueChanged<String> onAddCategory,
  VoidCallback? onApplied,
}) async {
  final next = Set<String>.from(state.categories);
  final result = await showDialog<Set<String>>(
    context: context,
    barrierDismissible: false,
    builder: (ctx) {
      final addController = TextEditingController();
      return AlertDialog(
        title: const Text('Select categories', style: TextStyle(fontSize: 12)),
        titlePadding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
        contentPadding: const EdgeInsets.fromLTRB(12, 6, 12, 0),
        actionsPadding: const EdgeInsets.fromLTRB(12, 0, 12, 6),
        insetPadding: const EdgeInsets.all(12),
        content: StatefulBuilder(
          builder: (ctx2, setState) {
            final filtered = List<String>.from(state.availableCategories)..sort();
            final hasSelection = next.isNotEmpty;
            return SizedBox(
              width: 260,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  TextField(
                    controller: addController,
                    decoration: const InputDecoration(
                      labelText: 'Add new category',
                      prefixIcon: Icon(Icons.add),
                    ),
                    style: const TextStyle(fontSize: 11),
                    textInputAction: TextInputAction.done,
                    onSubmitted: (val) {
                      final v = val.trim();
                      if (v.isEmpty) {
                        return;
                      }
                      setState(() {
                        next.add(v);
                      });
                    },
                    stylusHandwritingEnabled: false,
                  ),
                  const SizedBox(height: 4),
                  Flexible(
                    child: Scrollbar(
                      thumbVisibility: true,
                      child: ListView(
                        shrinkWrap: true,
                        children: [
                          for (final c in filtered)
                            CheckboxListTile(
                              dense: true,
                              visualDensity: const VisualDensity(horizontal: -4, vertical: -4),
                              contentPadding: EdgeInsets.zero,
                              title: Text(c, style: const TextStyle(fontSize: 11)),
                              value: next.contains(c),
                              onChanged: (checked) {
                                setState(() {
                                  if (checked == true) {
                                    next.add(c);
                                  } else {
                                    next.remove(c);
                                  }
                                });
                              },
                            ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            );
          },
        ),
        actions: [
          TextButton(
            onPressed: next.isNotEmpty
                ? () {
                    next.clear();
                    Navigator.of(ctx).pop(next);
                  }
                : null,
            child: const Text('Clear', style: TextStyle(fontSize: 11)),
          ),
          TextButton(
            onPressed: next.isNotEmpty ? () => Navigator.of(ctx).pop(null) : null,
            child: const Text('Cancel', style: TextStyle(fontSize: 11)),
          ),
          TextButton(
            onPressed: next.isNotEmpty
                ? () {
                    for (final v in next) {
                      if (!state.availableCategories.contains(v)) {
                        onAddCategory(v);
                      }
                    }
                    Navigator.of(ctx).pop(next);
                  }
                : null,
            child: const Text('Apply', style: TextStyle(fontSize: 11)),
          ),
        ],
      );
    },
  );
  if (result != null) {
    onChanged(result.toList());
    onApplied?.call();
  }
}
