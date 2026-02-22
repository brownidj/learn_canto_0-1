import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import '../../../data/asset_data_repository.dart';
import '../../../domain/jyutping_cue.dart';
import '../../../settings.dart';
import '../../services/main_tts_service.dart';
import '../../services/google_tts_timepoint_service.dart';
import '../../services/google_tts_player.dart';
import '../../services/google_tts_proxy_service.dart';
import 'main_state.dart';

class MainCubit extends Cubit<MainState> {
  MainCubit() : super(MainState.initial());

  int? _tortoisePrevWpm;
  final AssetDataRepository _repo = AssetDataRepository();
  final MainTtsService _tts = MainTtsService();
  GoogleTtsTimepointService? _googleTimepoints;
  GoogleTtsProxyService? _googleProxy;
  final GoogleTtsPlayer _googlePlayer = GoogleTtsPlayer();
  Map<String, dynamic> _vocab = <String, dynamic>{};
  Map<String, List<String>> _categories = <String, List<String>>{};
  List<String> _filtered = <String>[];
  int _index = 0;
  Timer? _highlightTimer;
  Timer? _hanziHighlightTimer;
  final List<Timer> _hanziHighlightTimers = [];
  int _highlightSeq = 0;
  bool _autoLooping = false;

  Future<void> loadData() async {
    emit(state.copyWith(loading: true, errorMessage: null));
    try {
      await _loadVoices();
      final legacy = await _repo.loadLegacyVocab();
      final vocab = legacy['vocab'];
      final catsMap = legacy['categories'];
      if (vocab is Map) {
        _vocab = vocab.map((k, v) => MapEntry(k.toString(), v));
      }
      if (catsMap is Map) {
        _categories = catsMap.map((k, v) {
          if (v is List) {
            return MapEntry(k.toString(), v.map((e) => e.toString()).toList());
          }
          return MapEntry(k.toString(), <String>[]);
        });
      }
      final categories = _categories.keys.toList()..sort();
      if (!categories.contains('All')) {
        categories.insert(0, 'All');
      }
      _applyCategory(state.selectedCategory, categories: categories);
    } catch (e) {
      emit(state.copyWith(
        loading: false,
        errorMessage: 'Failed to load data: $e',
      ));
    }
  }

  void setCategory(String value) {
    _applyCategory(value);
  }

  void toggleDelays() {
    emit(state.copyWith(showDelays: !state.showDelays));
  }

  void toggleAbout() {
    emit(state.copyWith(showAbout: !state.showAbout));
  }

  // Tone/Radicals toggle removed in Flutter UI.

  void setWpm(int value) {
    emit(state.copyWith(wpm: value));
  }

  void setRepeats(int value) {
    emit(state.copyWith(repeats: value));
  }

  void setIntroDelay(int value) {
    emit(state.copyWith(introDelay: value));
  }

  void setRepeatDelay(int value) {
    emit(state.copyWith(repeatDelay: value));
  }

  void setExtroDelay(int value) {
    emit(state.copyWith(extroDelay: value));
  }

  void setAutoDelay(int value) {
    emit(state.copyWith(autoDelay: value));
  }

  void toggleTortoise(bool enabled) {
    if (!state.ttsArmed || state.isPlaying || state.autoMode) {
      return;
    }
    if (enabled) {
      _tortoisePrevWpm = state.wpm;
      emit(state.copyWith(tortoise: true, wpm: 60));
    } else {
      final prev = _tortoisePrevWpm ?? state.wpm;
      emit(state.copyWith(tortoise: false, wpm: prev));
    }
  }

  void toggleAuto(bool enabled) {
    if (!state.ttsArmed && !state.autoMode) {
      return;
    }
    emit(state.copyWith(autoMode: enabled));
    if (enabled) {
      _startAutoLoop();
    } else {
      _autoLooping = false;
    }
  }

