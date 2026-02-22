import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_app/ui/screens/dialogs/missing_jyutping_dialog.dart';
import 'package:flutter_app/ui/screens/dialogs/manual_entry_dialog.dart';
import 'package:flutter_app/ui/cubits/add_edit/add_edit_cubit.dart';
import 'package:flutter_app/ui/cubits/add_edit/add_edit_state.dart';

class AddFocusPolicy {
  String _lastJy = '';
  String? _lastToast;
  bool _categoryDialogOpen = false;

  bool get categoryDialogOpen => _categoryDialogOpen;

  void setCategoryDialogOpen(bool value) {
    _categoryDialogOpen = value;
  }

  void applyFocusPolicy(
    AddEditState state, {
    required FocusNode jyutpingFocus,
    required FocusNode categoryFocus,
    required void Function() onToastFocus,
  }) {
    if (state.toastMessage != null && state.toastMessage != _lastToast) {
      _lastToast = state.toastMessage;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        onToastFocus();
      });
      return;
    }

    final jy = state.jyutping.trim();
    final jyOk = jy.isNotEmpty && !state.errors.containsKey('jyutping');
    if (jyOk && _lastJy != jy) {
      _lastJy = jy;
      if (state.manualHanzi) {
        return;
      }
    }
  }

  void handleCategoryApplied(
    BuildContext context,
    AddEditCubit cubit, {
    required FocusNode hanziFocus,
    required FocusNode meaningFocus,
    required FocusNode candidateFocus,
  }) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final items = cubit.state.candidateItems;
      debugPrint(
        '[AddEditScreen] category applied: jy="${cubit.state.jyutping.trim()}" '
        'cats=${cubit.state.categories.length} candidates=${items.length}',
      );
      if (items.isEmpty) {
        showMissingJyutpingDialog(context, cubit.state.jyutping.trim()).then((choice) async {
          if (choice == MissingJyutpingChoice.manual) {
            cubit.setManualHanzi(true);
            final draft = await showManualEntryDialog(
              context,
              state: cubit.state,
              onAddCategory: cubit.addCategory,
            );
            if (draft == null) {
              return;
            }
            cubit.setJyutping(draft.jyutping);
            cubit.setHanzi(draft.hanzi);
            cubit.setMeaning(draft.gloss);
            cubit.setCategories(draft.categories);
            cubit.setRegister(draft.register);
            debugPrint('[AddEditScreen] manual entry applied -> focus meaning');
            FocusScope.of(context).requestFocus(meaningFocus);
          } else if (choice == MissingJyutpingChoice.chatgpt) {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('ChatGPT lookup not wired yet.')),
            );
            debugPrint('[AddEditScreen] ChatGPT flow not wired -> focus hanzi');
            FocusScope.of(context).requestFocus(hanziFocus);
          }
        });
        return;
      }
      if (items.length == 1) {
        cubit.selectCandidate(items.first.hanzi);
        debugPrint('[AddEditScreen] single candidate -> focus meaning');
        FocusScope.of(context).requestFocus(meaningFocus);
        return;
      }
      if (!cubit.state.manualHanzi) {
        debugPrint('[AddEditScreen] multiple candidates -> focus candidates');
        FocusScope.of(context).requestFocus(candidateFocus);
      }
    });
  }
}
