import 'dart:convert';
import 'dart:io';
import 'package:flutter/services.dart';
import 'package:yaml/yaml.dart';
import 'package:csv/csv.dart';
import 'package:path_provider/path_provider.dart';

class HkWordsData {
  final Map<String, double> freqMap;
  final Set<String> colloquial;
  final Set<String> attested;

  const HkWordsData({
    required this.freqMap,
    required this.colloquial,
    required this.attested,
  });
}

class AssetDataRepository {
  Map<String, List<String>>? _cccantoCache;
  Map<String, List<String>>? _cedictCache;

  Future<List<String>> loadCategories() async {
    final local = await _loadLocalVocab();
    final text = local ?? await rootBundle.loadString('assets/data/vocab.yaml');
    final doc = loadYaml(text);
    final cats = <String>{};
    if (doc is YamlMap) {
      final block = doc['categories'];
      if (block is YamlMap) {
        for (final k in block.keys) {
          if (k != null) {
            final v = k.toString().trim();
            if (v.isNotEmpty) {
              cats.add(v);
            }
          }
        }
      }
    }
    cats.add('unassigned');
    final out = cats.toList();
    out.sort();
    return out;
  }

  Future<Map<String, List<List<dynamic>>>> loadReverseIndex() async {
    final out = <String, List<List<dynamic>>>{};
    Future<void> addFromYaml(String path, {required String defaultSource}) async {
      final text = await rootBundle.loadString(path);
      final doc = loadYaml(text);
      if (doc is! YamlMap) {
        return;
      }
      for (final entry in doc.entries) {
        final key = entry.key.toString().trim();
        if (key.isEmpty) {
          continue;
        }
        final list = <List<dynamic>>[];
        final val = entry.value;
        if (val is YamlList) {
          for (final item in val) {
            if (item is String && item.trim().isNotEmpty) {
              list.add([item.trim(), defaultSource, 1.0]);
            } else if (item is YamlMap) {
              final hz = item['hanzi']?.toString().trim() ?? '';
              if (hz.isEmpty) {
                continue;
              }
              final src = item['source']?.toString().trim().isNotEmpty == true
                  ? item['source'].toString().trim()
                  : defaultSource;
              final score = item['score'] is num ? (item['score'] as num).toDouble() : 0.0;
              list.add([hz, src, score]);
            }
          }
        }
        if (list.isNotEmpty) {
          out.putIfAbsent(key, () => <List<dynamic>>[]).addAll(list);
        }
      }
    }

    await addFromYaml('assets/data/reverse_jyut.yaml', defaultSource: 'tier1');
    await addFromYaml('assets/data/reverse_manual.yaml', defaultSource: 'reverse_manual');
    return out;
  }

  Future<HkWordsData> loadHkWords() async {
    final text = await rootBundle.loadString('assets/data/words_hk.csv');
    if (text.trim().isEmpty) {
      return const HkWordsData(freqMap: {}, colloquial: {}, attested: {});
    }
    final rows = const CsvToListConverter(eol: '\n').convert(text, shouldParseNumbers: false);
    if (rows.isEmpty) {
      return const HkWordsData(freqMap: {}, colloquial: {}, attested: {});
    }
    final header = rows.first.map((e) => e.toString()).toList();
    final data = rows.skip(1);

    String firstNonEmpty(Map<String, String> row, List<String> keys) {
      for (final k in keys) {
        final v = row[k];
        if (v != null && v.trim().isNotEmpty) {
          return v.trim();
        }
      }
      return '';
    }

    final wordKeys = ['hanzi', 'word', 'traditional', 'trad', 'text', 'form'];
    final freqKeys = ['freq', 'frequency', 'count', 'score', 'pm', 'ppm', 'pmw'];
    final rankKeys = ['rank', 'ranking'];
    final metaKeys = ['register', 'style', 'usage', 'note', 'notes', 'tag', 'tags'];

    final freqMap = <String, double>{};
    final colloq = <String>{};
    final attested = <String>{};
    final ranks = <String, double>{};

    for (final row in data) {
      final map = <String, String>{};
      for (var i = 0; i < header.length && i < row.length; i++) {
        map[header[i].toLowerCase()] = row[i]?.toString() ?? '';
      }
      var word = firstNonEmpty(map, wordKeys);
      if (word.isEmpty && row.isNotEmpty) {
        word = row.first.toString().trim();
      }
      if (word.isEmpty) {
        continue;
      }
      attested.add(word);

      final freqVal = firstNonEmpty(map, freqKeys);
      final rankVal = firstNonEmpty(map, rankKeys);
      if (freqVal.isNotEmpty) {
        final v = double.tryParse(freqVal);
        if (v != null) {
          freqMap[word] = v;
        }
      } else if (rankVal.isNotEmpty) {
        final v = double.tryParse(rankVal);
        if (v != null) {
          ranks[word] = v;
        }
      }

      final meta = metaKeys.map((k) => map[k] ?? '').join(' ').toLowerCase();
      if (meta.contains('colloquial') || meta.contains('spoken') || meta.contains('slang') || meta.contains('hk')) {
        colloq.add(word);
      }
    }

    if (ranks.isNotEmpty && freqMap.isEmpty) {
      final maxRank = ranks.values.reduce((a, b) => a > b ? a : b);
      ranks.forEach((w, r) {
        freqMap[w] = (maxRank - r) + 1.0;
      });
    }

    return HkWordsData(freqMap: freqMap, colloquial: colloq, attested: attested);
  }

