import 'package:flutter/foundation.dart';

@immutable
class ToneBlock {
  final String label;
  final String syllable;
  final int tone;
  final String hint;

  const ToneBlock({
    required this.label,
    required this.syllable,
    required this.tone,
    required this.hint,
  });
}

@immutable
class MainState {
  final bool loading;
  final String? errorMessage;
  final List<String> categories;
  final String selectedCategory;
  final String hanzi;
  final String jyutping;
  final List<String> meanings;
  final List<ToneBlock> toneBlocks;
  final List<String> radicals;
  final int? highlightIndex;
  final bool showDelays;
  final bool showAbout;
  final bool showToneRadicals;
  final int wpm;
  final int repeats;
  final int introDelay;
  final int repeatDelay;
  final int extroDelay;
  final int autoDelay;
  final bool tortoise;
  final bool autoMode;
  final bool isPlaying;
  final bool ttsArmed;
  final String aboutText;
  final String ttsEngine;
  final List<Map<String, String>> googleVoices;
  final String? selectedGoogleVoice;
  final String macosVoice;
  final bool googleAvailable;
  final bool googleVoicesFromProxy;

  const MainState({
    required this.loading,
    required this.errorMessage,
    required this.categories,
    required this.selectedCategory,
    required this.hanzi,
    required this.jyutping,
    required this.meanings,
    required this.toneBlocks,
    required this.radicals,
    required this.highlightIndex,
    required this.showDelays,
    required this.showAbout,
    required this.showToneRadicals,
    required this.wpm,
    required this.repeats,
    required this.introDelay,
    required this.repeatDelay,
    required this.extroDelay,
    required this.autoDelay,
    required this.tortoise,
    required this.autoMode,
    required this.isPlaying,
    required this.ttsArmed,
    required this.aboutText,
    required this.ttsEngine,
    required this.googleVoices,
    required this.selectedGoogleVoice,
    required this.macosVoice,
    required this.googleAvailable,
    required this.googleVoicesFromProxy,
  });

  factory MainState.initial() {
    return const MainState(
      loading: true,
      errorMessage: null,
      categories: ['All'],
      selectedCategory: 'All',
      hanzi: '',
      jyutping: '',
      meanings: [],
      toneBlocks: [],
      radicals: [],
      highlightIndex: null,
      showDelays: false,
      showAbout: false,
      showToneRadicals: true,
      wpm: 120,
      repeats: 1,
      introDelay: 0,
      repeatDelay: 0,
      extroDelay: 0,
      autoDelay: 0,
      tortoise: false,
      autoMode: false,
      isPlaying: false,
      ttsArmed: false,
      aboutText:
          'This screen mirrors the main window from the Python app. '
          'Wire real data, TTS, and playback here.',
      ttsEngine: 'google',
      googleVoices: [],
      selectedGoogleVoice: null,
      macosVoice: 'Sinji',
      googleAvailable: false,
      googleVoicesFromProxy: false,
    );
  }

  MainState copyWith({
    bool? loading,
    String? errorMessage,
    List<String>? categories,
    String? selectedCategory,
    String? hanzi,
    String? jyutping,
    List<String>? meanings,
    List<ToneBlock>? toneBlocks,
    List<String>? radicals,
    int? highlightIndex,
    bool? showDelays,
    bool? showAbout,
    bool? showToneRadicals,
    int? wpm,
    int? repeats,
    int? introDelay,
    int? repeatDelay,
    int? extroDelay,
    int? autoDelay,
    bool? tortoise,
    bool? autoMode,
    bool? isPlaying,
    bool? ttsArmed,
    String? aboutText,
    String? ttsEngine,
    List<Map<String, String>>? googleVoices,
    String? selectedGoogleVoice,
    String? macosVoice,
    bool? googleAvailable,
    bool? googleVoicesFromProxy,
  }) {
    return MainState(
      loading: loading ?? this.loading,
      errorMessage: errorMessage ?? this.errorMessage,
      categories: categories ?? this.categories,
      selectedCategory: selectedCategory ?? this.selectedCategory,
      hanzi: hanzi ?? this.hanzi,
      jyutping: jyutping ?? this.jyutping,
      meanings: meanings ?? this.meanings,
      toneBlocks: toneBlocks ?? this.toneBlocks,
      radicals: radicals ?? this.radicals,
      highlightIndex: highlightIndex ?? this.highlightIndex,
      showDelays: showDelays ?? this.showDelays,
      showAbout: showAbout ?? this.showAbout,
      showToneRadicals: showToneRadicals ?? this.showToneRadicals,
      wpm: wpm ?? this.wpm,
      repeats: repeats ?? this.repeats,
      introDelay: introDelay ?? this.introDelay,
      repeatDelay: repeatDelay ?? this.repeatDelay,
      extroDelay: extroDelay ?? this.extroDelay,
      autoDelay: autoDelay ?? this.autoDelay,
      tortoise: tortoise ?? this.tortoise,
      autoMode: autoMode ?? this.autoMode,
      isPlaying: isPlaying ?? this.isPlaying,
      ttsArmed: ttsArmed ?? this.ttsArmed,
      aboutText: aboutText ?? this.aboutText,
      ttsEngine: ttsEngine ?? this.ttsEngine,
      googleVoices: googleVoices ?? this.googleVoices,
      selectedGoogleVoice: selectedGoogleVoice ?? this.selectedGoogleVoice,
      macosVoice: macosVoice ?? this.macosVoice,
      googleAvailable: googleAvailable ?? this.googleAvailable,
      googleVoicesFromProxy: googleVoicesFromProxy ?? this.googleVoicesFromProxy,
    );
  }
}