  Future<void> _loadVoices() async {
    List<Map<String, String>> google = [];
    var fromProxy = false;
    if (googleTtsProxyUrl().isNotEmpty) {
      try {
        _googleProxy ??= GoogleTtsProxyService(Uri.parse(googleTtsProxyUrl()));
        google = await _googleProxy!.listVoices();
        fromProxy = google.isNotEmpty;
      } catch (e) {
        if (kDebugMode) {
          debugPrint('TTS: proxy voices failed: $e');
        }
      }
    }
    if (google.isEmpty) {
      final voices = await _tts.listVoices();
      google = voices.where((v) {
        final locale = (v['locale'] ?? '').toLowerCase();
        return locale.startsWith('yue');
      }).toList();
      fromProxy = false;
    }
    String? selected;
    if (google.isNotEmpty) {
      selected = google.first['name'];
    }
    final googleConfigured = _googleConfigured();
    if (kDebugMode) {
      debugPrint('TTS: google voices=${google.length} proxy=${googleTtsProxyUrl().isNotEmpty} apiKey=${googleTtsApiKey().isNotEmpty}');
    }
    final googleAvailable = google.isNotEmpty || googleConfigured;
    emit(state.copyWith(
      googleVoices: google,
      selectedGoogleVoice: selected,
      ttsEngine: googleAvailable ? 'google' : 'macos',
      googleAvailable: googleAvailable,
      googleVoicesFromProxy: fromProxy,
    ));
  }

  void setTtsEngine(String engine) {
    if (engine != 'google' && engine != 'macos') {
      return;
    }
    if (engine == 'google' && !state.googleAvailable) {
      return;
    }
    emit(state.copyWith(ttsEngine: engine));
  }

  void setGoogleVoice(String? name) {
    emit(state.copyWith(selectedGoogleVoice: name));
  }

  void resetSettings() {
    _autoLooping = false;
    _tortoisePrevWpm = null;
    emit(state.copyWith(
      wpm: 120,
      repeats: 1,
      introDelay: 0,
      repeatDelay: 0,
      extroDelay: 0,
      autoDelay: 0,
      tortoise: false,
      autoMode: false,
      ttsArmed: false,
    ));
    _applyCategory('All');
  }

  void nextItem() {
    if (_filtered.isEmpty) {
      return;
    }
    if (state.isPlaying) {
      return;
    }
    final armed = state.ttsArmed;
    _index = (_index + 1) % _filtered.length;
    _emitCurrent();
    if (armed) {
      unawaited(playSequence());
    }
  }

  void prevItem() {
    if (_filtered.isEmpty) {
      return;
    }
    if (state.isPlaying) {
      return;
    }
    final armed = state.ttsArmed;
    _index = (_index - 1) < 0 ? _filtered.length - 1 : _index - 1;
    _emitCurrent();
    if (armed) {
      unawaited(playSequence());
    }
  }

  Future<void> playOnce() async {
    final hanzi = state.hanzi.trim();
    if (hanzi.isEmpty) {
      return;
    }
    if (state.ttsEngine == 'google' && _googleConfigured()) {
      await _playWithGoogleTimepoints(hanzi, state.wpm, enableHighlight: false);
      return;
    }
    final voice = state.selectedGoogleVoice;
    final locale = state.ttsEngine == 'google' ? 'yue-HK' : null;
    await _tts.speak(
      hanzi,
      rate: _wpmToRate(state.wpm),
      voiceName: state.ttsEngine == 'google' && !state.googleVoicesFromProxy ? voice : null,
      locale: locale,
    );
  }

  Future<void> playSequence() async {
    if (state.isPlaying) {
      return;
    }
    if (!state.ttsArmed) {
      emit(state.copyWith(ttsArmed: true));
    }
    emit(state.copyWith(isPlaying: true));
    final hanzi = state.hanzi.trim();
    if (hanzi.isEmpty) {
      emit(state.copyWith(isPlaying: false));
      return;
    }
    if (state.introDelay > 0) {
      await Future.delayed(Duration(seconds: state.introDelay));
    }
    for (var i = 0; i < state.repeats; i++) {
      if (state.ttsEngine == 'google' && _canUseGoogleTimepoints()) {
        if (kDebugMode) {
          debugPrint('TTS: using google timepoints (proxy=${googleTtsProxyUrl().isNotEmpty})');
        }
        final ok = await _playWithGoogleTimepoints(
          hanzi,
          state.wpm,
          enableHighlight: _shouldHighlightDuringPlayback(),
        );
        if (!ok) {
          if (kDebugMode) {
            debugPrint('TTS: google timepoints failed, falling back to flutter_tts');
          }
          await _tts.speakAndWait(
            hanzi,
            rate: _wpmToRate(state.wpm),
            voiceName: state.ttsEngine == 'google' && !state.googleVoicesFromProxy
                ? state.selectedGoogleVoice
                : null,
            locale: state.ttsEngine == 'google' ? 'yue-HK' : null,
          );
        }
      } else {
        if (kDebugMode) {
          debugPrint('TTS: using flutter_tts (highlight=${_shouldHighlightDuringPlayback()}, googleReady=${_canUseGoogleTimepoints()})');
        }
        if (_shouldHighlightDuringPlayback()) {
          _scheduleHanziHighlights(hanzi, state.wpm);
        }
        await _tts.speakAndWait(
          hanzi,
          rate: _wpmToRate(state.wpm),
          voiceName: state.ttsEngine == 'google' && !state.googleVoicesFromProxy
              ? state.selectedGoogleVoice
              : null,
          locale: state.ttsEngine == 'google' ? 'yue-HK' : null,
        );
      }
      if (i + 1 < state.repeats && state.repeatDelay > 0) {
        await Future.delayed(Duration(seconds: state.repeatDelay));
      }
    }
    if (state.autoMode && state.extroDelay > 0) {
      await Future.delayed(Duration(seconds: state.extroDelay));
    }
    emit(state.copyWith(isPlaying: false));
  }

