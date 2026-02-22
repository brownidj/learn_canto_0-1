import 'package:flutter/material.dart';
import '../../cubits/add_edit/add_edit_state.dart';

class CandidateList extends StatelessWidget {
  final List<CandidateItem> candidates;
  final String selected;
  final ValueChanged<String> onSelect;
  final FocusNode? focusNode;
  final bool enabled;

  const CandidateList({
    super.key,
    required this.candidates,
    required this.selected,
    required this.onSelect,
    this.focusNode,
    this.enabled = true,
  });

  @override
  Widget build(BuildContext context) {
    return Focus(
      focusNode: focusNode,
      child: Container(
        padding: const EdgeInsets.all(6),
        decoration: BoxDecoration(
          color: const Color(0xFFF6F1EA),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: const Color(0xFFD8C6B6)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Candidates', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 11)),
            const SizedBox(height: 4),
            if (candidates.isEmpty)
              const Text('No candidates yet. Use manual Hanzi.', style: TextStyle(fontSize: 11)),
            for (final item in candidates)
              ListTile(
                dense: true,
                contentPadding: EdgeInsets.zero,
                title: Row(
                  children: [
                    Text(item.hanzi, style: const TextStyle(fontSize: 18)),
                    if (item.hkBadge != null) ...[
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                        decoration: BoxDecoration(
                          color: const Color(0xFF1F6F8B),
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: Text(
                          item.hkBadge!,
                          style: const TextStyle(color: Colors.white, fontSize: 10),
                        ),
                      ),
                    ],
                    if (item.sourceTag != null) ...[
                      const SizedBox(width: 6),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                        decoration: BoxDecoration(
                          color: const Color(0xFF3B4252),
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: Text(
                          item.sourceTag!,
                          style: const TextStyle(color: Colors.white, fontSize: 10),
                        ),
                      ),
                    ],
                  ],
                ),
                subtitle: Text(item.label, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 10)),
                trailing: selected == item.hanzi ? const Icon(Icons.check) : null,
                onTap: enabled ? () => onSelect(item.hanzi) : null,
              ),
          ],
        ),
      ),
    );
  }
}
