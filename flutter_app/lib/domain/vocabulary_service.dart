import 'exceptions.dart';
import 'jyutping_validation.dart';
import 'duplicate_rules.dart';

class VocabEntry {
  final String jyutping;
  final String hanzi;
  final List<String> meanings;
  final List<String> categories;
  final String notes;

  const VocabEntry({
    required this.jyutping,
    required this.hanzi,
    required this.meanings,
    required this.categories,
    this.notes = '',
  });

  Map<String, dynamic> toMap() {
    return {
      'jyutping': jyutping,
      'hanzi': hanzi,
      'meaning': meanings.join(', '),
      'gloss': meanings.join(', '),
      'categories': List<String>.from(categories),
      'category': categories.isNotEmpty ? categories.first : '',
      'notes': notes,
    };
  }
}

class VocabularyService {
  final Map<String, dynamic> _vocab;
  final Map<String, List<String>> _categories;
  final String Function(String) _normalizeJy;

  VocabularyService({
    required Map<String, dynamic> vocab,
    required Map<String, List<String>> categories,
    String Function(String)? normalizeJy,
  })  : _vocab = vocab,
        _categories = categories,
        _normalizeJy = normalizeJy ?? _defaultNormalize;

  static String _defaultNormalize(String jy) {
    return jy.trim().toLowerCase().split(RegExp(r'\s+')).where((p) => p.isNotEmpty).join(' ');
  }

  String validateJyutping(String jyutping) {
    final jy = jyutping.trim();
    if (jy.isEmpty) {
      throw JyutpingValidationError('', 'Jyutping is empty');
    }
    final res = validateJyutSyllables(jy);
    final ok = res[0] as bool;
    final reason = res[1] as String?;
    if (!ok) {
      throw JyutpingValidationError(jy, reason ?? 'Invalid format');
    }
    return _normalizeJy(jy);
  }

  VocabEntry validateEntry({
    required String jyutping,
    required String hanzi,
    required dynamic meanings,
    required dynamic categories,
  }) {
    final jyNorm = validateJyutping(jyutping);

    final hz = hanzi.trim();
    if (hz.isEmpty) {
      throw ValidationError('hanzi', hz, 'Hanzi is required');
    }

    List<String> mnList;
    if (meanings is String) {
      mnList = meanings.split(',').map((m) => m.trim()).where((m) => m.isNotEmpty).toList();
    } else if (meanings is List) {
      mnList = meanings.map((m) => m.toString().trim()).where((m) => m.isNotEmpty).toList();
    } else {
      mnList = [];
    }
    if (mnList.isEmpty) {
      throw ValidationError('meanings', meanings.toString(), 'At least one meaning required');
    }

    List<String> catList;
    if (categories is String) {
      catList = categories.trim().isNotEmpty ? [categories.trim()] : <String>[];
    } else if (categories is List) {
      catList = categories.map((c) => c.toString().trim()).where((c) => c.isNotEmpty).toList();
    } else {
      catList = [];
    }
    for (final cat in catList) {
      if (cat.toLowerCase() == 'all') {
        throw ValidationError('category', cat, 'Reserved category name');
      }
    }

    return VocabEntry(
      jyutping: jyNorm,
      hanzi: hz,
      meanings: mnList,
      categories: catList.isNotEmpty ? catList : ['unassigned'],
    );
  }

  bool checkDuplicateJyutping(String jyutping) {
    return isDuplicateJy(jyutping, vocab: _vocab, normalize: _normalizeJy);
  }

  bool checkExactDuplicate(String jyutping, String hanzi) {
    return isExactDuplicateEntry(_vocab, jyutping, hanzi, normalize: _normalizeJy);
  }

  List<dynamic>? getEntryRaw(String hanzi) {
    final hz = hanzi.trim();
    if (hz.isEmpty) {
      return null;
    }
    final row = _vocab[hz];
    if (row is List && row.isNotEmpty) {
      final meanings = row[0];
      final jy = row.length >= 2 ? row[1] : '';
      return [meanings, jy.toString()];
    }
    return null;
  }

  dynamic getMeaningsRaw(String hanzi) {
    final entry = getEntryRaw(hanzi);
    return entry != null ? entry[0] : null;
  }

  VocabEntry addEntry({
    required String jyutping,
    required String hanzi,
    required dynamic meanings,
    required dynamic categories,
    bool allowDuplicateJy = false,
    String notes = '',
  }) {
    final entry = validateEntry(
      jyutping: jyutping,
      hanzi: hanzi,
      meanings: meanings,
      categories: categories,
    );

    if (!allowDuplicateJy && checkDuplicateJyutping(entry.jyutping)) {
      throw DuplicateEntryError(entry.jyutping, entry.hanzi);
    }
    if (checkExactDuplicate(entry.jyutping, entry.hanzi)) {
      throw DuplicateEntryError(entry.jyutping, entry.hanzi, {'reason': 'Exact entry already exists'});
    }

    _vocab[entry.hanzi] = [entry.meanings, entry.jyutping];

    for (final cat in entry.categories) {
      _categories.putIfAbsent(cat, () => <String>[]);
      if (!_categories[cat]!.contains(entry.hanzi)) {
        _categories[cat]!.add(entry.hanzi);
      }
    }

    if (entry.categories.isNotEmpty && !(entry.categories.length == 1 && entry.categories.first == 'unassigned')) {
      final unassigned = _categories['unassigned'];
      if (unassigned != null) {
        unassigned.remove(entry.hanzi);
      }
    }

    return VocabEntry(
      jyutping: entry.jyutping,
      hanzi: entry.hanzi,
      meanings: entry.meanings,
      categories: entry.categories,
      notes: notes,
    );
  }

  VocabEntry updateEntry({
    required String originalHanzi,
    required String jyutping,
    required String hanzi,
    required dynamic meanings,
    required dynamic categories,
    String notes = '',
  }) {
    final entry = validateEntry(
      jyutping: jyutping,
      hanzi: hanzi,
      meanings: meanings,
      categories: categories,
    );

    if (originalHanzi != hanzi && _vocab.containsKey(originalHanzi)) {
      _vocab.remove(originalHanzi);
    }

    for (final cat in _categories.values) {
      cat.remove(originalHanzi);
    }

    _vocab[entry.hanzi] = [entry.meanings, entry.jyutping];

    for (final cat in entry.categories) {
      _categories.putIfAbsent(cat, () => <String>[]);
      if (!_categories[cat]!.contains(entry.hanzi)) {
        _categories[cat]!.add(entry.hanzi);
      }
    }

    return VocabEntry(
      jyutping: entry.jyutping,
      hanzi: entry.hanzi,
      meanings: entry.meanings,
      categories: entry.categories,
      notes: notes,
    );
  }
}