  Future<void> playSyllable(int index) async {
    if (index < 0 || index >= state.toneBlocks.length) {
      return;
    }
    _highlightTimer?.cancel();
    emit(state.copyWith(highlightIndex: index));
    final block = state.toneBlocks[index];
    final text = block.syllable.isNotEmpty ? block.syllable : block.label;
    await _tts.speak(text, rate: _wpmToRate(state.wpm));
    _highlightTimer = Timer(const Duration(milliseconds: 600), () {
      emit(state.copyWith(highlightIndex: null));
    });
  }

  void _startAutoLoop() {
    if (_autoLooping) {
      return;
    }
    _autoLooping = true;
    unawaited(_autoTick());
  }

  Future<void> _autoTick() async {
    while (_autoLooping) {
      await playSequence();
      if (!_autoLooping) {
        break;
      }
      if (state.autoDelay > 0) {
        await Future.delayed(Duration(seconds: state.autoDelay));
      }
      if (!_autoLooping) {
        break;
      }
      nextItem();
    }
  }

  void _applyCategory(String value, {List<String>? categories}) {
    final selected = value.trim().isEmpty ? 'All' : value;
    final list = List<String>.from(categories ?? state.categories);
    if (!list.contains(selected)) {
      list.insert(0, selected);
    }
    if (selected == 'All') {
      _filtered = _vocab.keys.toList()..sort();
    } else {
      _filtered = List<String>.from(_categories[selected] ?? <String>[])..sort();
    }
    _index = 0;
    _autoLooping = false;
    _emitCurrent(
      categories: list,
      selectedCategory: selected,
    );
    emit(state.copyWith(
      tortoise: false,
      autoMode: false,
      isPlaying: false,
      ttsArmed: false,
    ));
  }

  void _emitCurrent({List<String>? categories, String? selectedCategory}) {
    if (_filtered.isEmpty) {
      emit(state.copyWith(
        loading: false,
        categories: categories ?? state.categories,
        selectedCategory: selectedCategory ?? state.selectedCategory,
        hanzi: '',
        jyutping: '',
        meanings: const [],
        toneBlocks: const [],
        radicals: const [],
        highlightIndex: null,
      ));
      return;
    }
    final hz = _filtered[_index];
    final raw = _vocab[hz];
    List<String> meanings = [];
    String jyut = '';
    if (raw is List && raw.isNotEmpty) {
      final m = raw[0];
      if (m is List) {
        meanings = m.map((e) => e.toString()).toList();
      }
      if (raw.length > 1) {
        jyut = raw[1]?.toString() ?? '';
      }
    }
    final toneBlocks = _buildToneBlocks(jyut);
    final radicals = _deriveRadicals(hz);
    emit(state.copyWith(
      loading: false,
      categories: categories ?? state.categories,
      selectedCategory: selectedCategory ?? state.selectedCategory,
      hanzi: hz,
      jyutping: jyut,
      meanings: meanings,
      toneBlocks: toneBlocks,
      radicals: radicals,
      highlightIndex: null,
    ));
  }

