import 'package:flutter/material.dart';

class MeaningPreview extends StatelessWidget {
  final String hanzi;
  final List<String> meanings;
  final String sourceTag;
  final List<String> fullMeanings;

  const MeaningPreview({
    super.key,
    required this.hanzi,
    required this.meanings,
    required this.sourceTag,
    required this.fullMeanings,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(6),
      decoration: BoxDecoration(
        color: const Color(0xFFEAF2F7),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFB9CBE0)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Text('Meaning Preview', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 11)),
              if (sourceTag.isNotEmpty) ...[
                const SizedBox(width: 6),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(
                    color: const Color(0xFF315A8F),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    sourceTag,
                    style: const TextStyle(color: Colors.white, fontSize: 10),
                  ),
                ),
              ],
            ],
          ),
          const SizedBox(height: 4),
          if (meanings.isEmpty)
            const Text('Select a candidate to preview meanings.', style: TextStyle(fontSize: 10))
          else
            for (final m in meanings)
              Text('- $m', style: const TextStyle(fontSize: 10)),
          if (fullMeanings.length > meanings.length)
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton(
                onPressed: () => _showMore(context),
                child: const Text('Show more', style: TextStyle(fontSize: 10)),
              ),
            ),
        ],
      ),
    );
  }

  void _showMore(BuildContext context) {
    showModalBottomSheet(
      context: context,
      builder: (ctx) {
        return Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Hanzi: $hanzi'),
              if (sourceTag.isNotEmpty) Text('Source: $sourceTag'),
              const SizedBox(height: 8),
              Expanded(
                child: ListView(
                  children: [
                    for (final m in fullMeanings) Text('- $m'),
                  ],
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
