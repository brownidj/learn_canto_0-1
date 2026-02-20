import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class FieldBlock extends StatelessWidget {
  final String label;
  final String? error;
  final ValueChanged<String> onChanged;
  final FocusNode? focusNode;
  final ValueChanged<String>? onSubmitted;
  final bool labelLeft;
  final Widget? trailing;
  final String? initialValue;
  final bool readOnly;
  final VoidCallback? onTap;
  final bool enabled;

  const FieldBlock({
    super.key,
    required this.label,
    required this.onChanged,
    this.error,
    this.focusNode,
    this.onSubmitted,
    this.labelLeft = false,
    this.trailing,
    this.initialValue,
    this.readOnly = false,
    this.onTap,
    this.enabled = true,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: labelLeft
          ? Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                SizedBox(
                  width: 72,
                  child: Text(label, style: const TextStyle(fontSize: 11)),
                ),
                Expanded(
                  child: Row(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: initialValue != null ? TextEditingController(text: initialValue) : null,
                          decoration: InputDecoration(
                            isDense: true,
                            contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                            errorText: (error != null && error!.isNotEmpty) ? error : null,
                          ),
                          style: const TextStyle(fontSize: 12),
                          focusNode: focusNode,
                          onChanged: enabled ? onChanged : null,
                          onSubmitted: onSubmitted,
                          readOnly: readOnly || !enabled,
                          enabled: enabled,
                          onTap: () {
                            SystemChannels.textInput.invokeMethod('TextInput.hide');
                            if (enabled) {
                              onTap?.call();
                            }
                          },
                          enableInteractiveSelection: true,
                          stylusHandwritingEnabled: false,
                        ),
                      ),
                      if (trailing != null) ...[
                        const SizedBox(width: 8),
                        trailing!,
                      ],
                    ],
                  ),
                ),
              ],
            )
          : Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                TextField(
                  controller: initialValue != null ? TextEditingController(text: initialValue) : null,
                  decoration: InputDecoration(
                    labelText: label,
                    labelStyle: const TextStyle(fontSize: 11),
                    contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                    errorText: (error != null && error!.isNotEmpty) ? error : null,
                  ),
                  style: const TextStyle(fontSize: 12),
                  focusNode: focusNode,
                  onChanged: enabled ? onChanged : null,
                  onSubmitted: onSubmitted,
                  readOnly: readOnly || !enabled,
                  enabled: enabled,
                  onTap: () {
                    SystemChannels.textInput.invokeMethod('TextInput.hide');
                    if (enabled) {
                      onTap?.call();
                    }
                  },
                  enableInteractiveSelection: true,
                  stylusHandwritingEnabled: false,
                ),
              ],
            ),
    );
  }
}
