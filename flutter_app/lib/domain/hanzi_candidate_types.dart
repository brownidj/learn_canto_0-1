class HanziCandidate {
  final String hanzi;
  final String source;
  final double freq;
  final List<String> glosses;

  const HanziCandidate(
    this.hanzi,
    this.source,
    this.freq, [
    List<String>? glosses,
  ]) : glosses = glosses ?? const [];

  HanziCandidate withGlosses(List<String> glossesIn) {
    final clean = glossesIn
        .whereType<String>()
        .map((g) => g.trim())
        .where((g) => g.isNotEmpty)
        .toList();
    return HanziCandidate(hanzi, source, freq, clean);
  }
}