  Future<Map<String, List<String>>> loadCccantoMeanings() async {
    if (_cccantoCache != null) {
      return _cccantoCache!;
    }
    final text = await rootBundle.loadString('assets/data/cccanto.txt');
    final out = <String, List<String>>{};
    final regex = RegExp(r'^([^\s]+)\s+([^\s]+)\s+\[[^]]*]\s+\{[^}]*}\s+/(.+)/\s*$');
    for (final line in const LineSplitter().convert(text)) {
      final s = line.trim();
      if (s.isEmpty || s.startsWith('#')) {
        continue;
      }
      String? hanzi;
      String? defsRaw;
      if (s.contains('\t')) {
        final parts = s.split('\t');
        if (parts.length >= 2) {
          hanzi = parts.first.trim();
          defsRaw = parts.last.trim();
        }
      } else {
        final m = regex.firstMatch(s);
        if (m != null) {
          final trad = m.group(1)!.trim();
          final simp = m.group(2)!.trim();
          defsRaw = m.group(3)!.trim();
          hanzi = trad;
          if (simp.isNotEmpty && simp != trad) {
            out[simp] = _splitDefs(defsRaw);
          }
        }
      }
      if (hanzi == null || hanzi.isEmpty || defsRaw == null || defsRaw.isEmpty) {
        continue;
      }
      out[hanzi] = _splitDefs(defsRaw);
    }
    _cccantoCache = out;
    return out;
  }

  Future<Map<String, List<String>>> loadCedictMeanings() async {
    if (_cedictCache != null) {
      return _cedictCache!;
    }
    final text = await rootBundle.loadString('assets/data/cedict_ts.u8');
    final out = <String, List<String>>{};
    final regex = RegExp(r'^([^\s]+)\s+([^\s]+)\s+\[[^]]*]\s+/(.+)/\s*$');
    for (final line in const LineSplitter().convert(text)) {
      final s = line.trim();
      if (s.isEmpty || s.startsWith('#')) {
        continue;
      }
      final m = regex.firstMatch(s);
      if (m == null) {
        continue;
      }
      final trad = m.group(1)!.trim();
      final simp = m.group(2)!.trim();
      final defsRaw = m.group(3)!.trim();
      final defs = _splitDefs(defsRaw);
      if (defs.isEmpty) {
        continue;
      }
      out[trad] = defs;
      out[simp] = defs;
    }
    _cedictCache = out;
    return out;
  }

  Future<void> persistCategories(List<String> categories) async {
    final local = await _loadLocalVocab();
    final baseText = local ?? await rootBundle.loadString('assets/data/vocab.yaml');
    final obj = _yamlToObject(loadYaml(baseText));
    final data = obj is Map<String, dynamic> ? obj : <String, dynamic>{};
    final categoriesBlock = <String, dynamic>{};
    for (final c in categories) {
      final key = c.trim();
      if (key.isNotEmpty) {
        categoriesBlock[key] = {};
      }
    }
    data['categories'] = categoriesBlock;
    data['entries'] = data['entries'] ?? {};
    final jsonText = const JsonEncoder.withIndent('  ').convert(data);
    final path = await _localVocabPath();
    if (path == null) {
      return;
    }
    final file = File(path);
    await file.writeAsString(jsonText, flush: true);
  }

