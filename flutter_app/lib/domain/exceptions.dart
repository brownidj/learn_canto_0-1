class VocabularyError implements Exception {
  final String message;
  final Map<String, dynamic> context;

  VocabularyError(this.message, [Map<String, dynamic>? context])
      : context = context ?? {};

  @override
  String toString() => message;
}

class ValidationError extends VocabularyError {
  final String field;
  final String value;
  final String reason;

  ValidationError(this.field, this.value, this.reason, [Map<String, dynamic>? context])
      : super('Invalid $field: $reason', {
          'field': field,
          'value': value,
          'reason': reason,
          if (context != null) ...context,
        });
}

class JyutpingValidationError extends ValidationError {
  JyutpingValidationError(String jyutping, String reason)
      : super('Jyutping', jyutping, reason);
}

class DuplicateEntryError extends VocabularyError {
  final String jyutping;
  final String? hanzi;

  DuplicateEntryError(this.jyutping, [this.hanzi, Map<String, dynamic>? context])
      : super(
          hanzi != null
              ? 'Entry already exists: $hanzi ($jyutping)'
              : 'Jyutping already exists: $jyutping',
          {
            'jyutping': jyutping,
            'hanzi': hanzi,
            if (context != null) ...context,
          },
        );
}
