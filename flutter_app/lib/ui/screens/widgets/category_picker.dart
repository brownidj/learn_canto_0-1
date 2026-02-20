import 'package:flutter/material.dart';
import 'field_block.dart';

class CategoryPicker extends StatelessWidget {
  final List<String> selected;
  final ValueChanged<List<String>> onChanged;
  final String? error;
  final List<String> allCategories;
  final ValueChanged<String> onAddCategory;
  final FocusNode? focusNode;
  final ValueChanged<BuildContext> onOpen;
  final ValueChanged<String>? onSubmitted;
  final bool labelLeft;
  final bool enabled;

  const CategoryPicker({
    super.key,
    required this.selected,
    required this.onChanged,
    required this.error,
    required this.allCategories,
    required this.onAddCategory,
    required this.focusNode,
    required this.onOpen,
    required this.onSubmitted,
    this.labelLeft = false,
    this.enabled = true,
  });

  @override
  Widget build(BuildContext context) {
    final label = selected.isEmpty ? '' : selected.join(', ');
    return FieldBlock(
      label: 'Categories',
      error: error,
      onChanged: (_) {},
      focusNode: focusNode,
      onSubmitted: onSubmitted,
      labelLeft: labelLeft,
      trailing: ActionChip(
        label: const Icon(Icons.arrow_drop_down, size: 16),
        onPressed: enabled && selected.isNotEmpty ? () => onOpen(context) : null,
      ),
      initialValue: label,
      readOnly: true,
      onTap: enabled ? () => onOpen(context) : null,
      enabled: enabled,
    );
  }
}