  Iterable<String> _toneTokens(String jyutping) {
    final matchRe = RegExp(r'[a-z]+[1-6]', caseSensitive: false);
    final matched = matchRe.allMatches(jyutping).map((m) => m.group(0) ?? '').where((t) => t.isNotEmpty);
    if (matched.isNotEmpty) {
      return matched;
    }
    return jyutping.trim().split(RegExp(r'\\s+')).where((t) => t.isNotEmpty);
  }

  Iterable<String> debugToneTokens(String jyutping) => _toneTokens(jyutping);

  List<ToneBlock> _buildToneBlocks(String jyutping) {
    final tokens = _toneTokens(jyutping);
    final blocks = <ToneBlock>[];
    for (final token in tokens) {
      final m = RegExp(r'^(.*?)([0-6])$').firstMatch(token);
      if (m == null) {
        blocks.add(ToneBlock(
          label: cueForSyllable(token),
          syllable: token,
          tone: 0,
          hint: hintForSyllable(token),
        ));
        continue;
      }
      final tone = int.tryParse(m.group(2) ?? '') ?? 0;
      blocks.add(ToneBlock(
        label: cueForSyllable(token),
        syllable: token,
        tone: tone,
        hint: hintForSyllable(token),
      ));
    }
    return blocks;
  }

  List<String> _deriveRadicals(String hanzi) {
    final chars = hanzi.runes.map((r) => String.fromCharCode(r)).toList();
    if (chars.isEmpty) {
      return const [];
    }
    if (chars.length == 1) {
      return chars;
    }
    return chars.take(2).toList();
  }

  double _wpmToRate(int wpm) {
    const minWpm = 60;
    const maxWpm = 220;
    final clamped = wpm.clamp(minWpm, maxWpm);
    final t = (clamped - minWpm) / (maxWpm - minWpm);
    return 0.2 + (0.6 * t);
  }

  bool _shouldHighlightDuringPlayback() {
    if (state.ttsEngine != 'google') {
      return false;
    }
    return state.wpm <= 80 || state.tortoise;
  }

  bool _canUseGoogleTimepoints() {
    return _googleConfigured();
  }

  bool _googleConfigured() {
    return googleTtsProxyUrl().isNotEmpty || googleTtsApiKey().isNotEmpty;
  }

  Future<bool> _playWithGoogleTimepoints(String hanzi, int wpm, {required bool enableHighlight}) async {
    if (_googleConfigured() && googleTtsProxyUrl().isNotEmpty) {
      return _playWithGoogleProxy(hanzi, wpm, enableHighlight: enableHighlight);
    }
    final key = googleTtsApiKey();
    if (key.isEmpty) {
      return false;
    }
    _googleTimepoints ??= GoogleTtsTimepointService(key);
    final speakingRate = _wpmToRate(wpm);
    try {
      final resp = await _googleTimepoints!.synthesizeWithTimepoints(
        text: hanzi,
        voiceName: state.selectedGoogleVoice,
        speakingRate: speakingRate,
      );
      final audio = resp['audioContent']?.toString() ?? '';
      final timepoints = (resp['timepoints'] as List<dynamic>?) ?? const [];
      if (audio.isEmpty) {
        return false;
      }
      if (enableHighlight && timepoints.isEmpty) {
        return false;
      }
      final handle = await _googlePlayer.playBase64Mp3(audio);
      final seq = enableHighlight ? _scheduleTimepointHighlights(timepoints, hanzi, handle.startedAt) : null;
      await handle.completed;
      if (enableHighlight && seq == _highlightSeq) {
        _clearHanziHighlights();
      }
      return true;
    } catch (e) {
      if (kDebugMode) {
        debugPrint('TTS: google proxy error: $e');
      }
      return false;
    }
  }

