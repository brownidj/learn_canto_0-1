import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import '../widgets/panel_shell.dart';
import '../widgets/vocab_table_panel.dart';
import '../../cubits/edit/edit_cubit.dart';
import '../../cubits/edit/edit_state.dart';
import '../../cubits/shared/vocab_row.dart';
import '../../../domain/entry_validation.dart';
import '../../../domain/vocabulary_service.dart';
import '../../../data/asset_data_repository.dart';

class EditScreen extends StatelessWidget {
  final VoidCallback? onRequestClose;

  const EditScreen({
    super.key,
    this.onRequestClose,
  });

  @override
  Widget build(BuildContext context) {
    return BlocProvider(
      create: (_) {
        final vocab = <String, dynamic>{};
        final categories = <String, List<String>>{'unassigned': []};
        final cubit = EditCubit(
          validator: EntryValidator(),
          vocabService: VocabularyService(vocab: vocab, categories: categories),
          vocabMap: vocab,
          categoriesMap: categories,
        );
        cubit.loadData(AssetDataRepository());
        return cubit;
      },
      child: _EditView(
        onRequestClose: onRequestClose,
      ),
    );
  }
}

class _EditView extends StatefulWidget {
  final VoidCallback? onRequestClose;

  const _EditView({
    this.onRequestClose,
  });

  @override
  State<_EditView> createState() => _EditViewState();
}

class _EditViewState extends State<_EditView> {

  @override
  @override
  void dispose() {
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Edit (Prototype)'),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 12),
            child: Row(
              children: [
              ],
            ),
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(10.0),
        child: BlocBuilder<EditCubit, EditState>(
          builder: (context, state) {
            final cubit = context.read<EditCubit>();
            return Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  flex: 1,
                  child: PanelShell(
                    title: 'Vocabulary',
                    child: VocabTablePanel(
                      rows: state.vocabRows,
                      searchQuery: state.searchQuery,
                      onSearchChanged: cubit.setSearchQuery,
                      onSelectRow: (row) {
                        _openEditDialog(context, cubit, row);
                      },
                    ),
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }

  Future<void> _openEditDialog(
    BuildContext context,
    EditCubit cubit,
    VocabRow row,
  ) async {
    final jyCtrl = TextEditingController(text: row.jyutping);
    final hzCtrl = TextEditingController(text: row.hanzi);
    final mnCtrl = TextEditingController(text: row.meanings.join(', '));
    final catCtrl = TextEditingController(text: row.categories.join(', '));
    final result = await showDialog<bool>(
      context: context,
      builder: (ctx) {
        return AlertDialog(
          title: const Text('Edit Entry', style: TextStyle(fontSize: 12)),
          contentPadding: const EdgeInsets.fromLTRB(12, 6, 12, 0),
          actionsPadding: const EdgeInsets.fromLTRB(12, 0, 12, 6),
          content: SizedBox(
            width: 320,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: jyCtrl,
                  decoration: const InputDecoration(labelText: 'Jyutping'),
                  style: const TextStyle(fontSize: 11),
                ),
                TextField(
                  controller: hzCtrl,
                  decoration: const InputDecoration(labelText: 'Hanzi'),
                  style: const TextStyle(fontSize: 11),
                ),
                TextField(
                  controller: mnCtrl,
                  decoration: const InputDecoration(labelText: 'Meanings (comma-separated)'),
                  style: const TextStyle(fontSize: 11),
                ),
                TextField(
                  controller: catCtrl,
                  decoration: const InputDecoration(labelText: 'Categories (comma-separated)'),
                  style: const TextStyle(fontSize: 11),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: const Text('Cancel', style: TextStyle(fontSize: 11)),
            ),
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(true),
              child: const Text('Save', style: TextStyle(fontSize: 11)),
            ),
          ],
        );
      },
    );
    if (result == true) {
      final cats = catCtrl.text
          .split(',')
          .map((e) => e.trim())
          .where((e) => e.isNotEmpty)
          .toList();
      cubit.updateEntry(
        row: row,
        hanzi: hzCtrl.text.trim(),
        jyutping: jyCtrl.text.trim(),
        meaningsText: mnCtrl.text.trim(),
        categories: cats,
      );
    }
    jyCtrl.dispose();
    hzCtrl.dispose();
    mnCtrl.dispose();
    catCtrl.dispose();
  }
}
