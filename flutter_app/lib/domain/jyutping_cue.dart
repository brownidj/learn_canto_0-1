final RegExp _syllableRe = RegExp(r'^([a-z]+)([1-6])$', caseSensitive: false);

const List<String> _initials = [
  'gw',
  'kw',
  'ng',
  'b',
  'p',
  'm',
  'f',
  'd',
  't',
  'n',
  'l',
  'g',
  'k',
  'h',
  'w',
  'z',
  'c',
  's',
  'j',
];

const Map<String, String> _initialMap = {
  'b': 'B',
  'p': 'P',
  'm': 'M',
  'f': 'F',
  'd': 'D',
  't': 'T',
  'n': 'N',
  'l': 'L',
  'g': 'G',
  'k': 'K',
  'ng': 'NG',
  'h': 'H',
  'gw': 'GW',
  'kw': 'KW',
  'w': 'W',
  'z': 'DZ',
  'c': 'TS',
  's': 'S',
  'j': 'Y',
  '': '',
};

const Map<String, String> _toneSuperscript = {
  '1': '¹',
  '2': '²',
  '3': '³',
  '4': '⁴',
  '5': '⁵',
  '6': '⁶',
};

const Map<String, String> _baseFinalMap = {
  'aa': 'AH',
  'a': 'UH',
  'i': 'EE',
  'u': 'OO',
  'e': 'EH',
  'o': 'AW',
  'ai': 'EYE',
  'au': 'OW',
  'ei': 'AY',
  'ou': 'OH',
  'oi': 'OY',
  'ui': 'OOEY',
  'eoi': 'OEY',
  'oe': 'OE',
  'eo': 'OE',
  'iu': 'EEU',
  'yu': 'YOO',
  'aai': 'AHY',
};

const Map<String, String> _codaMap = {
  'm': 'M',
  'n': 'N',
  'ng': 'NG',
  'p': 'P',
  't': 'T',
  'k': 'K',
};

const Map<String, String> _finalHints = {
  'aa': 'AH like “spa”',
  'a': 'UH like “uh”',
  'i': 'EE like “see”',
  'u': 'OO like “too”',
  'e': 'EH like “bed”',
  'o': 'AW like “law”',
  'ai': 'EYE like “eye”',
  'au': 'OW like “cow”',
  'ei': 'AY like “say”',
  'ou': 'OH like “go”',
  'oi': 'OY like “boy”',
  'ui': 'OO-EE glide',
  'eoi': 'rounded “uh/er”',
  'oe': 'rounded “uh/er”',
  'eo': 'rounded “uh/er”',
  'iu': 'EE-OO glide',
  'yu': 'front “oo” (like “you”)',
};

({String initial, String finalPart, String tone}) _splitSyllable(String syl) {
  final m = _syllableRe.firstMatch(syl.trim().toLowerCase());
  if (m == null) {
    return (initial: '', finalPart: syl, tone: '');
  }
  final base = m.group(1) ?? '';
  final tone = m.group(2) ?? '';
  var initial = '';
  var rest = base;
  for (final ini in _initials) {
    if (base.startsWith(ini)) {
      initial = ini;
      rest = base.substring(ini.length);
      break;
    }
  }
  return (initial: initial, finalPart: rest, tone: tone);
}

String? _cueFinal(String finalPart) {
  if (_baseFinalMap.containsKey(finalPart)) {
    return _baseFinalMap[finalPart];
  }
  for (final coda in ['ng', 'm', 'n', 'p', 't', 'k']) {
    if (finalPart.endsWith(coda) && finalPart != coda) {
      final base = finalPart.substring(0, finalPart.length - coda.length);
      final baseCue = _baseFinalMap[base];
      if (baseCue == null) {
        return null;
      }
      return '$baseCue${_codaMap[coda]}';
    }
  }
  if (finalPart.isEmpty) {
    return '';
  }
  return null;
}

String cueForSyllable(String syl) {
  final parts = _splitSyllable(syl);
  final toneMark = _toneSuperscript[parts.tone] ?? parts.tone;
  final finalCue = _cueFinal(parts.finalPart);
  final initCue = _initialMap[parts.initial] ?? parts.initial.toUpperCase();
  if (finalCue == null) {
    return '${(parts.initial + parts.finalPart).toUpperCase()}$toneMark';
  }
  return '$initCue$finalCue$toneMark';
}

String hintForSyllable(String syl) {
  final parts = _splitSyllable(syl);
  final finalPart = parts.finalPart;
  if (finalPart.isEmpty) {
    return '';
  }
  for (final coda in ['ng', 'm', 'n', 'p', 't', 'k']) {
    if (finalPart.endsWith(coda) && finalPart != coda) {
      final base = finalPart.substring(0, finalPart.length - coda.length);
      final baseHint = _finalHints[base];
      if (baseHint != null) {
        if (coda == 'p' || coda == 't' || coda == 'k') {
          return '$baseHint, checked -$coda';
        }
        return '$baseHint, ending -$coda';
      }
    }
  }
  return _finalHints[finalPart] ?? '';
}