  Future<bool> _playWithGoogleProxy(String hanzi, int wpm, {required bool enableHighlight}) async {
    final url = googleTtsProxyUrl();
    if (url.isEmpty) {
      return false;
    }
    _googleProxy ??= GoogleTtsProxyService(Uri.parse(url));
    try {
      if (kDebugMode) {
        debugPrint('TTS: proxy request url=$url textLen=${hanzi.length} wpm=$wpm');
      }
      final resp = await _googleProxy!.synthesizeWithTimepoints(
        text: hanzi,
        voiceName: state.selectedGoogleVoice,
        rate: wpm,
      );
      final audio = resp['audioContent']?.toString() ?? '';
      final timepoints = (resp['timepoints'] as List<dynamic>?) ?? const [];
      if (audio.isEmpty) {
        if (kDebugMode) {
          debugPrint('TTS: google proxy empty payload audioLen=${audio.length} timepoints=${timepoints.length}');
        }
        return false;
      }
      if (enableHighlight && timepoints.isEmpty) {
        if (kDebugMode) {
          debugPrint('TTS: google proxy missing timepoints for highlight');
        }
        return false;
      }
      if (kDebugMode) {
        debugPrint('TTS: google proxy ok audioLen=${audio.length} timepoints=${timepoints.length}');
      }
      final handle = await _googlePlayer.playBase64Mp3(audio);
      final seq = enableHighlight ? _scheduleTimepointHighlights(timepoints, hanzi, handle.startedAt) : null;
      await handle.completed;
      if (enableHighlight && seq == _highlightSeq) {
        _clearHanziHighlights();
      }
      return true;
    } catch (e) {
      if (kDebugMode) {
        debugPrint('TTS: google proxy error: $e');
      }
      return false;
    }
  }
  int _scheduleTimepointHighlights(List<dynamic> timepoints, String hanzi, DateTime startedAt) {
    _clearHanziHighlights();
    final seq = _highlightSeq;
    final entries = <({int index, int ms})>[];
    for (final tp in timepoints) {
      if (tp is! Map) {
        continue;
      }
      final name = tp['markName']?.toString() ?? '';
      final t = tp['timeSeconds'];
      if (!name.startsWith('s') || t is! num) {
        continue;
      }
      final idx = int.tryParse(name.substring(1)) ?? -1;
      if (idx < 0) {
        continue;
      }
      entries.add((index: idx, ms: (t * 1000).round()));
    }
    if (entries.isEmpty) {
      return seq;
    }
    entries.sort((a, b) => a.ms.compareTo(b.ms));
    final startMs = startedAt.millisecondsSinceEpoch;
    final nowMs = DateTime.now().millisecondsSinceEpoch;
    for (final entry in entries) {
      final delayMs = (startMs + entry.ms) - nowMs;
      final timer = Timer(Duration(milliseconds: delayMs < 0 ? 0 : delayMs), () {
        if (seq == _highlightSeq) {
          emit(state.copyWith(highlightIndex: entry.index));
        }
      });
      _hanziHighlightTimers.add(timer);
    }
    final last = entries.last.ms;
    final clearDelayMs = (startMs + last + 250) - nowMs;
    final clearTimer = Timer(Duration(milliseconds: clearDelayMs < 0 ? 0 : clearDelayMs), () {
      if (seq == _highlightSeq) {
        emit(state.copyWith(highlightIndex: null));
      }
    });
    _hanziHighlightTimers.add(clearTimer);
    return seq;
  }

  void _scheduleHanziHighlights(String hanzi, int wpm) {
    _clearHanziHighlights();
    final seq = _highlightSeq;
    final chars = hanzi.runes.map((r) => String.fromCharCode(r)).toList();
    if (chars.isEmpty) {
      return;
    }
    final baseMs = 60000 / wpm;
    final msPerChar = (baseMs * 0.65).clamp(120, 1600).toInt();
    final leadMs = (baseMs * 0.25).clamp(80, 300).toInt();
    final start = DateTime.now().millisecondsSinceEpoch - leadMs;
    _hanziHighlightTimer = Timer.periodic(const Duration(milliseconds: 50), (timer) {
      if (seq != _highlightSeq) {
        timer.cancel();
        return;
      }
      final elapsed = DateTime.now().millisecondsSinceEpoch - start;
      final idx = elapsed ~/ msPerChar;
      if (idx >= chars.length) {
        timer.cancel();
        if (seq == _highlightSeq) {
          emit(state.copyWith(highlightIndex: null));
        }
        return;
      }
      emit(state.copyWith(highlightIndex: idx));
    });
  }

  void _clearHanziHighlights() {
    _highlightSeq += 1;
    _hanziHighlightTimer?.cancel();
    _hanziHighlightTimer = null;
    for (final timer in _hanziHighlightTimers) {
      timer.cancel();
    }
    _hanziHighlightTimers.clear();
    emit(state.copyWith(highlightIndex: null));
  }

  @override
  Future<void> close() async {
    _highlightTimer?.cancel();
    _clearHanziHighlights();
    _autoLooping = false;
    await _tts.stop();
    return super.close();
  }
}
