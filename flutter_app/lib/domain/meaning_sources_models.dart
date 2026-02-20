import 'meaning_sources_cleaning.dart';
import 'category_rules.dart';

class SelectedCandidate {
  final String hanzi;
  final String source;
  final List<String> meanings;
  final String label;

  const SelectedCandidate({
    required this.hanzi,
    required this.source,
    required this.meanings,
    required this.label,
  });
}

typedef GlossesFor = List<String> Function(String);

class MeaningResolver {
  final GlossesFor? ccGlossesFor;
  final GlossesFor? cedictMeaningsFor;

  const MeaningResolver({this.ccGlossesFor, this.cedictMeaningsFor});

  List<String> cleanGlosses(dynamic glosses) {
    return cleanGlossesForDisplay(glosses);
  }

  List<String> glossesFor(String hanzi, {int limit = 6}) {
    final hz = hanzi.trim();
    if (hz.isEmpty) {
      return [];
    }
    final lim = limit < 1 ? 1 : limit;

    if (ccGlossesFor != null) {
      try {
        final cc = cleanGlosses(ccGlossesFor!(hz));
        if (cc.isNotEmpty) {
          return cc.take(lim).toList();
        }
      } catch (_) {}
    }

    if (cedictMeaningsFor != null) {
      try {
        final ce = cleanGlosses(cedictMeaningsFor!(hz));
        if (ce.isNotEmpty) {
          return ce.take(lim).toList();
        }
      } catch (_) {}
    }
    return [];
  }

  List<String> meaningsFor(String hanzi, {int limit = 3}) {
    return glossesFor(hanzi, limit: limit);
  }
}

class MeaningFacade {
  final MeaningResolver? _resolver;
  final List<String> Function(List<String>)? _cleaner;

  const MeaningFacade({MeaningResolver? resolver, List<String> Function(List<String>)? cleaner})
      : _resolver = resolver,
        _cleaner = cleaner;

  List<String> meaningsFor(String hanzi) {
    final hz = hanzi.trim();
    if (hz.isEmpty || _resolver == null) {
      return [];
    }
    try {
      final out = _resolver!.meaningsFor(hz);
      return out.where((x) => x.trim().isNotEmpty).toList();
    } catch (_) {
      return [];
    }
  }

  List<String> meaningsForDisplay(String hanzi) {
    final items = meaningsFor(hanzi);
    if (items.isEmpty) {
      return [];
    }
    if (_cleaner != null) {
      try {
        final cleaned = _cleaner!(items);
        return cleaned.where((x) => x.trim().isNotEmpty).toList();
      } catch (_) {}
    }
    return items;
  }

  List<String> previewForDisplay(String hanzi, {int maxItems = 2}) {
    final items = meaningsForDisplay(hanzi);
    if (items.isEmpty) {
      return [];
    }
    var n = maxItems;
    if (n <= 0) {
      n = 2;
    }
    return items.take(n).toList();
  }

  String candidateLabel(
    String hanzi,
    String source, {
    bool preferred = false,
    int maxItems = 2,
  }) {
    final hz = hanzi.trim();
    if (hz.isEmpty) {
      return '';
    }
    var n = maxItems;
    if (n <= 0) {
      n = 2;
    }
    List<String> glosses;
    try {
      glosses = meaningsForDisplay(hz);
    } catch (_) {
      glosses = [];
    }
    final plain = glosses
        .where((g) => g.trim().isNotEmpty && !g.contains('[') && !g.contains('('))
        .toList();
    final shown = (plain.isNotEmpty ? plain : glosses).take(n).toList();
    final tag = abbrForSource(source);
    final core = shown.isNotEmpty ? '$hz — ${shown.join(', ')} ($tag)' : '$hz ($tag)';
    return preferred ? '✓ $core' : core;
  }

  SelectedCandidate selectCandidate(
    String hanzi,
    String source, {
    bool preferred = false,
    int maxItems = 2,
  }) {
    final hz = hanzi.trim();
    final src = source.trim();
    List<String> meanings;
    try {
      meanings = meaningsForDisplay(hz);
    } catch (_) {
      meanings = [];
    }
    final label = candidateLabel(hz, src, preferred: preferred, maxItems: maxItems);
    return SelectedCandidate(hanzi: hz, source: src, meanings: meanings, label: label);
  }
}
