import 'package:flutter/material.dart';
import '../../cubits/add_edit/add_edit_state.dart';
import '../widgets/field_block.dart';
import '../widgets/category_picker.dart';

class AddEntryPanel extends StatelessWidget {
  final AddEditState state;
  final ValueChanged<String> onJyutpingChanged;
  final FocusNode jyutpingFocus;
  final ValueChanged<String>? onJyutpingSubmitted;
  final Widget? jyutpingTrailing;
  final ValueChanged<List<String>> onCategoriesChanged;
  final FocusNode categoryFocus;
  final ValueChanged<BuildContext> onOpenCategories;
  final ValueChanged<String>? onCategorySubmitted;
  final ValueChanged<String> onMeaningChanged;
  final FocusNode meaningFocus;
  final Widget? meaningTrailing;
  final ValueChanged<String>? onMeaningSubmitted;
  final bool enableAfterJyutping;

  const AddEntryPanel({
    super.key,
    required this.state,
    required this.onJyutpingChanged,
    required this.jyutpingFocus,
    required this.onJyutpingSubmitted,
    required this.jyutpingTrailing,
    required this.onCategoriesChanged,
    required this.categoryFocus,
    required this.onOpenCategories,
    required this.onCategorySubmitted,
    required this.onMeaningChanged,
    required this.meaningFocus,
    required this.meaningTrailing,
    this.onMeaningSubmitted,
    this.enableAfterJyutping = true,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        FieldBlock(
          label: 'Jyutping',
          error: state.errors['jyutping'],
          onChanged: onJyutpingChanged,
          focusNode: jyutpingFocus,
          onSubmitted: onJyutpingSubmitted,
          labelLeft: true,
          trailing: jyutpingTrailing,
          keyboardType: TextInputType.none,
        ),
        if (state.duplicateWarning != null)
          Padding(
            padding: const EdgeInsets.only(bottom: 2),
            child: Text(
              state.duplicateWarning!,
              style: const TextStyle(color: Colors.red, fontSize: 12),
            ),
          ),
        CategoryPicker(
          selected: state.categories,
          onChanged: onCategoriesChanged,
          error: state.errors['category'],
          allCategories: state.availableCategories,
          focusNode: categoryFocus,
          onOpen: onOpenCategories,
          onSubmitted: onCategorySubmitted,
          labelLeft: true,
          enabled: enableAfterJyutping,
        ),
        FieldBlock(
          label: 'Meaning',
          error: state.errors['meanings'],
          onChanged: onMeaningChanged,
          focusNode: meaningFocus,
          onSubmitted: onMeaningSubmitted,
          labelLeft: true,
          trailing: meaningTrailing,
          enabled: enableAfterJyutping,
        ),
        FieldBlock(
          label: 'Notes',
          error: null,
          onChanged: (_) {},
          focusNode: null,
          labelLeft: true,
          initialValue: state.notes,
          readOnly: true,
          enabled: false,
          bottomPadding: 1,
        ),
      ],
    );
  }
}
