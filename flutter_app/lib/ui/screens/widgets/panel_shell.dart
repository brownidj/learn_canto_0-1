import 'package:flutter/material.dart';

class PanelShell extends StatelessWidget {
  final String? title;
  final Widget child;
  final bool expandChild;
  final bool scrollable;

  const PanelShell({
    super.key,
    this.title,
    required this.child,
    this.expandChild = true,
    this.scrollable = true,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: const Color(0xFFF8EDE1),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFB7DAD0)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (title != null) ...[
            Text(title!, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12)),
            const SizedBox(height: 2),
          ],
          if (expandChild)
            Expanded(
              child: scrollable
                  ? SingleChildScrollView(
                      child: child,
                    )
                  : child,
            )
          else if (scrollable)
            SingleChildScrollView(
              child: child,
            )
          else
            child,
        ],
      ),
    );
  }
}
