import 'jyutping_validation.dart';

class ValidationResult {
  final bool valid;
  final String field;
  final String value;
  final String? errorMessage;

  const ValidationResult({
    required this.valid,
    required this.field,
    required this.value,
    this.errorMessage,
  });

  factory ValidationResult.ok(String field, String value) {
    return ValidationResult(valid: true, field: field, value: value);
  }

  factory ValidationResult.error(String field, String value, String message) {
    return ValidationResult(
      valid: false,
      field: field,
      value: value,
      errorMessage: message,
    );
  }

  Map<String, dynamic> toMap() {
    return {
      'valid': valid,
      'field': field,
      'value': value,
      'error_message': errorMessage,
    };
  }
}

class EntryValidator {
  final String Function(String) _normalizeJy;
  final Set<String>? _validCategories;

  EntryValidator({String Function(String)? normalizeJy, Set<String>? validCategories})
      : _normalizeJy = normalizeJy ?? _defaultNormalize,
        _validCategories = validCategories;

  static String _defaultNormalize(String jy) {
    return jy.trim().toLowerCase().split(RegExp(r'\s+')).where((p) => p.isNotEmpty).join(' ');
  }

  ValidationResult validateJyutping(String jyutping) {
    final jy = jyutping.trim();
    if (jy.isEmpty) {
      return ValidationResult.error('jyutping', jy, 'Jyutping is required');
    }
    final res = validateJyutSyllables(jy);
    final ok = res[0] as bool;
    final reason = res[1] as String?;
    if (!ok) {
      return ValidationResult.error('jyutping', jy, reason ?? 'Invalid format');
    }
    final normalized = _normalizeJy(jy);
    return ValidationResult.ok('jyutping', normalized);
  }

  ValidationResult validateHanzi(String hanzi) {
    final hz = hanzi.trim();
    if (hz.isEmpty) {
      return ValidationResult.error('hanzi', hz, 'Hanzi is required');
    }
    return ValidationResult.ok('hanzi', hz);
  }

  ValidationResult validateMeanings(dynamic meanings) {
    List<String> mnList;
    String mnStr;
    if (meanings is String) {
      mnList = meanings.split(',').map((m) => m.trim()).where((m) => m.isNotEmpty).toList();
      mnStr = meanings.trim();
    } else if (meanings is List) {
      mnList = meanings.map((m) => m.toString().trim()).where((m) => m.isNotEmpty).toList();
      mnStr = mnList.join(', ');
    } else {
      mnList = [];
      mnStr = '';
    }
    if (mnList.isEmpty) {
      return ValidationResult.error('meanings', mnStr, 'At least one meaning required');
    }
    return ValidationResult.ok('meanings', mnStr);
  }

  ValidationResult validateCategory(String category) {
    final cat = category.trim();
    if (cat.isEmpty) {
      return ValidationResult.ok('category', '');
    }
    if (cat.toLowerCase() == 'all') {
      return ValidationResult.error('category', cat, 'Reserved category name');
    }
    if (_validCategories != null && !_validCategories!.contains(cat)) {
      return ValidationResult.error('category', cat, 'Unknown category: $cat');
    }
    return ValidationResult.ok('category', cat);
  }

  Map<String, ValidationResult> validateAll({
    required String jyutping,
    required String hanzi,
    required dynamic meanings,
    required String category,
  }) {
    return {
      'jyutping': validateJyutping(jyutping),
      'hanzi': validateHanzi(hanzi),
      'meanings': validateMeanings(meanings),
      'category': validateCategory(category),
    };
  }

  bool isValidEntry({
    required String jyutping,
    required String hanzi,
    required dynamic meanings,
    required String category,
  }) {
    final results = validateAll(
      jyutping: jyutping,
      hanzi: hanzi,
      meanings: meanings,
      category: category,
    );
    return results.values.every((r) => r.valid);
  }
}
