import '../shared/vocab_row.dart';

class AddEditVocabService {
  final Map<String, dynamic> vocabMap;
  final Map<String, List<String>> categoriesMap;

  const AddEditVocabService({
    required this.vocabMap,
    required this.categoriesMap,
  });

  List<VocabRow> buildRows() {
    final hanziToCats = <String, List<String>>{};
    categoriesMap.forEach((cat, list) {
      for (final hz in list) {
        final key = hz.trim();
        if (key.isEmpty) {
          continue;
        }
        hanziToCats.putIfAbsent(key, () => <String>[]).add(cat);
      }
    });

    final rows = <VocabRow>[];
    vocabMap.forEach((key, value) {
      final hanzi = key.toString().trim();
      if (hanzi.isEmpty) {
        return;
      }
      var jy = '';
      List<String> meanings = <String>[];
      if (value is List && value.isNotEmpty) {
        final m = value[0];
        meanings = _extractMeanings(m);
        if (value.length > 1) {
          jy = value[1].toString().trim();
        }
      }
      final cats = hanziToCats[hanzi] ?? <String>[];
      rows.add(
        VocabRow(
          hanzi: hanzi,
          jyutping: jy,
          meanings: meanings,
          categories: List<String>.from(cats),
        ),
      );
    });

    rows.sort((a, b) => a.hanzi.compareTo(b.hanzi));
    return rows;
  }

  List<String> _extractMeanings(dynamic raw) {
    if (raw is List) {
      final flat = <String>[];
      for (final item in raw) {
        if (item is List) {
          for (final sub in item) {
            final s = sub.toString().trim();
            if (s.isNotEmpty) {
              flat.add(s);
            }
          }
        } else {
          final s = item.toString().trim();
          if (s.isNotEmpty) {
            flat.add(s);
          }
        }
      }
      return flat;
    }
    if (raw is String) {
      return raw.split(',').map((e) => e.trim()).where((e) => e.isNotEmpty).toList();
    }
    return <String>[];
  }
}
