import 'package:flutter/material.dart';
import 'field_block.dart';

class CategoryPicker extends StatefulWidget {
  final List<String> selected;
  final ValueChanged<List<String>> onChanged;
  final String? error;
  final List<String> allCategories;
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
    required this.focusNode,
    required this.onOpen,
    required this.onSubmitted,
    this.labelLeft = false,
    this.enabled = true,
  });

  @override
  State<CategoryPicker> createState() => _CategoryPickerState();
}

class _CategoryPickerState extends State<CategoryPicker> {

  @override
  Widget build(BuildContext context) {
    final label = widget.selected.isEmpty ? '' : widget.selected.join(', ');
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        FieldBlock(
          label: 'Categories',
          error: widget.error,
          onChanged: (_) {},
          focusNode: widget.focusNode,
          onSubmitted: widget.onSubmitted,
          labelLeft: widget.labelLeft,
          trailing: ActionChip(
            label: const Text('List', style: TextStyle(fontSize: 11)),
            onPressed: widget.enabled && widget.selected.isNotEmpty ? () => widget.onOpen(context) : null,
          ),
          initialValue: label,
          readOnly: true,
          onTap: widget.enabled && widget.selected.isNotEmpty ? () => widget.onOpen(context) : null,
          enabled: widget.enabled,
        ),
        Padding(
          padding: const EdgeInsets.only(left: 72, bottom: 2),
          child: Wrap(
            spacing: 4,
            runSpacing: -6,
            children: [
              for (final c in widget.selected)
                Chip(
                  label: Text(c, style: const TextStyle(fontSize: 10)),
                  visualDensity: const VisualDensity(horizontal: -4, vertical: -4),
                ),
            ],
          ),
        ),
      ],
    );
  }

}
