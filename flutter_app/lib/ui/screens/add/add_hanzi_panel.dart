import 'package:flutter/material.dart';
import '../../cubits/add_edit/add_edit_state.dart';
import '../widgets/field_block.dart';
import '../widgets/candidate_list.dart';
import '../widgets/meaning_preview.dart';

class AddHanziPanel extends StatelessWidget {
  final AddEditState state;
  final ValueChanged<String> onHanziChanged;
  final FocusNode hanziFocus;
  final ValueChanged<String>? onHanziSubmitted;
  final ValueChanged<String> onCandidateSelected;
  final FocusNode candidateFocus;
  final bool enableAfterJyutping;

  const AddHanziPanel({
    super.key,
    required this.state,
    required this.onHanziChanged,
    required this.hanziFocus,
    required this.onHanziSubmitted,
    required this.onCandidateSelected,
    required this.candidateFocus,
    this.enableAfterJyutping = true,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        FieldBlock(
          label: 'Hanzi',
          error: state.errors['hanzi'],
          onChanged: onHanziChanged,
          focusNode: hanziFocus,
          onSubmitted: onHanziSubmitted,
          enabled: enableAfterJyutping,
        ),
        CandidateList(
          candidates: state.candidateItems,
          selected: state.selectedHanzi,
          onSelect: onCandidateSelected,
          focusNode: candidateFocus,
          enabled: enableAfterJyutping,
        ),
        const SizedBox(height: 12),
        MeaningPreview(
          hanzi: state.selectedHanzi,
          meanings: state.meaningsPreview,
          sourceTag: state.meaningSourceTag,
          fullMeanings: state.meaningsFull,
        ),
      ],
    );
  }
}
