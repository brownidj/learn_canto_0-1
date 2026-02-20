import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'add_entry_panel.dart';
import 'add_hanzi_panel.dart';
import 'add_focus_policy.dart';
import '../dialogs/category_dialog.dart';
import '../dialogs/save_confirm_dialog.dart';
import '../widgets/panel_shell.dart';
import '../../cubits/add_edit/add_edit_cubit.dart';
import '../../cubits/add_edit/add_edit_state.dart';
import '../../../domain/entry_validation.dart';
import '../../../domain/vocabulary_service.dart';
import '../../../data/asset_data_repository.dart';

class AddScreen extends StatelessWidget {
  const AddScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return BlocProvider(
      create: (_) {
        final vocab = <String, dynamic>{};
        final categories = <String, List<String>>{'unassigned': []};
        final cubit = AddEditCubit(
          validator: EntryValidator(),
          vocabService: VocabularyService(vocab: vocab, categories: categories),
          vocabMap: vocab,
          categoriesMap: categories,
        );
        cubit.loadData(AssetDataRepository());
        return cubit;
      },
      child: const _AddView(),
    );
  }
}

class _AddView extends StatefulWidget {
  const _AddView();

  @override
  State<_AddView> createState() => _AddViewState();
}

class _AddViewState extends State<_AddView> {
  final FocusNode _jyFocus = FocusNode();
  final FocusNode _meaningFocus = FocusNode();
  final FocusNode _hanziFocus = FocusNode();
  final FocusNode _categoryFocus = FocusNode();
  final FocusNode _candidateFocus = FocusNode();
  final AddFocusPolicy _focusPolicy = AddFocusPolicy();

  @override
  void initState() {
    super.initState();
    _attachHideIme(_jyFocus);
    _attachHideIme(_meaningFocus);
    _attachHideIme(_hanziFocus);
    _attachHideIme(_categoryFocus);
  }

  void _attachHideIme(FocusNode node) {
    node.addListener(() {
      if (node.hasFocus) {
        SystemChannels.textInput.invokeMethod('TextInput.hide');
      }
    });
  }

  @override
  void dispose() {
    _jyFocus.dispose();
    _meaningFocus.dispose();
    _hanziFocus.dispose();
    _categoryFocus.dispose();
    _candidateFocus.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Add (Prototype)'),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 12),
            child: ActionChip(
              label: const Text('Close', style: TextStyle(fontSize: 11)),
              onPressed: () => Navigator.of(context).maybePop(),
            ),
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(10.0),
        child: BlocBuilder<AddEditCubit, AddEditState>(
          builder: (context, state) {
            final isLandscape = MediaQuery.of(context).orientation == Orientation.landscape;
            final cubit = context.read<AddEditCubit>();
            if (state.toastMessage != null) {
              WidgetsBinding.instance.addPostFrameCallback((_) {
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text(state.toastMessage!)),
                );
                cubit.clearToast();
              });
            }
            _focusPolicy.applyFocusPolicy(
              state,
              jyutpingFocus: _jyFocus,
              categoryFocus: _categoryFocus,
              onToastFocus: () => _jyFocus.requestFocus(),
            );
            final enableAfterJyutping = state.jyutping.trim().isNotEmpty;
            if (!isLandscape) {
              return const Center(
                child: Text('Rotate to landscape to edit entries.'),
              );
            }
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        flex: 3,
                        child: PanelShell(
                          title: 'Entry',
                          child: AddEntryPanel(
                            state: state,
                            onJyutpingChanged: cubit.setJyutping,
                            jyutpingFocus: _jyFocus,
                            onJyutpingSubmitted: (_) => _openCategoryDialog(context),
                            jyutpingTrailing: ActionChip(
                              label: const Text('Apply', style: TextStyle(fontSize: 11)),
                              onPressed: state.jyutping.trim().isNotEmpty
                                  ? () => _openCategoryDialog(context)
                                  : null,
                            ),
                            onCategoriesChanged: cubit.setCategories,
                            onAddCategory: cubit.addCategory,
                            categoryFocus: _categoryFocus,
                            onOpenCategories: (ctx) => _openCategoryDialog(ctx),
                            onCategorySubmitted: (_) => _openCategoryDialog(context),
                            onMeaningChanged: cubit.setMeaning,
                            meaningFocus: _meaningFocus,
                            meaningTrailing: ActionChip(
                              label: const Text('Save', style: TextStyle(fontSize: 11)),
                              onPressed: state.saveEnabled
                                  ? () async {
                                      final ok = await showSaveConfirm(
                                        context,
                                        cubit.previewPayload(),
                                      );
                                      if (ok == true) {
                                        cubit.save();
                                      }
                                    }
                                  : null,
                            ),
                            enableAfterJyutping: enableAfterJyutping,
                          ),
                        ),
                      ),
                      const SizedBox(width: 16),
                      Expanded(
                        flex: 2,
                        child: PanelShell(
                          title: 'Hanzi',
                          child: AddHanziPanel(
                            state: state,
                            onHanziChanged: cubit.setHanzi,
                            hanziFocus: _hanziFocus,
                            onHanziSubmitted: (_) => _meaningFocus.requestFocus(),
                            onCandidateSelected: (hz) {
                              cubit.selectCandidate(hz);
                              _hanziFocus.requestFocus();
                            },
                            candidateFocus: _candidateFocus,
                            enableAfterJyutping: enableAfterJyutping,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 8),
                const SizedBox.shrink(),
              ],
            );
          },
        ),
      ),
    );
  }

  void _openCategoryDialog(BuildContext context) {
    if (_focusPolicy.categoryDialogOpen) {
      return;
    }
    _focusPolicy.setCategoryDialogOpen(true);
    final cubit = context.read<AddEditCubit>();
    showCategoryDialog(
      context,
      state: cubit.state,
      onChanged: cubit.setCategories,
      onAddCategory: cubit.addCategory,
      onApplied: () => _focusPolicy.handleCategoryApplied(
        context,
        cubit,
        hanziFocus: _hanziFocus,
        meaningFocus: _meaningFocus,
        candidateFocus: _candidateFocus,
      ),
    ).whenComplete(() {
      _focusPolicy.setCategoryDialogOpen(false);
    });
  }
}
