import 'dart:async';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter_tts/flutter_tts.dart';

class MainTtsService {
  final FlutterTts _tts = FlutterTts();
  bool _initialized = false;
  String? _defaultLocale;

  Future<void> _init() async {
    if (_initialized) {
      return;
    }
    _initialized = true;
    await _tts.awaitSpeakCompletion(true);
    if (Platform.isIOS) {
      await _tts.setSharedInstance(true);
      await _tts.setIosAudioCategory(
        IosTextToSpeechAudioCategory.playback,
        [
          IosTextToSpeechAudioCategoryOptions.mixWithOthers,
          IosTextToSpeechAudioCategoryOptions.defaultToSpeaker,
        ],
      );
    }
    try {
      final languages = await _tts.getLanguages;
      if (languages is List) {
        final normalized = languages.map((e) => e.toString()).toList();
        _defaultLocale = _pickDefaultLocale(normalized);
      }
    } catch (_) {}
    _tts.setErrorHandler((msg) {
      debugPrint('TTS: flutter_tts error=$msg');
    });
    _tts.setStartHandler(() {
      debugPrint('TTS: flutter_tts start');
    });
    _tts.setCompletionHandler(() {
      debugPrint('TTS: flutter_tts complete');
    });
  }

  Future<List<Map<String, String>>> listVoices() async {
    await _init();
    try {
      final voices = await _tts.getVoices;
      if (voices is List) {
        return voices.map<Map<String, String>>((v) {
          if (v is Map) {
            return v.map((k, val) => MapEntry(k.toString(), val.toString()));
          }
          return <String, String>{};
        }).where((v) => v.isNotEmpty).toList();
      }
    } catch (_) {}
    return [];
  }

  Future<void> stop() async {
    await _tts.stop();
  }

  Future<void> speak(
    String text, {
    double? rate,
    String? voiceName,
    String? locale,
  }) async {
    await _init();
    debugPrint('TTS: flutter_tts speak len=${text.length} rate=$rate voice=$voiceName locale=$locale');
    await _tts.stop();
    final resolvedLocale = (locale == null || locale.isEmpty) ? _defaultLocale : locale;
    if (resolvedLocale != null && resolvedLocale.isNotEmpty) {
      await _tts.setLanguage(resolvedLocale);
    }
    if (voiceName != null && voiceName.isNotEmpty) {
      await _tts.setVoice({'name': voiceName, 'locale': resolvedLocale ?? ''});
    }
    if (rate != null) {
      await _tts.setSpeechRate(rate);
    }
    await _tts.speak(text);
  }

  Future<void> speakAndWait(
    String text, {
    double? rate,
    String? voiceName,
    String? locale,
  }) async {
    await _init();
    debugPrint('TTS: flutter_tts speakAndWait len=${text.length} rate=$rate voice=$voiceName locale=$locale');
    await _tts.stop();
    final resolvedLocale = (locale == null || locale.isEmpty) ? _defaultLocale : locale;
    if (resolvedLocale != null && resolvedLocale.isNotEmpty) {
      await _tts.setLanguage(resolvedLocale);
    }
    if (voiceName != null && voiceName.isNotEmpty) {
      await _tts.setVoice({'name': voiceName, 'locale': resolvedLocale ?? ''});
    }
    if (rate != null) {
      await _tts.setSpeechRate(rate);
    }
    final completer = Completer<void>();
    Timer? timeout;
    void completeIfNeeded() {
      if (timeout?.isActive ?? false) {
        timeout?.cancel();
      }
      if (!completer.isCompleted) {
        completer.complete();
      }
    }

    _tts.setCompletionHandler(completeIfNeeded);
    _tts.setErrorHandler((_) => completeIfNeeded());
    await _tts.speak(text);

    final baseMs = (rate == null || rate <= 0) ? 800 : (800 / rate).round();
    final timeoutMs = (text.isEmpty ? 1000 : (text.length * baseMs)).clamp(1500, 10000);
    final isSimulator = Platform.isIOS && Platform.environment.containsKey('SIMULATOR_DEVICE_NAME');
    if (isSimulator) {
      timeout = Timer(Duration(milliseconds: timeoutMs), () {
        debugPrint('TTS: flutter_tts timeout after ${timeoutMs}ms');
        _tts.stop();
        completeIfNeeded();
      });
    }

    await completer.future;
  }

  String? _pickDefaultLocale(List<String> languages) {
    if (languages.isEmpty) {
      return null;
    }
    const preferred = ['yue-HK', 'zh-HK', 'zh-CN', 'en-US', 'en-GB'];
    for (final locale in preferred) {
      final match = languages.firstWhere(
        (l) => l.toLowerCase() == locale.toLowerCase(),
        orElse: () => '',
      );
      if (match.isNotEmpty) {
        return match;
      }
    }
    return languages.first;
  }
}