  Future<Map<String, dynamic>> loadLegacyVocab() async {
    final local = await _loadLocalVocab();
    final baseText = local ?? await rootBundle.loadString('assets/data/vocab.yaml');
    final obj = _yamlToObject(loadYaml(baseText));
    final data = obj is Map<String, dynamic> ? obj : <String, dynamic>{};
    final entries = data['entries'];
    if (entries is! Map) {
      return {'vocab': <String, dynamic>{}, 'categories': <String, List<String>>{}};
    }
    final vocab = <String, dynamic>{};
    final categories = <String, List<String>>{};
    for (final e in entries.entries) {
      final jyKey = e.key.toString().trim();
      if (e.value is! Map) {
        continue;
      }
      final entry = Map<String, dynamic>.from(e.value as Map);
      final jy = (entry['jyutping'] ?? jyKey).toString().trim();
      final senses = entry['senses'];
      if (senses is! List) {
        continue;
      }
      for (final s in senses) {
        if (s is! Map) {
          continue;
        }
        final hanzi = (s['hanzi'] ?? '').toString().trim();
        final gloss = (s['gloss'] ?? '').toString().trim();
        if (hanzi.isEmpty || gloss.isEmpty) {
          continue;
        }
        final existing = vocab[hanzi];
        if (existing is List && existing.isNotEmpty) {
          final meanings = existing[0] is List ? List<String>.from(existing[0]) : <String>[];
          if (!meanings.contains(gloss)) {
            meanings.add(gloss);
          }
          vocab[hanzi] = [meanings, existing.length > 1 ? existing[1] : jy];
        } else {
          vocab[hanzi] = [
            <String>[gloss],
            jy,
          ];
        }

        final cats = s['categories'];
        if (cats is List) {
          for (final c in cats) {
            final key = c.toString().trim();
            if (key.isEmpty) {
              continue;
            }
            categories.putIfAbsent(key, () => <String>[]);
            if (!categories[key]!.contains(hanzi)) {
              categories[key]!.add(hanzi);
            }
          }
        }
      }
    }
    if (!categories.containsKey('unassigned')) {
      categories['unassigned'] = <String>[];
    }
    return {'vocab': vocab, 'categories': categories};
  }

  Future<void> persistEntry({
    required String jyutping,
    required String hanzi,
    required List<String> meanings,
    required List<String> categories,
    String? register,
    String? headword,
  }) async {
    final local = await _loadLocalVocab();
    final baseText = local ?? await rootBundle.loadString('assets/data/vocab.yaml');
    final obj = _yamlToObject(loadYaml(baseText));
    final data = obj is Map<String, dynamic> ? obj : <String, dynamic>{};
    final entries = (data['entries'] is Map) ? Map<String, dynamic>.from(data['entries']) : <String, dynamic>{};
    final categoriesBlock = (data['categories'] is Map)
        ? Map<String, dynamic>.from(data['categories'])
        : <String, dynamic>{};

    for (final c in categories) {
      final key = c.trim();
      if (key.isNotEmpty) {
        categoriesBlock[key] = {};
      }
    }

    final entryObj = (entries[jyutping] is Map)
        ? Map<String, dynamic>.from(entries[jyutping])
        : <String, dynamic>{'senses': []};
    final hw = (headword ?? hanzi).trim();
    if (hw.isNotEmpty && (entryObj['headword'] ?? '').toString().trim().isEmpty) {
      entryObj['headword'] = hw;
    }
    final senses = (entryObj['senses'] is List)
        ? List<Map<String, dynamic>>.from(entryObj['senses'])
        : <Map<String, dynamic>>[];

    bool merged = false;
    for (final s in senses) {
      if (s['hanzi'] == hanzi) {
        final existingGloss = (s['gloss'] ?? '').toString();
        if (existingGloss == meanings.join(', ')) {
          final existingCats = (s['categories'] is List)
              ? List<String>.from(s['categories'])
              : <String>[];
          final mergedCats = {...existingCats, ...categories}.toList();
          s['categories'] = mergedCats;
          final reg = (register ?? '').trim();
          if (reg.isNotEmpty && (s['register'] ?? '').toString().trim().isEmpty) {
            s['register'] = reg;
          }
          merged = true;
          break;
        }
      }
    }

    if (!merged) {
      final newSense = <String, dynamic>{
        'hanzi': hanzi,
        'gloss': meanings.join(', '),
        'categories': categories,
      };
      final reg = (register ?? '').trim();
      if (reg.isNotEmpty) {
        newSense['register'] = reg;
      }
      senses.add(newSense);
    }

    entryObj['senses'] = senses;
    entries[jyutping] = entryObj;

    data['categories'] = categoriesBlock;
    data['entries'] = entries;

    final jsonText = const JsonEncoder.withIndent('  ').convert(data);
    final path = await _localVocabPath();
    if (path == null) {
      return;
    }
    final file = File(path);
    await file.writeAsString(jsonText, flush: true);
  }

  Future<String?> _localVocabPath() async {
    try {
      final dir = await getApplicationDocumentsDirectory();
      return '${dir.path}/vocab.yaml';
    } catch (_) {
      return null;
    }
  }

  Future<String?> _loadLocalVocab() async {
    final path = await _localVocabPath();
    if (path == null) {
      return null;
    }
    try {
      final file = File(path);
      if (await file.exists()) {
        return await file.readAsString();
      }
    } catch (_) {}
    return null;
  }
}

List<String> _splitDefs(String defsRaw) {
  return defsRaw
      .replaceAll('/', ';')
      .split(';')
      .map((e) => e.trim())
      .where((e) => e.isNotEmpty)
      .toList();
}

dynamic _yamlToObject(dynamic node) {
  if (node is YamlMap) {
    final out = <String, dynamic>{};
    for (final e in node.entries) {
      final k = e.key.toString();
      out[k] = _yamlToObject(e.value);
    }
    return out;
  }
  if (node is YamlList) {
    return node.map(_yamlToObject).toList();
  }
  return node;
}
