import 'package:flutter/material.dart';
import '../../cubits/shared/vocab_row.dart';

class VocabTablePanel extends StatelessWidget {
  final List<VocabRow> rows;
  final String searchQuery;
  final ValueChanged<String> onSearchChanged;
  final ValueChanged<VocabRow> onSelectRow;

  const VocabTablePanel({
    super.key,
    required this.rows,
    required this.searchQuery,
    required this.onSearchChanged,
    required this.onSelectRow,
  });

  @override
  Widget build(BuildContext context) {
    final query = searchQuery.trim().toLowerCase();
    final filtered = query.isEmpty ? rows : rows.where((row) {
      final hay = [
        row.hanzi,
        row.jyutping,
        row.meanings.join(' '),
        row.categories.join(' '),
      ].join(' ').toLowerCase();
      return hay.contains(query);
    }).toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        TextField(
          decoration: const InputDecoration(
            isDense: true,
            contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 6),
            labelText: 'Search (Hanzi / Jyutping / meaning)',
          ),
          style: const TextStyle(fontSize: 12),
          onChanged: onSearchChanged,
        ),
        const SizedBox(height: 8),
        if (filtered.isEmpty)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 12),
            child: Center(child: Text('No matches')),
          )
        else
          ListView.separated(
            itemCount: filtered.length,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            separatorBuilder: (_, __) => const Divider(height: 1),
            itemBuilder: (context, index) {
              final row = filtered[index];
              final cats = row.categories.isEmpty ? '' : row.categories.join(', ');
              final meanings = row.meanings.isEmpty ? '' : row.meanings.join(', ');
              return ListTile(
                dense: true,
                contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                title: Row(
                  children: [
                    Text(row.hanzi, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
                    const SizedBox(width: 8),
                    Text(row.jyutping, style: const TextStyle(fontSize: 12, color: Colors.black54)),
                  ],
                ),
                subtitle: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (meanings.isNotEmpty) Text(meanings, style: const TextStyle(fontSize: 11)),
                    if (cats.isNotEmpty) Text('Categories: $cats', style: const TextStyle(fontSize: 10)),
                  ],
                ),
                onTap: () => onSelectRow(row),
              );
            },
          ),
      ],
    );
  }
}
