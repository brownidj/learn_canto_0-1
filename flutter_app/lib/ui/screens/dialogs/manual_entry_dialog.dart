import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../cubits/add_edit/add_edit_state.dart';

class ManualEntryDraft {
  final String jyutping;
  final String hanzi;
  final String gloss;
  final List<String> categories;
  final String register;

  const ManualEntryDraft({
    required this.jyutping,
    required this.hanzi,
    required this.gloss,
    required this.categories,
    required this.register,
  });
}

Future<ManualEntryDraft?> showManualEntryDialog(
  BuildContext context, {
  required AddEditState state,
  required ValueChanged<String> onAddCategory,
}) {
  final jyutController = TextEditingController(text: state.jyutping.trim());
  final hanziController = TextEditingController(text: state.hanzi.trim());
  final glossController = TextEditingController(text: state.meaningText.trim());
  final next = Set<String>.from(state.categories);
  String register = state.register.trim();
  final focusHanzi = FocusNode();
  final focusGloss = FocusNode();
  const registerOptions = <String>['colloquial', 'literary', 'both'];

  String yamlPreview() {
    final jy = jyutController.text.trim();
    final hz = hanziController.text.trim();
    final gl = glossController.text.trim();
    final cats = next.toList();
    final reg = register.trim();
    final catLines = cats.isEmpty ? '      - ' : cats.map((c) => '      - $c').join('\n');
    final regLine = reg.isEmpty ? '      register: ' : '      register: $reg';
    return '  $jy:\n'
        '    headword: $hz\n'
        '    senses:\n'
        '    - categories:\n'
        '$catLines\n'
        '      gloss: $gl\n'
        '      hanzi: $hz\n'
        '$regLine';
  }

  return showDialog<ManualEntryDraft>(
    context: context,
    builder: (ctx) {
      return StatefulBuilder(
        builder: (ctx2, setState) {
          final filtered = List<String>.from(state.availableCategories)..sort();
          final canApply = jyutController.text.trim().isNotEmpty &&
              hanziController.text.trim().isNotEmpty &&
              glossController.text.trim().isNotEmpty &&
              next.isNotEmpty &&
              register.trim().isNotEmpty;
          return AlertDialog(
            title: const Text('Manual entry', style: TextStyle(fontSize: 12)),
            contentPadding: const EdgeInsets.fromLTRB(12, 6, 12, 0),
            actionsPadding: const EdgeInsets.fromLTRB(12, 0, 12, 6),
            insetPadding: const EdgeInsets.all(12),
            content: SizedBox(
              width: 300,
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    TextField(
                      controller: jyutController,
                      decoration: const InputDecoration(labelText: 'Jyutping'),
                      style: const TextStyle(fontSize: 11),
                      textInputAction: TextInputAction.next,
                      onSubmitted: (_) => focusHanzi.requestFocus(),
                      onChanged: (_) => setState(() {}),
                      onTap: () => SystemChannels.textInput.invokeMethod('TextInput.hide'),
                      enableInteractiveSelection: true,
                      stylusHandwritingEnabled: false,
                    ),
                    const SizedBox(height: 6),
                    TextField(
                      controller: hanziController,
                      focusNode: focusHanzi,
                      decoration: const InputDecoration(labelText: 'Hanzi'),
                      style: const TextStyle(fontSize: 12),
                      textInputAction: TextInputAction.next,
                      onSubmitted: (_) => focusGloss.requestFocus(),
                      onChanged: (_) => setState(() {}),
                      onTap: () => SystemChannels.textInput.invokeMethod('TextInput.hide'),
                      enableInteractiveSelection: true,
                      stylusHandwritingEnabled: false,
                    ),
                    const SizedBox(height: 6),
                    TextField(
                      controller: glossController,
                      focusNode: focusGloss,
                      decoration: const InputDecoration(labelText: 'Gloss (colloquial)'),
                      style: const TextStyle(fontSize: 12),
                      textInputAction: TextInputAction.done,
                      onChanged: (_) => setState(() {}),
                      onTap: () => SystemChannels.textInput.invokeMethod('TextInput.hide'),
                      enableInteractiveSelection: true,
                      stylusHandwritingEnabled: false,
                    ),
                    const SizedBox(height: 6),
                    DropdownButtonFormField<String>(
                      value: register.isEmpty ? null : register,
                      decoration: const InputDecoration(labelText: 'Register'),
                      style: const TextStyle(fontSize: 11, color: Colors.black87),
                      items: registerOptions
                          .map((opt) => DropdownMenuItem(
                                value: opt,
                                child: Text(opt, style: const TextStyle(fontSize: 11)),
                              ))
                          .toList(),
                      onChanged: (val) {
                        setState(() {
                          register = val ?? '';
                        });
                      },
                    ),
                    const SizedBox(height: 6),
                    TextField(
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
                    SizedBox(
                      height: 140,
                      child: Scrollbar(
                        thumbVisibility: true,
                        child: ListView(
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
                    const SizedBox(height: 6),
                    const Text('Preview', style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold)),
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(6),
                      decoration: BoxDecoration(
                        color: const Color(0xFFF7F3EF),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: const Color(0xFFD8C6B6)),
                      ),
                      child: Text(
                        yamlPreview(),
                        style: const TextStyle(fontSize: 10),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(ctx2).pop(null),
                child: const Text('Cancel', style: TextStyle(fontSize: 11)),
              ),
              TextButton(
                onPressed: canApply
                    ? () {
                        final jy = jyutController.text.trim();
                        final hz = hanziController.text.trim();
                        final gl = glossController.text.trim();
                        final cats = next.toList();
                        for (final v in cats) {
                          if (!state.availableCategories.contains(v)) {
                            onAddCategory(v);
                          }
                        }
                        Navigator.of(ctx2).pop(
                          ManualEntryDraft(
                            jyutping: jy,
                            hanzi: hz,
                            gloss: gl,
                            categories: cats,
                            register: register.trim(),
                          ),
                        );
                      }
                    : null,
                child: const Text('Apply', style: TextStyle(fontSize: 11)),
              ),
            ],
          );
        },
      );
    },
  ).whenComplete(() {
    focusHanzi.dispose();
    focusGloss.dispose();
    jyutController.dispose();
    hanziController.dispose();
    glossController.dispose();
  });
}
