import 'add_edit_state.dart';

class AddEditPayloadMapper {
  const AddEditPayloadMapper();

  Map<String, dynamic> toPreviewPayload(AddEditState state) {
    return {
      'jyutping': state.jyutping.trim(),
      'hanzi': state.hanzi.trim(),
      'meanings': state.meaningText
          .split(',')
          .map((e) => e.trim())
          .where((e) => e.isNotEmpty)
          .toList(),
      'categories': List<String>.from(state.categories),
      'register': state.register.trim(),
      'notes': state.notes,
    };
  }

  // Entry row mapping is handled by Edit flow for now.
}
